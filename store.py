# -*- coding: utf-8 -*-
"""専用の GeoPackage への書き込みと、レイヤーパネルへの配置。

- 基盤地図情報はレイヤーごとに1つの表（表の名前は RdEdg などの名前）。どのメッシュから来たかを
  mesh_code、データの日付を data_date に持ち、同じメッシュを取り直したときはそのメッシュの分を入れ替える。
- 取得したメッシュは fgd_meshes に、最適化ベクトルタイルのタイルは bv_tiles に枠として残す。
- 座標は JGD2011 の経緯度（EPSG:6668）で持つ（基盤地図情報の元の座標系のまま）。

書き込み（write_ で始まるもの）は別スレッドから呼ぶ。GDAL だけを使い、QGIS のレイヤーには触れない。
"""

import os
import re
import zipfile

from osgeo import gdal, ogr, osr

from .catalog import (
    ADMIN_LAYERS, ANNO_LABEL_BUFFER, ANNO_LABEL_SIZE, ANNO_SYMBOL_NAMES, BV_BY_LAYER, BV_SOURCE_PAGE,
    BV_TABLE_PREFIX, DEFAULT_GROUP_NAMES_ALL, DIMMED_LAYERS, DIMMED_OPACITY, FGD_LAYER_NAMES, FGD_SOURCE_PAGE,
    FGD_STYLES, FIELD_ALIASES, HIDE_BEYOND_SCALE, MAIN_LAYERS, PREVIEW_PROPERTY, ROAD_DARKER, ROAD_LAYERS,
    ROAD_OPACITY, ROAD_WIDTH_MM, SUBGROUP_NAMES_ALL, admin_group_name, bv_attribution, bv_group_name, bv_table,
    bv_title, fgd_attribution, fgd_group_name, fgd_layer_name, rights_text,
)
from . import fgd_api
from .i18n import tr
from .tiles import tile_bounds_lonlat, tile_center_lonlat

STORE_EPSG = 6668
MESH_TABLE = "fgd_meshes"
BV_TILES_TABLE = "bv_tiles"

_OGR_GEOMETRY = {
    "MultiPoint": ogr.wkbMultiPoint,
    "MultiLineString": ogr.wkbMultiLineString,
    "MultiPolygon": ogr.wkbMultiPolygon,
}
_FORCE_MULTI = {
    "MultiPoint": ogr.ForceToMultiPoint,
    "MultiLineString": ogr.ForceToMultiLineString,
    "MultiPolygon": ogr.ForceToMultiPolygon,
}
_OGR_FIELD_TYPES = {"Integer": ogr.OFTInteger, "String": ogr.OFTString, "Real": ogr.OFTReal}


def _store_srs():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(STORE_EPSG)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def open_store(path, update):
    """GeoPackage を開く。update で無ければ作る。読むだけで無いときは None"""
    if not os.path.exists(path):
        if not update:
            return None
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    else:
        ds = ogr.Open(path, 1 if update else 0)
    if ds is None and update:
        raise OSError(tr("Could not open the GeoPackage: {0}", "GeoPackage を開けませんでした：{0}").format(path))
    return ds


def _new_field(name, kind, alias=None):
    field = ogr.FieldDefn(name, kind)
    if alias and hasattr(field, "SetAlternativeName"):
        field.SetAlternativeName(alias)
    return field


def _ensure_table(ds, name, geometry_type, fields):
    layer = ds.GetLayerByName(name)
    if layer is None:
        layer = ds.CreateLayer(name, _store_srs(), geometry_type, options=["FID=fid"])
        if layer is None:
            raise OSError(tr("Could not create the table {0}.", "表 {0} を作れませんでした。").format(name))
        for field_name, kind in fields:
            layer.CreateField(_new_field(field_name, kind, FIELD_ALIASES.get(field_name)))
        # GDAL は表を作るのを後回しにする。取り込みのまとまりの中で作られると、すぐに止めて元に戻したとき
        # 表ごと消え、表の無い GeoPackage は次に開けなくなる。ここで作っておく
        layer.SyncToDisk()
    return layer


# ---- SQL（GDAL の ExecuteSQL は値を別に渡せないので文で組み立てる） ----
#
# 組み立てるのは下の _delete・_select_first・rtree_subset だけ。表・列の名前は _ident で英数字と
# アンダースコアだけのもの（このプラグインが決めた名前）に限り、値は _quote（文字）か int（数）で入れる。
# 外から来た文字がそのまま SQL の文になることはないので、組み立てる3行だけ bandit の B608 を外している。

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name):
    """表・列の名前を SQL に入れる形（"名前"）にする。想定外の文字があれば止める"""
    if not _IDENTIFIER.match(str(name)):
        raise ValueError(tr("Unexpected table or column name: {0}", "想定していない表・項目の名前です：{0}").format(name))
    return '"{0}"'.format(name)


def _quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def _condition(conditions):
    """[(項目, 値)...] を「項目 = 値 AND ...」にする。値は int なら数、ほかは文字として入れる"""
    parts = []
    for column, value in conditions:
        literal = str(int(value)) if isinstance(value, int) else _quote(value)
        parts.append("{0} = {1}".format(_ident(column), literal))
    return " AND ".join(parts)


def _delete(ds, table, conditions):
    statement = "DELETE FROM " + _ident(table) + " WHERE " + _condition(conditions)  # nosec B608
    result = ds.ExecuteSQL(statement)
    if result is not None:
        ds.ReleaseResultSet(result)


