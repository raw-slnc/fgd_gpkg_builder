# -*- coding: utf-8 -*-
"""時間のかかる処理（一覧の問い合わせ・ダウンロード・取り込み）を行う別スレッド。"""

import os
import shutil
import tempfile
import time
from datetime import datetime, timezone

from osgeo import gdal
from qgis.PyQt.QtCore import QThread, pyqtSignal

from . import fgd_api, store
from .catalog import BV_SOURCE_URL, BV_ZOOM, FGD_TYPE_BY_CODE, FGD_TYPES, fgd_type_name
from .i18n import tr
from .tiles import tile_bounds_3857, tile_center_lonlat, tiles_for_bounds

BV_USER_AGENT = "QGIS fgd_gpkg_builder plugin"
# 一時的な調べもの用：取り込んだ基盤地図情報の ZIP を消さずに残す（行政区画界線・町字界線が入らない件）。
# 残した場所は記録に出す。調べ終わったら False に戻す
KEEP_FGD_ZIPS = False


class ListThread(QThread):
    """表示範囲のメッシュについて、種類ごとの最新データの一覧を問い合わせる（ログイン不要）"""

    progress = pyqtSignal(int, int)  # 問い合わせ終えたメッシュの数, 全体の数

    def __init__(self, meshes):
        super().__init__()
        self.meshes = list(meshes)
        self.results = []
        self.error = ""

    def run(self):
        try:
            self.results = fgd_api.query_latest(
                fgd_api.new_session(), [t["code"] for t in FGD_TYPES], self.meshes, progress_cb=self.progress.emit
            )
        except Exception as e:  # 通信の失敗は理由をそのまま見せる
            self.error = str(e)


class StoredThread(QThread):
    """保存先の取得の記録を読む（大きな GeoPackage では時間がかかるので、窓を開くのを待たせない）。

    results: {"fgd": {(mesh, type_code): data_date}, "bv": {source_layer: {メッシュ: タイル数}}}
    最適化ベクトルタイルは、中心が入るメッシュに数える（隣のメッシュと重ねて数えない）"""

    progress = pyqtSignal(int, int)  # 読んだ行数, 全体の行数（取得の記録の行）

    EVERY = 2000  # 進み具合を送る行の間隔

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.results = {"fgd": {}, "bv": {}}

    def run(self):
        try:
            if not self.path or not os.path.exists(self.path):
                return
            fgd_rows, bv_rows = store.record_counts(self.path)
            total = fgd_rows + bv_rows
            self.progress.emit(0, total)
            fgd = store.read_fgd_dates(self.path, lambda n: self.progress.emit(n, total), self.EVERY)
            bv = {}
            for n, (name, x, y) in enumerate(store.iter_bv_tiles(self.path, BV_ZOOM), 1):
                lon, lat = tile_center_lonlat(x, y, BV_ZOOM)
                mesh = fgd_api.latlon_to_mesh2(lat, lon)
                per_mesh = bv.setdefault(name, {})
                per_mesh[mesh] = per_mesh.get(mesh, 0) + 1
                if n % self.EVERY == 0:
                    self.progress.emit(fgd_rows + n, total)
            self.progress.emit(total, total)
            self.results = {"fgd": fgd, "bv": bv}
        except Exception:  # 壊れたファイルなどは「保存なし」として扱う
            self.results = {"fgd": {}, "bv": {}}


def plan_fgd_downloads(listing, stored, type_codes, skip_current):
    """取得するもの [(mesh, type_code, [一覧の項目...])] を決める。保存済みで同じ日付なら除く"""
    groups = {}
    for item in listing:
        type_code = item.get("type_code")
        if type_code not in type_codes:
            continue
        groups.setdefault((item["place_code"], type_code), []).append(item)
    plan = []
    for (mesh, type_code), items in sorted(groups.items()):
        items.sort(key=lambda i: i.get("file_split_seq_no") or 0)
        if skip_current and stored.get((mesh, type_code)) == fgd_api.item_date(items[0]):
            continue
        plan.append((mesh, type_code, items))
    return plan


def mesh_tiles(mesh):
    """2次メッシュの範囲を覆う最適化ベクトルタイル"""
    return tiles_for_bounds(*fgd_api.mesh2_bounds(mesh), BV_ZOOM)