def _select_rows(ds, expressions, table, conditions=(), group_by=()):
    """行ごとの値のリストのリスト。expressions は COUNT(*)・MIN(項目)・項目名などこのモジュールで決めた式だけ。
    group_by は項目名（_ident で確かめる）"""
    where = " WHERE " + _condition(conditions) if conditions else ""
    group = " GROUP BY " + ", ".join(_ident(c) for c in group_by) if group_by else ""
    statement = "SELECT " + ", ".join(expressions) + " FROM " + _ident(table) + where + group  # nosec B608
    result = ds.ExecuteSQL(statement)
    rows = []
    if result is not None:
        for feature in result:
            rows.append([feature.GetField(i) for i in range(len(expressions))])
        ds.ReleaseResultSet(result)
    return rows


def _select_first(ds, expressions, table, conditions=()):
    """1行目の値のリスト（集計の結果など）。無ければ None"""
    rows = _select_rows(ds, expressions, table, conditions)
    return rows[0] if rows else None


def rtree_subset(table, rtree_where):
    """GeoPackage の空間索引（R-tree）で絞り込むレイヤーの subset。rtree_where は数だけで作った範囲の条件"""
    rtree = _ident("rtree_" + table + "_geom")
    return '"fid" IN (SELECT "id" FROM ' + rtree + " WHERE " + rtree_where + ")"  # nosec B608


def _polygon_wkt(lon0, lat0, lon1, lat1):
    return "POLYGON(({0} {1},{2} {1},{2} {3},{0} {3},{0} {1}))".format(lon0, lat0, lon1, lat1)


# ---- 読み出し（どのスレッドからでもよい） ----

def stored_bv_tiles(path, source_layer, zoom):
    """{(x, y): source_date}"""
    ds = open_store(path, False)
    if ds is None:
        return {}
    layer = ds.GetLayerByName(BV_TILES_TABLE)
    tiles = {}
    if layer is not None:
        layer.SetAttributeFilter("source_layer = {0} AND tile_z = {1}".format(_quote(source_layer), int(zoom)))
        for feature in layer:
            tiles[(feature.GetField("tile_x"), feature.GetField("tile_y"))] = feature.GetField("source_date") or ""
    ds = None
    return tiles


def record_count(path):
    """基盤地図情報の取得の記録の行数。読み込みの進み具合の分母にする"""
    ds = open_store(path, False)
    if ds is None:
        return 0
    layer = ds.GetLayerByName(MESH_TABLE)
    count = layer.GetFeatureCount() if layer is not None else 0
    ds = None
    return count


def _parse_layer_counts(text):
    """記録の layer_counts（「AdmBdy=87, AdmArea=51」）を {レイヤー: 件数の文字} にする"""
    counts = {}
    for part in (text or "").split(","):
        code, separator, count = part.strip().partition("=")
        if separator:
            counts[code] = count
    return counts


def read_fgd_records(path, progress_cb=None, every=2000):
    """({(mesh_code, type_code): data_date}, {(mesh_code, type_code): 取り込んだレイヤーの集合})。
    1つの種類の ZIP に複数のレイヤーが入っているので、取り込んだかどうかはレイヤーごとに見る。
    progress_cb(読んだ行数) を every 行ごとに呼ぶ"""
    ds = open_store(path, False)
    if ds is None:
        return {}, {}
    layer = ds.GetLayerByName(MESH_TABLE)
    dates = {}
    layers = {}
    if layer is not None:
        for n, feature in enumerate(layer, 1):
            key = (feature.GetField("mesh_code"), feature.GetField("type_code"))
            dates[key] = feature.GetField("data_date")
            layers[key] = set(_parse_layer_counts(feature.GetField("layer_counts")))
            if progress_cb and n % every == 0:
                progress_cb(n)
    ds = None
    return dates, layers


def tile_mesh(x, y, zoom):
    """タイルの中心が入る2次メッシュ（隣のメッシュと重ねて数えないよう、タイルは中心で1つのメッシュに数える）"""
    lon, lat = tile_center_lonlat(x, y, zoom)
    return fgd_api.latlon_to_mesh2(lat, lon)


def missing_tile_meshes(path):
    """最適化ベクトルタイルの取得の記録のうち、メッシュ番号（mesh_code）が入っていない行の数。
    前の版で書いた記録には無い（項目ごと無いときは全部の行）"""
    ds = open_store(path, False)
    if ds is None:
        return 0
    layer = ds.GetLayerByName(BV_TILES_TABLE)
    count = 0
    if layer is not None:
        if layer.GetLayerDefn().GetFieldIndex("mesh_code") < 0:
            count = layer.GetFeatureCount()
        else:
            layer.SetAttributeFilter("mesh_code IS NULL")
            count = layer.GetFeatureCount()
    ds = None
    return count


def fill_tile_meshes(path, zoom):
    """前の版で書いた最適化ベクトルタイルの取得の記録に、メッシュ番号を足す（一度だけ。以後は書き込むときに入る）。

    2次メッシュの番号は「行（緯度）の部分＝タイルの y だけで決まる」と「列（経度）の部分＝タイルの x だけで
    決まる」に分かれるので、x・y の値ごとの対応を作り、UPDATE 1本で埋める（1行ずつ書き戻すと遅かった）"""
    ds = open_store(path, True)
    layer = ds.GetLayerByName(BV_TILES_TABLE)
    if layer is None:
        ds = None
        return
    if layer.GetLayerDefn().GetFieldIndex("mesh_code") < 0:
        layer.CreateField(_new_field("mesh_code", ogr.OFTString))
    xs = [r[0] for r in _select_rows(ds, ["tile_x"], BV_TILES_TABLE, [("tile_z", int(zoom))], group_by=["tile_x"])]
    ys = [r[0] for r in _select_rows(ds, ["tile_y"], BV_TILES_TABLE, [("tile_z", int(zoom))], group_by=["tile_y"])]
    if not xs or not ys:
        ds = None
        return
    # メッシュ番号 PPUUQV：PP・Q は緯度（y）、UU・V は経度（x）から決まる。もう一方は何でもよいので代わりの値で求める
    x_code = {x: tile_mesh(x, ys[0], zoom) for x in xs}
    y_code = {y: tile_mesh(xs[0], y, zoom) for y in ys}
    pp = _case("tile_y", {y: code[0:2] for y, code in y_code.items()})
    q = _case("tile_y", {y: code[4] for y, code in y_code.items()})
    uu = _case("tile_x", {x: code[2:4] for x, code in x_code.items()})
    v = _case("tile_x", {x: code[5] for x, code in x_code.items()})
    _update_mesh_codes(ds, " || ".join((pp, uu, q, v)), int(zoom))
    ds = None


def _ensure_index(ds, table, columns):
    """表に索引が無ければ作る（あれば何もしない）。表が無いときも何もしない。取り込みのまとまりの外で呼ぶ"""
    if ds.GetLayerByName(table) is None:
        return
    name = _ident("idx_{0}_{1}".format(table, "_".join(columns)))
    statement = "CREATE INDEX IF NOT EXISTS " + name + " ON " + _ident(table) + " (" + ", ".join(
        _ident(c) for c in columns) + ")"
    result = ds.ExecuteSQL(statement)
    if result is not None:
        ds.ReleaseResultSet(result)


def _case(column, values):
    """CASE 項目 WHEN 数 THEN '文字' ... END。値はこのモジュールで求めた数字の文字だけ"""
    whens = " ".join("WHEN {0} THEN {1}".format(int(k), _quote(v)) for k, v in values.items())
    return "(CASE " + _ident(column) + " " + whens + " END)"


def _update_mesh_codes(ds, expression, zoom):
    # expression は _case で作った式だけ（表・項目の名前は _ident、値は int と _quote で入れてある）
    statement = ("UPDATE " + _ident(BV_TILES_TABLE) + " SET " + _ident("mesh_code") + " = " + expression  # nosec B608
                 + " WHERE " + _ident("mesh_code") + " IS NULL AND " + _condition([("tile_z", zoom)]))
    result = ds.ExecuteSQL(statement)
    if result is not None:
        ds.ReleaseResultSet(result)


def bv_mesh_counts(path, zoom):
    """{source_layer: {メッシュ: タイル数}}。最適化ベクトルタイルの項目・メッシュごとの取得済みタイルの数。
    数えるのは GeoPackage（SQLite）に任せ、返ってくるのは項目×メッシュの行だけにする"""
    ds = open_store(path, False)
    if ds is None or ds.GetLayerByName(BV_TILES_TABLE) is None:
        return {}
    rows = _select_rows(ds, ["source_layer", "mesh_code", "COUNT(*)"], BV_TILES_TABLE,
                        [("tile_z", int(zoom))], group_by=["source_layer", "mesh_code"])
    ds = None
    counts = {}
    for name, mesh, count in rows:
        if mesh:
            counts.setdefault(name, {})[mesh] = count
    return counts


def bv_date_range(path, source_layer):
    """最適化ベクトルタイルの配信データの日付（最も古い, 最も新しい）を 20260917 の形で返す"""
    ds = open_store(path, False)
    if ds is None or ds.GetLayerByName(BV_TILES_TABLE) is None:
        return "", ""
    values = _select_first(ds, ["MIN(source_date)", "MAX(source_date)"], BV_TILES_TABLE,
                           [("source_layer", source_layer)])
    dates = tuple((v or "").replace("-", "") for v in values) if values else ("", "")
    ds = None
    return dates


def table_summary(path, table, dated):
    """(件数, 最も古い日付, 最も新しい日付)。表が無ければ None"""
    ds = open_store(path, False)
    if ds is None:
        return None
    if ds.GetLayerByName(table) is None:
        ds = None
        return None
    expressions = ["COUNT(*)", "MIN(data_date)", "MAX(data_date)"] if dated else ["COUNT(*)"]
    values = _select_first(ds, expressions, table)
    summary = None
    if values is not None:
        summary = (values[0] or 0, values[1] or "", values[2] or "") if dated else (values[0] or 0, "", "")
    ds = None
    return summary


# ---- 基盤地図情報の書き込み ----

# ZIP の中のファイル名の綴りが一覧の名前と違うもの（実際の ZIP の記録で確認、2026-11-03）
_MEMBER_CODE_ALIASES = {"AdmBdry": "AdmBdy", "CommBdry": "CommBdy"}


def _member_code(member):
    # FG-GML-523807-RdEdg-20260701-0001.xml
    parts = os.path.basename(member)[:-4].split("-")
    code = parts[3] if len(parts) >= 5 else ""
    return _MEMBER_CODE_ALIASES.get(code, code)


def _axis_state(ds, bounds):
    lon0, lat0, lon1, lat1 = bounds
    tolerance = 0.05
    for i in range(ds.GetLayerCount()):
        layer = ds.GetLayer(i)
        layer.ResetReading()
        for feature in layer:
            geometry = feature.GetGeometryRef()
            if geometry is None or geometry.IsEmpty():
                continue
            min_x, max_x, min_y, max_y = geometry.GetEnvelope()
            layer.ResetReading()
            inside = (lon0 - tolerance <= min_x and max_x <= lon1 + tolerance
                      and lat0 - tolerance <= min_y and max_y <= lat1 + tolerance)
            return "ok" if inside else "bad"
    return "empty"


def _open_gml(src, bounds):
    """経度・緯度の順に読める開き方で開く。

    QGIS の中の GDAL では基盤地図情報の GML の緯度と経度が入れ替わって読まれることがあった
    （Morizon Next、2026-10-05）。メッシュの範囲に収まるかで確かめ、収まる開き方を使う"""
    for swap in ("YES", "NO", "AUTO"):
        ds = gdal.OpenEx(src, gdal.OF_VECTOR | gdal.OF_READONLY, open_options=["SWAP_COORDINATES=" + swap])
        if ds is None:
            continue
        if _axis_state(ds, bounds) in ("ok", "empty"):
            return ds
        ds = None
    raise RuntimeError(tr("Could not determine the coordinate axis order: {0}",
                          "座標の並びを判定できませんでした：{0}").format(os.path.basename(src)))