class FetchThread(QThread):
    """2次メッシュを1つずつ（ブロックごとに）取得する。

    1つのブロックでは、チェックした基盤地図情報の種類すべてと、そのメッシュに掛かる最適化ベクトルタイルを
    取り、まとめて書き込む。止めるときは今のブロックを終えてから止める（stop_after_block）。
    すぐに止めたとき（cancel）は、途中のブロックは書き込まない"""

    stage = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # 全体の進み（済んだメッシュの数, 全体の数）
    file_progress = pyqtSignal(int, int)  # 今の作業の進み（済んだ量, 全体の量）
    log = pyqtSignal(str)

    def __init__(self, session, path, meshes, fgd_layers, bv_items, skip_current):
        """fgd_layers: {type_code: [レイヤー名...]}"""
        super().__init__()
        self.session = session
        self.path = path
        self.meshes = sorted(meshes)
        self.fgd_layers = dict(fgd_layers)
        self.bv_items = list(bv_items)
        self.skip_current = skip_current
        self.need_login = False
        self.error = ""
        self.summary = []
        self.done_meshes = []
        self.stopped_early = False
        self._stop_after_block = False
        self._cancelled = False

    def stop_after_block(self):
        self._stop_after_block = True

    def cancel(self):
        self._stop_after_block = True
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def is_stopping(self):
        return self._stop_after_block

    def _check_cancel(self):
        if self._cancelled:
            raise InterruptedError()

    def run(self):
        bv_ds = None
        try:
            fgd_plan, absent = self._plan_fgd() if self.fgd_layers else ({}, {})
            if self.need_login:
                return
            source_date = ""
            bv_stored = []
            if self.bv_items:
                bv_ds, source_date = _open_bvmap()
                if self.skip_current and source_date:
                    # 同じ配信データから取ったタイルは取り直さない（項目ごとに確かめ、どれかが古ければ取る）
                    bv_stored = [store.stored_bv_tiles(self.path, i["source_layer"], BV_ZOOM) for i in self.bv_items]
            blocks = self._plan_blocks(fgd_plan, absent, bv_stored, source_date)
            if not blocks:
                self.summary.append(tr("Everything stored is up to date. Nothing needs fetching.",
                                       "保存済みのものがすべて最新でした。取得の必要なものはありません。"))
                return
            self._run_blocks(blocks, bv_ds, source_date)
        except InterruptedError:
            self.log.emit(tr("Stopped immediately. The mesh in progress is left as it was before the fetch.",
                             "すぐに止めました。途中だったメッシュは取得する前の状態のままです。"))
        except Exception as e:  # 理由を問わず画面で知らせる
            self.error = str(e)
        finally:
            bv_ds = None

    # ---- 計画 ----

    def _plan_fgd(self):
        """({mesh: [(type_code, [一覧の項目...])]}, {mesh: [データの無い type_code]})"""
        self.stage.emit(tr("Fundamental Geospatial Data: querying the list of the latest data…",
                           "基盤地図情報：最新データの一覧を問い合わせています…"))
        listing = fgd_api.query_latest(fgd_api.new_session(), list(self.fgd_layers), self.meshes)
        stored = store.stored_fgd_dates(self.path)
        plan = {}
        for mesh, type_code, items in plan_fgd_downloads(listing, stored, set(self.fgd_layers), self.skip_current):
            plan.setdefault(mesh, []).append((type_code, items))
        listed = {(i["place_code"], i.get("type_code")) for i in listing}
        absent = {}
        for mesh in self.meshes:
            for type_code in self.fgd_layers:
                if (mesh, type_code) not in listed and (mesh, type_code) not in stored:
                    absent.setdefault(mesh, []).append(type_code)
        if plan and (self.session is None or not fgd_api.check_login(self.session)):
            # ダウンロードにはログインが必要。画面でログインしてから、もう一度始める
            self.need_login = True
        return plan, absent

    def _plan_blocks(self, fgd_plan, absent, bv_stored, source_date):
        """[(mesh, [(type_code, items)], [データの無い type_code], [(x, y)])]"""
        blocks = []
        claimed = set()  # 隣のメッシュと掛かるタイルは、先のメッシュで取る
        for mesh in self.meshes:
            tiles = []
            if self.bv_items:
                for tile in mesh_tiles(mesh):
                    if tile in claimed:
                        continue
                    claimed.add(tile)
                    if bv_stored and all(s.get(tile) == source_date for s in bv_stored):
                        continue
                    tiles.append(tile)
            fgd = fgd_plan.get(mesh, [])
            if fgd or tiles or absent.get(mesh):
                blocks.append((mesh, fgd, absent.get(mesh, []), tiles))
        if not blocks:
            return blocks
        downloads = [i for _m, fgd, _a, _t in blocks for _c, items in fgd for i in items]
        tile_count = sum(len(t) for _m, _f, _a, t in blocks)
        self.log.emit(tr(
            "Fetching {0} meshes (Fundamental Geospatial Data: {1} files, about {2:.1f} MB; "
            "optimized vector tiles: {3}).",
            "{0} メッシュを取得します（基盤地図情報 {1} ファイル・約 {2:.1f} MB、最適化ベクトルタイル {3} 枚）。",
        ).format(len(blocks), len(downloads), sum(fgd_api.item_size(i) for i in downloads) / 1024 / 1024,
                 tile_count))
        return blocks

    # ---- 取得 ----

    def _run_blocks(self, blocks, bv_ds, source_date):
        work_dir = tempfile.mkdtemp(prefix="fgd_gpkg_builder_")
        started = time.monotonic()
        unknown = set()
        try:
            for index, block in enumerate(blocks):
                if self._stop_after_block:
                    self.stopped_early = True
                    break
                self.progress.emit(index, len(blocks))
                if not self._run_block(index, len(blocks), block, bv_ds, source_date, work_dir, unknown):
                    return
                self.done_meshes.append(block[0])
            self.progress.emit(len(self.done_meshes), len(blocks))
        finally:
            if KEEP_FGD_ZIPS:
                self.log.emit(tr("Kept the Fundamental Geospatial Data ZIP files: ", "基盤地図情報の ZIP を残しました：")
                              + work_dir)
            else:
                shutil.rmtree(work_dir, ignore_errors=True)
            if unknown:
                self.log.emit(tr("The ZIP files contained layers that are not in the list (not imported): ",
                                 "一覧に無いレイヤーが ZIP にありました（取り込んでいません）：")
                              + tr(", ", "、").join(sorted(unknown)))
            if self.done_meshes or self.stopped_early:
                text = tr("Imported {0} of {1} meshes ({2:.0f} s).", "{0} / {1} メッシュを取り込みました（{2:.0f} 秒）。").format(
                    len(self.done_meshes), len(blocks), time.monotonic() - started)
                if self.stopped_early:
                    text += tr(" The remaining meshes were not fetched (the imported meshes are complete).",
                               "残りのメッシュは取得していません（取り込んだメッシュはそろっています）。")
                self.summary.append(text)

    def _run_block(self, index, total, block, bv_ds, source_date, work_dir, unknown):
        """1つのメッシュを取得して書き込む。ログインが切れて続けられないときは False"""
        mesh, fgd, absent_codes, tiles = block
        head = tr("Mesh {0} ({1} of {2})", "メッシュ {0}（{1} / {2}）").format(mesh, index + 1, total)
        entries = []
        zip_paths_all = []
        for type_code, items in fgd:
            self._check_cancel()
            type_info = FGD_TYPE_BY_CODE[type_code]
            zip_paths = []
            for n, item in enumerate(items):
                self.stage.emit(tr("{0}: downloading Fundamental Geospatial Data, {1} ({2} of {3})",
                                   "{0}：基盤地図情報 {1} をダウンロードしています（{2} / {3}）").format(
                    head, fgd_type_name(type_info), n + 1, len(items)))
                zip_path = os.path.join(work_dir, item["file_name"])
                size = fgd_api.item_size(item)
                try:
                    fgd_api.download_file(
                        self.session, item["id"], zip_path, cancel_cb=self.is_cancelled,
                        chunk_cb=lambda received, s=size: self.file_progress.emit(received, s),
                    )
                except fgd_api.LoginRequired:
                    self.need_login = True
                    self.log.emit(tr("The login expired, so the fetch stopped before {0}.",
                                     "ログインの有効期限が切れたため、{0} の前で止めました。").format(mesh))
                    return False
                zip_paths.append(zip_path)
            zip_paths_all.extend(zip_paths)
            entries.append({
                "type_info": type_info, "layer_codes": self.fgd_layers[type_code], "zip_paths": zip_paths,
                "data_date": fgd_api.item_date(items[0]), "file_names": [i["file_name"] for i in items],
            })

        results = []
        for n, (x, y) in enumerate(tiles):
            self._check_cancel()
            if n % 10 == 0:
                self.stage.emit(tr("{0}: optimized vector tiles {1} of {2}",
                                   "{0}：最適化ベクトルタイル {1} / {2} 枚").format(head, n, len(tiles)))
            results.append(self._read_tile(bv_ds, x, y))
            self.file_progress.emit(n + 1, len(tiles))

        self.stage.emit(tr("{0}: importing…", "{0}：取り込んでいます…").format(head))
        fgd_counts, bv_counts, found_unknown = store.write_block(
            self.path, mesh, entries, [FGD_TYPE_BY_CODE[c] for c in absent_codes], self.bv_items, BV_ZOOM,
            results, datetime.now().isoformat(timespec="seconds"), source_date, cancel_cb=self.is_cancelled,
        )
        unknown |= found_unknown
        sep = tr(", ", "、")
        count_text = tr("{0} {1}", "{0} {1} 件")
        parts = [count_text.format(c, n) for c, n in fgd_counts.items()]
        if tiles:
            parts.append(tr("{0} tiles ({1})", "タイル {0} 枚（{1}）").format(
                len(tiles), sep.join(count_text.format(c, n) for c, n in bv_counts.items())))
        if absent_codes:
            parts.append(tr("no data: ", "データなし：") + sep.join(
                fgd_type_name(FGD_TYPE_BY_CODE[c]) for c in absent_codes))
        self.log.emit(tr("{0}: {1}", "{0}：{1}").format(mesh, sep.join(parts)))
        if not KEEP_FGD_ZIPS:
            for zip_path in zip_paths_all:
                os.remove(zip_path)
        return True

    def _read_tile(self, ds, x, y):
        # 範囲をタイルの内側に少し縮め、そのタイルだけを読む（地物はタイルの枠で切られている）
        x0, y0, x1, y1 = tile_bounds_3857(x, y, BV_ZOOM)
        inset = 0.001
        result = {"x": x, "y": y, "features": {}}
        for item in self.bv_items:
            features = []
            layer = ds.GetLayerByName(item["source_layer"])
            if layer is not None:
                layer.SetSpatialFilterRect(x0 + inset, y0 + inset, x1 - inset, y1 - inset)
                layer.ResetReading()
                gdal.ErrorReset()
                for feature in layer:
                    geometry = feature.GetGeometryRef()
                    if geometry is None:
                        continue
                    attrs = {}
                    for name, _kind in item["fields"]:
                        attrs[name] = feature.GetField(name) if feature.GetFieldIndex(name) >= 0 else None
                    features.append((attrs, bytes(geometry.ExportToWkb())))
                if gdal.GetLastErrorType() >= gdal.CE_Failure:
                    # 読めなかったタイルを「地物なし」として残さないよう、ここで止める
                    raise RuntimeError(tr("Could not read the tile {0}/{1}/{2}.\n{3}",
                                          "タイル {0}/{1}/{2} を読めませんでした。\n{3}").format(
                        BV_ZOOM, x, y, gdal.GetLastErrorMsg()))
            result["features"][item["source_layer"]] = features
        return result


def _open_bvmap():
    """最適化ベクトルタイルの配信ファイルを開く。返り値は (データセット, 配信データの更新日)"""
    for key, value in (
        ("GDAL_HTTP_USERAGENT", BV_USER_AGENT),
        ("GDAL_HTTP_MAX_RETRY", "3"),
        ("GDAL_HTTP_RETRY_DELAY", "1"),
    ):
        gdal.SetThreadLocalConfigOption(key, value)
    url = "/vsicurl/" + BV_SOURCE_URL
    ds = gdal.OpenEx(url, gdal.OF_VECTOR | gdal.OF_READONLY, open_options=["ZOOM_LEVEL={0}".format(BV_ZOOM)])
    if ds is None:
        raise RuntimeError(tr("Could not open the optimized vector tiles.\n", "最適化ベクトルタイルを開けませんでした。\n")
                           + gdal.GetLastErrorMsg())
    return ds, _source_date(url)


def _source_date(path):
    # 配信ファイルの更新日時（Last-Modified）。取り直すかどうかの目安にする
    try:
        stat = gdal.VSIStatL(path)
    except RuntimeError:
        return ""
    if stat is None or not stat.mtime:
        return ""
    return datetime.fromtimestamp(stat.mtime, timezone.utc).date().isoformat()