def _target_field_name(name):
    # GeoPackage の fid（行の番号）と重ならないよう、基盤地図情報の fid（地物ID）は名前を変える
    return "src_fid" if name.lower() == "fid" else name


def _ensure_fgd_table(out, code, src_layer):
    layer = out.GetLayerByName(code)
    if layer is None:
        geometry_type = ogr.GT_GetLinear(ogr.GT_Flatten(src_layer.GetGeomType()))
        if geometry_type == ogr.wkbNone:
            geometry_type = ogr.wkbUnknown
        layer = _ensure_table(out, code, geometry_type, [("mesh_code", ogr.OFTString), ("data_date", ogr.OFTString)])
    defn = layer.GetLayerDefn()
    existing = {defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())}
    src_defn = src_layer.GetLayerDefn()
    for i in range(src_defn.GetFieldCount()):
        src_field = src_defn.GetFieldDefn(i)
        name = _target_field_name(src_field.GetName())
        if name in existing:
            continue
        field = _new_field(name, src_field.GetType(), FIELD_ALIASES.get(name))
        field.SetSubType(src_field.GetSubType())
        layer.CreateField(field)
        existing.add(name)
    return out.GetLayerByName(code)


def _open_fgd_sources(zip_paths, layer_codes, bounds):
    """1つの種類の ZIP（分割されていれば複数）の中の GML を開く。返り値は ([(レイヤー, データセット)], 一覧に無い名前)"""
    sources = []
    unknown = set()
    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.namelist()
        for member in members:
            base = os.path.basename(member)
            if not (base.startswith("FG-GML-") and base.lower().endswith(".xml")):
                continue
            code = _member_code(base)
            if code not in layer_codes:
                if code not in FGD_LAYER_NAMES:
                    unknown.add(code)
                continue
            sources.append((code, _open_gml("/vsizip/{0}/{1}".format(zip_path, member), bounds)))
    return sources, unknown


def _ensure_mesh_table(out):
    return _ensure_table(out, MESH_TABLE, ogr.wkbPolygon, [
        ("mesh_code", ogr.OFTString), ("type_code", ogr.OFTString), ("type_name", ogr.OFTString),
        ("data_date", ogr.OFTString), ("file_names", ogr.OFTString), ("fetched_at", ogr.OFTString),
        ("layer_counts", ogr.OFTString),
    ])


def _merged_layer_counts(out, mesh, type_code, data_date, counts):
    """記録に残す「レイヤー=件数」。同じ日付のデータなら、今回取り込まなかったレイヤーの記録も残す。
    日付が変わったときは残さない（残すと、古いデータのレイヤーを最新として扱ってしまう）"""
    merged = {code: str(count) for code, count in counts.items()}
    previous = _select_first(out, ["data_date", "layer_counts"], MESH_TABLE,
                             [("mesh_code", mesh), ("type_code", type_code)])
    if previous is not None and previous[0] == data_date:
        for code, count in _parse_layer_counts(previous[1]).items():
            merged.setdefault(code, count)
    return ", ".join("{0}={1}".format(code, count) for code, count in merged.items())


def _write_mesh_record(out, mesh, type_info, data_date, file_names, fetched_at, bounds, layer_counts):
    _delete(out, MESH_TABLE, [("mesh_code", mesh), ("type_code", type_info["code"])])
    mesh_layer = out.GetLayerByName(MESH_TABLE)
    record = ogr.Feature(mesh_layer.GetLayerDefn())
    record.SetGeometry(ogr.CreateGeometryFromWkt(_polygon_wkt(*bounds)))
    record.SetField("mesh_code", mesh)
    record.SetField("type_code", type_info["code"])
    record.SetField("type_name", type_info["name"])
    record.SetField("data_date", data_date)
    record.SetField("file_names", ", ".join(file_names))
    record.SetField("fetched_at", fetched_at)
    record.SetField("layer_counts", layer_counts)
    mesh_layer.CreateFeature(record)


def _write_fgd_type(out, mesh, layer_codes, sources, data_date, cancel_cb):
    """1つの種類の地物を書き込む（まとまりの中で呼ぶ）。そのメッシュの前の地物は消して入れ替える"""
    counts = {code: 0 for code in layer_codes}
    for code in layer_codes:
        if out.GetLayerByName(code) is not None:
            _delete(out, code, [("mesh_code", mesh)])
    for code, ds in sources:
        out_layer = out.GetLayerByName(code)
        if out_layer is None:
            # GDAL が地物を1件も読めなかったファイル（表を作るもとが無い）は飛ばす
            continue
        out_defn = out_layer.GetLayerDefn()
        mesh_index = out_defn.GetFieldIndex("mesh_code")
        date_index = out_defn.GetFieldIndex("data_date")
        for i in range(ds.GetLayerCount()):
            src_layer = ds.GetLayer(i)
            src_defn = src_layer.GetLayerDefn()
            field_map = [
                out_defn.GetFieldIndex(_target_field_name(src_defn.GetFieldDefn(j).GetName()))
                for j in range(src_defn.GetFieldCount())
            ]
            src_layer.ResetReading()
            for n, feature in enumerate(src_layer):
                if n % 2000 == 0 and cancel_cb is not None and cancel_cb():
                    raise InterruptedError()
                new = ogr.Feature(out_defn)
                new.SetFromWithMap(feature, 1, field_map)
                geometry = feature.GetGeometryRef()
                if geometry is not None:
                    if geometry.HasCurveGeometry():
                        geometry = geometry.GetLinearGeometry()
                    new.SetGeometry(geometry)
                new.SetField(mesh_index, mesh)
                new.SetField(date_index, data_date)
                out_layer.CreateFeature(new)
                counts[code] += 1
    return counts


def _ensure_bv_tables(out, items):
    layers = {}
    for item in items:
        fields = [(name, _OGR_FIELD_TYPES[kind]) for name, kind in item["fields"]] + [
            ("種別", ogr.OFTString), ("tile_z", ogr.OFTInteger), ("tile_x", ogr.OFTInteger),
            ("tile_y", ogr.OFTInteger), ("fetched_at", ogr.OFTString),
        ]
        layer = _ensure_table(out, bv_table(item), _OGR_GEOMETRY[item["geometry"]], fields)
        # 前の版で作った表に無い項目は足す
        defn = layer.GetLayerDefn()
        for name, kind in fields:
            if defn.GetFieldIndex(name) < 0:
                layer.CreateField(_new_field(name, kind))
        layers[item["source_layer"]] = out.GetLayerByName(bv_table(item))
    tile_fields = [
        ("source_layer", ogr.OFTString), ("tile_z", ogr.OFTInteger), ("tile_x", ogr.OFTInteger),
        ("tile_y", ogr.OFTInteger), ("feature_count", ogr.OFTInteger),
        ("fetched_at", ogr.OFTString), ("source_date", ogr.OFTString),
        # タイルの中心が入る2次メッシュ。読むときにメッシュごとの数を SQLite で数えるために持つ
        ("mesh_code", ogr.OFTString),
    ]
    tiles_layer = _ensure_table(out, BV_TILES_TABLE, ogr.wkbPolygon, tile_fields)
    if tiles_layer.GetLayerDefn().GetFieldIndex("mesh_code") < 0:
        # 前の版で作った表には無いので足す（前の行は、読むとき fill_tile_meshes で一度だけ埋める）
        tiles_layer.CreateField(_new_field("mesh_code", ogr.OFTString))
    return layers


def _write_bv_tiles(out, layers, items, zoom, results, fetched_at, source_date, cancel_cb):
    """読んだタイル（3857 の座標）を経緯度にして書き込む（まとまりの中で呼ぶ）。同じタイルの前の地物は入れ替える"""
    src_srs = osr.SpatialReference()
    src_srs.ImportFromEPSG(3857)
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_lonlat = osr.CoordinateTransformation(src_srs, _store_srs())
    tiles_layer = out.GetLayerByName(BV_TILES_TABLE)
    counts = {item["source_layer"]: 0 for item in items}
    for result in results:
        if cancel_cb is not None and cancel_cb():
            raise InterruptedError()
        x, y = result["x"], result["y"]
        tile_key = [("tile_z", int(zoom)), ("tile_x", int(x)), ("tile_y", int(y))]
        for item in items:
            name = item["source_layer"]
            _delete(out, bv_table(item), tile_key)
            _delete(out, BV_TILES_TABLE, [("source_layer", name)] + tile_key)
            out_layer = layers[name]
            defn = out_layer.GetLayerDefn()
            rows = result["features"].get(name, [])
            force_multi = _FORCE_MULTI[item["geometry"]]
            for attrs, wkb in rows:
                geometry = ogr.CreateGeometryFromWkb(wkb)
                geometry.Transform(to_lonlat)
                feature = ogr.Feature(defn)
                feature.SetGeometry(force_multi(geometry))
                for field_name, _kind in item["fields"]:
                    value = attrs.get(field_name)
                    if value is not None:
                        feature.SetField(field_name, value)
                feature.SetField("種別", item["codes"].get(attrs.get("vt_code"), ""))
                feature.SetField("tile_z", int(zoom))
                feature.SetField("tile_x", int(x))
                feature.SetField("tile_y", int(y))
                feature.SetField("fetched_at", fetched_at)
                out_layer.CreateFeature(feature)
            counts[name] += len(rows)
            tile = ogr.Feature(tiles_layer.GetLayerDefn())
            tile.SetGeometry(ogr.CreateGeometryFromWkt(_polygon_wkt(*tile_bounds_lonlat(x, y, zoom))))
            tile.SetField("source_layer", name)
            tile.SetField("tile_z", int(zoom))
            tile.SetField("tile_x", int(x))
            tile.SetField("tile_y", int(y))
            tile.SetField("feature_count", len(rows))
            tile.SetField("fetched_at", fetched_at)
            tile.SetField("source_date", source_date)
            tile.SetField("mesh_code", tile_mesh(x, y, zoom))
            tiles_layer.CreateFeature(tile)
    return counts


def write_block(path, mesh, fgd_entries, absent_types, bv_items, zoom, bv_results, fetched_at, source_date,
                cancel_cb=None):
    """1つの2次メッシュ（ブロック）の分をまとめて書き込む。すべて書けたときだけ残し、途中で止まったときや
    失敗したときは、このメッシュは取り込む前の状態のまま（中途半端な範囲を作らない）。

    fgd_entries: [{"type_info", "layer_codes", "zip_paths", "data_date", "file_names"}]
    absent_types: 一覧にデータが無かった基盤地図情報の種類（type_info）。「データなし」として記録する
    返り値は ({基盤地図情報のレイヤー: 件数}, {最適化ベクトルタイルの項目: 件数}, 一覧に無かったレイヤーの名前)"""
    bounds = fgd_api.mesh2_bounds(mesh)
    opened = []
    unknown = set()
    for entry in fgd_entries:
        sources, found = _open_fgd_sources(entry["zip_paths"], entry["layer_codes"], bounds)
        opened.append((entry, sources))
        unknown |= found

    out = open_store(path, True)
    try:
        # 表と項目を先にそろえる（作るのは取り込みのまとまりの外で）
        for _entry, sources in opened:
            for code, ds in sources:
                for i in range(ds.GetLayerCount()):
                    _ensure_fgd_table(out, code, ds.GetLayer(i))
        _ensure_mesh_table(out)
        bv_layers = _ensure_bv_tables(out, bv_items) if bv_items and bv_results else {}
        # 前の分を消す条件の項目に索引を作る（無いと消すたびに表全体を見ていて、取り込んだ量が増えるほど遅くなった）
        _ensure_index(out, MESH_TABLE, ["mesh_code", "type_code"])
        for entry in fgd_entries:
            for code in entry["layer_codes"]:
                _ensure_index(out, code, ["mesh_code"])
        if bv_layers:
            for item in bv_items:
                _ensure_index(out, bv_table(item), ["tile_z", "tile_x", "tile_y"])
            _ensure_index(out, BV_TILES_TABLE, ["source_layer", "tile_z", "tile_x", "tile_y"])

        fgd_counts = {}
        bv_counts = {}
        out.StartTransaction()
        try:
            for entry, sources in opened:
                counts = _write_fgd_type(out, mesh, entry["layer_codes"], sources, entry["data_date"], cancel_cb)
                layer_counts = _merged_layer_counts(out, mesh, entry["type_info"]["code"], entry["data_date"], counts)
                _write_mesh_record(
                    out, mesh, entry["type_info"], entry["data_date"], entry["file_names"], fetched_at, bounds,
                    layer_counts)
                fgd_counts.update(counts)
            for type_info in absent_types:
                # データの無い種類（海だけのメッシュの建物など）。data_date を空にして「確かめた」ことを残す
                _write_mesh_record(out, mesh, type_info, "", [], fetched_at, bounds, "")
            if bv_layers:
                bv_counts = _write_bv_tiles(
                    out, bv_layers, bv_items, zoom, bv_results, fetched_at, source_date, cancel_cb)
            out.CommitTransaction()
        except BaseException:
            out.RollbackTransaction()
            raise
    finally:
        opened = None
        out = None
    return fgd_counts, bv_counts, unknown


# ---- レイヤーパネルへの配置（メインスレッド） ----

def _same_table(layer, path, table):
    from qgis.core import QgsProviderRegistry
    if layer.providerType() != "ogr":
        return False
    parts = QgsProviderRegistry.instance().decodeUri("ogr", layer.source())
    if not parts.get("path") or parts.get("layerName") != table:
        return False
    return os.path.realpath(parts["path"]) == os.path.realpath(path)


def project_layer(path, table):
    from qgis.core import QgsProject, QgsVectorLayer
    for layer in QgsProject.instance().mapLayers().values():
        if isinstance(layer, QgsVectorLayer) and _same_table(layer, path, table):
            return layer
    return None


def refresh_project_layers(path):
    """書き込んだあと、プロジェクトに入っている同じ GeoPackage のレイヤーを読み直す"""
    from qgis.core import QgsProject, QgsProviderRegistry, QgsVectorLayer
    real = os.path.realpath(path)
    for layer in QgsProject.instance().mapLayers().values():
        if not isinstance(layer, QgsVectorLayer) or layer.providerType() != "ogr":
            continue
        parts = QgsProviderRegistry.instance().decodeUri("ogr", layer.source())
        if parts.get("path") and os.path.realpath(parts["path"]) == real:
            layer.dataProvider().reloadData()
            layer.updateExtents()
            layer.triggerRepaint()


def _date_label(first, last):
    if not first:
        return ""
    return first if first == last else tr("{0} to {1}", "{0}～{1}").format(first, last)


def _layer_name(title, first, last):
    label = _date_label(first, last)
    return "{0}-{1}".format(title, label) if label else title


def _find_child_group(parent, name):
    from qgis.core import QgsLayerTreeGroup
    for child in parent.children():
        if isinstance(child, QgsLayerTreeGroup) and child.name() == name:
            return child
    return None


def _child_group(parent, name, index=None):
    group = _find_child_group(parent, name)
    if group is None:
        group = parent.insertGroup(index, name) if index is not None else parent.addGroup(name)
    return group


def _prune_empty_groups(parent, names):
    """names のグループのうち、中が空のもの（中も同じ名前のグループだけで空のもの）を外す。
    ほかのグループの中にあるものも探す。ほかのグループ自体は外さない"""
    from qgis.core import QgsLayerTreeGroup
    for child in list(parent.children()):
        if isinstance(child, QgsLayerTreeGroup):
            _prune_empty_groups(child, names)
            if child.name() in names and not child.children():
                parent.removeChildNode(child)


def _move_child(parent, node, index):
    """node を parent の中の index（-1 は最後）へ動かす"""
    if node is None:
        return
    children = parent.children()
    current = children.index(node)
    target = len(children) - 1 if index == -1 else index
    if current == target:
        return
    clone = node.clone()
    parent.insertChildNode(index if index != -1 else len(children), clone)
    parent.removeChildNode(node)


def _is_network_layer(layer):
    if layer.customProperty(PREVIEW_PROPERTY):
        # 取得画面を開いている間だけ置くプレビュー地図は数えない
        return False
    source = (layer.source() or "").lower()
    return "http://" in source or "https://" in source


def _insert_main_group(root, name):
    """グループを最上位に、レイヤーパネルでいちばん上にあるネットワーク経由のレイヤーの直上に作る。
    そのレイヤーがグループの中にあれば、最上位にあるそのグループの直上。無ければいちばん上。
    ほかのグループの中には作らない"""
    target = next((node for node in root.findLayers()
                   if node.layer() is not None and _is_network_layer(node.layer())), None)
    if target is None:
        return root.insertGroup(0, name)
    # root の子になるまで親をたどる
    while target.parent() is not None and target.parent().parent() is not None:
        target = target.parent()
    return root.insertGroup(root.children().index(target), name)


def place_layers(path, group_name, fgd_codes, bv_items, meshes):
    """保存先にある表をレイヤーとしてグループに置く。

    グループの形（ユーザーが作った「GSI・基盤地図情報」の構成）：
        group_name（初期値 GSI・基盤地図情報）
          ├ 基盤地図情報・行政データ
          ├ 最適化ベクトルタイル
          └ 基盤地図情報
    meshes を渡したときは、その2次メッシュ（可視範囲をカバーするもの）の分だけを見せる。GeoPackage の
    ほかの範囲のデータは残る。None のときは絞り込まず、取得済みの範囲をすべて見せる。
    返り値は置いたレイヤーの名前のリスト"""
    from qgis.core import QgsLayerMetadata, QgsProject, QgsVectorLayer

    project = QgsProject.instance()
    root = project.layerTreeRoot()
    placed = []
    # 最上位だけを見る（findGroup は奥まで探すので、ほかのグループの中の同名グループを拾ってしまう）
    top_group = _find_child_group(root, group_name)

    def ensure_top_group():
        nonlocal top_group
        if top_group is None:
            top_group = _insert_main_group(root, group_name)
        return top_group

    def subgroup_getter(name):
        return lambda: _child_group(ensure_top_group(), name)

    # 読み込みは追加でなく、プラグインで選んだ構成への組み直し：この GeoPackage から置いた地物のレイヤーを
    # いったんすべて外し、今選んでいるものだけを決まった並びで置き直す（GeoPackage のデータは消さない）
    managed = set(FGD_LAYER_NAMES) | {BV_TABLE_PREFIX + layer for layer in BV_BY_LAYER}
    for layer in list(project.mapLayers().values()):
        if isinstance(layer, QgsVectorLayer) and any(_same_table(layer, path, table) for table in managed):
            project.removeMapLayer(layer.id())

    if meshes is None:
        fgd_subset = ""
    else:
        fgd_subset = '"mesh_code" IN ({0})'.format(", ".join(_quote(m) for m in meshes)) if meshes else "1 = 0"
        # 最適化ベクトルタイルはタイル単位なのでメッシュの枠とはそろわない。GeoPackage の空間索引（R-tree）で
        # 2次メッシュの範囲に掛かる地物だけにする
        mesh_boxes = [fgd_api.mesh2_bounds(m) for m in meshes]
        rtree_where = " OR ".join(
            '("maxx" >= {0!r} AND "minx" <= {2!r} AND "maxy" >= {1!r} AND "miny" <= {3!r})'.format(*box)
            for box in mesh_boxes) or "0"

    def bv_subset(table):
        if meshes is None:
            return ""
        return rtree_subset(table, rtree_where)

    def place(table, name, group_getter, style, rights):
        summary = table_summary(path, table, dated=not table.startswith("bv_"))
        if summary is None or summary[0] == 0:
            return
        # 絞り込みは URI に入れる（作ったあとに setSubsetString すると、同じ GeoPackage の2つ目以降の
        # レイヤーが開けなくなることがあった：QGIS 3.44 / GDAL 3.11）
        subset = bv_subset(table) if table.startswith(BV_TABLE_PREFIX) else fgd_subset
        uri = "{0}|layername={1}".format(path, table) + ("|subset=" + subset if subset else "")
        layer = QgsVectorLayer(uri, name, "ogr")
        if not layer.isValid():
            return
        style(layer)
        metadata = QgsLayerMetadata(layer.metadata())
        metadata.setRights([rights])
        layer.setMetadata(metadata)
        project.addMapLayer(layer, False)
        group_getter().addLayer(layer)
        placed.append(name)

    fgd_rights = rights_text(fgd_attribution(), FGD_SOURCE_PAGE)
    for codes, getter in (
        ([c for c in ADMIN_LAYERS if c in fgd_codes], subgroup_getter(admin_group_name())),
        ([c for c in MAIN_LAYERS if c in fgd_codes], subgroup_getter(fgd_group_name())),
    ):
        for code in codes:
            summary = table_summary(path, code, dated=True)
            if summary is None or summary[0] == 0:
                continue
            # 名前は「種別-データの日付」
            name = _layer_name(fgd_layer_name(code), summary[1], summary[2])
            place(code, name, getter, lambda layer, c=code: _apply_fgd_style(layer, c), fgd_rights)
    # 一覧に載せていない基盤地図情報のレイヤー（ZIP から見つかったもの）は置かない

    bv_rights = rights_text(bv_attribution(), BV_SOURCE_PAGE)
    for item in bv_items:
        # 最適化ベクトルタイルの日付は、配信ファイルの更新日（データの時点そのものではない）
        name = _layer_name(bv_title(item), *bv_date_range(path, item["source_layer"]))
        place(
            bv_table(item), name, subgroup_getter(bv_group_name()),
            lambda layer, i=item: _apply_bv_style(layer, i), bv_rights,
        )

    # 組み直しで空になった小グループ・グループを片づける。言語を切り替える前の名前や前の版の名前のもの、
    # 前の版で基盤地図情報のグループと同じ階層に作った「最適化ベクトルタイル」も含む
    _prune_empty_groups(root, SUBGROUP_NAMES_ALL | DEFAULT_GROUP_NAMES_ALL | {group_name})
    top_group = _find_child_group(root, group_name)
    if top_group is not None:
        position = 0
        for name in (admin_group_name(), bv_group_name(), fgd_group_name()):
            child = _find_child_group(top_group, name)
            if child is not None:
                _move_child(top_group, child, position)
                position += 1

    # レイヤーを足すとグループが開くので、最後に中の小グループ・レイヤーを閉じる。
    # いちばん上のグループは開いておき、3つの小グループが見えるようにする
    if top_group is not None:
        nodes = list(top_group.children())
        while nodes:
            node = nodes.pop()
            node.setExpanded(False)
            nodes.extend(node.children())
        top_group.setExpanded(True)
    return placed


STYLE_DIR = os.path.join(os.path.dirname(__file__), "styles")


def _load_style_file(layer, name):
    """styles/<name>.qml があれば当てる（記号・ラベル・描画の設定）。当てられたら True"""
    from qgis.core import QgsMapLayer

    qml = os.path.join(STYLE_DIR, name + ".qml")
    if not os.path.exists(qml):
        return False
    categories = (QgsMapLayer.StyleCategory.Symbology | QgsMapLayer.StyleCategory.Labeling
                  | QgsMapLayer.StyleCategory.Rendering)
    _message, ok = layer.loadNamedStyle(qml, categories)
    return bool(ok)


def _apply_fgd_style(layer, code):
    _apply_fgd_symbols(layer, code)
    _apply_opacity(layer, code)


def _apply_bv_style(layer, item):
    _apply_bv_symbols(layer, item)
    _apply_opacity(layer, item["source_layer"])


def _apply_opacity(layer, name):
    # QML に描画の設定があっても、道路関係と等高線はこちらの不透明度にそろえる
    if name in DIMMED_LAYERS:
        layer.setOpacity(DIMMED_OPACITY)
    if name in ROAD_LAYERS:
        layer.setOpacity(ROAD_OPACITY)
        _adjust_lines(layer, ROAD_DARKER, ROAD_WIDTH_MM[name])
    if name in HIDE_BEYOND_SCALE:
        # 縮尺による表示：最小縮尺（いちばんズームアウトした側）を超えたら描かない
        layer.setMinimumScale(HIDE_BEYOND_SCALE[name])
        layer.setMaximumScale(0)
        layer.setScaleBasedVisibility(True)


def _adjust_lines(layer, factor, width_mm):
    # 記号の線だけ、色を濃くして太さをそろえる（ラベルの文字や縁取りはそのまま）
    from qgis.core import Qgis, QgsLineSymbolLayer, QgsRenderContext

    renderer = layer.renderer()
    if renderer is None:
        return
    for symbol in renderer.symbols(QgsRenderContext()):
        for symbol_layer in symbol.symbolLayers():
            if isinstance(symbol_layer, QgsLineSymbolLayer):
                symbol_layer.setColor(symbol_layer.color().darker(factor))
                symbol_layer.setWidth(width_mm)
                symbol_layer.setWidthUnit(Qgis.RenderUnit.Millimeters)


def _apply_fgd_symbols(layer, code):
    from qgis.core import QgsSingleSymbolRenderer

    # これまで手で整えていた「基盤地図情報（伊豆）」の表示（styles/ に書き出したもの）があれば使う。
    # 書き出すとき、色分けやラベルの項目名は日本語名からこの表の名前（標高→alti、名称・点名称→name）に置き換えた
    if _load_style_file(layer, code):
        return

    color, size, fill = FGD_STYLES.get(code, ("#666666", 0.26, None))
    symbol = _make_symbol(layer.geometryType(), color, size, fill)
    if symbol is not None:
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def _apply_bv_symbols(layer, item):
    from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSingleSymbolRenderer

    # QGIS で整えた表示（styles/bv_<レイヤー名>.qml に書き出したもの）があれば使う
    if _load_style_file(layer, bv_table(item)):
        return
    color, size, fill = item["style"]
    if item["source_layer"] == "Anno":
        _apply_anno_labels(layer)
    if not item["code_colors"]:
        symbol = _make_symbol(layer.geometryType(), color, size, fill)
        if symbol is not None:
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        return
    categories = []
    for code, code_color in item["code_colors"].items():
        symbol = _make_symbol(layer.geometryType(), code_color, size, fill)
        name = item["codes"].get(code, "")
        categories.append(QgsRendererCategory(code, symbol, "{0}（{1}）".format(name, code)))
    layer.setRenderer(QgsCategorizedSymbolRenderer("vt_code", categories))


def _anno_label_expression():
    # 文字（vt_text）があれば文字、無ければコードの名前。対応はラベルの式の中だけに持ち、データは変えない
    pairs = ", ".join("'{0}', '{1}'".format(code, name) for code, name in sorted(ANNO_SYMBOL_NAMES.items()))
    return ('coalesce(nullif("vt_text", \'\'), map_get(map({0}), to_string("vt_code")))'.format(pairs))


def _apply_anno_labels(layer):
    from qgis.core import (
        Qgis, QgsPalLayerSettings, QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling,
    )
    from qgis.PyQt.QtGui import QColor

    text_format = QgsTextFormat()
    text_format.setSize(ANNO_LABEL_SIZE)
    text_format.setSizeUnit(Qgis.RenderUnit.Points)
    text_format.setColor(QColor("#222222"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(ANNO_LABEL_BUFFER)
    buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
    buffer.setColor(QColor("white"))
    text_format.setBuffer(buffer)

    settings = QgsPalLayerSettings()
    settings.fieldName = _anno_label_expression()
    settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.AroundPoint
    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _make_symbol(geometry_type, color, size, fill):
    from qgis.core import Qgis, QgsSymbol
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor

    symbol = QgsSymbol.defaultSymbol(geometry_type)
    if symbol is None:
        return None
    if geometry_type == Qgis.GeometryType.Point:
        symbol.setColor(QColor(color))
        symbol.setSize(size)
    elif geometry_type == Qgis.GeometryType.Line:
        symbol.setColor(QColor(color))
        symbol.setWidth(size)
    elif geometry_type == Qgis.GeometryType.Polygon:
        fill_layer = symbol.symbolLayer(0)
        if fill:
            symbol.setColor(QColor(fill))
        else:
            fill_layer.setBrushStyle(Qt.BrushStyle.NoBrush)
        fill_layer.setStrokeColor(QColor(color))
        fill_layer.setStrokeWidth(size)
    return symbol
