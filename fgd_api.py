# -*- coding: utf-8 -*-
"""基盤地図情報ダウンロードサービスの API と 2次メッシュの計算。

メッシュの計算・ログインの確かめ・ダウンロードは Morizon Next の fgd_fetcher.py（同じ作者）から写したもの。
一覧（/base/latest）はログインなしでも答えるが、ダウンロードはログインが必要（なければ HTTP 428）。
"""

import math

import requests

from .i18n import tr

API_BASE = "https://service.gsi.go.jp/kiban/app/api"
USER_AGENT = "Mozilla/5.0 (fgd_gpkg_builder QGIS Plugin)"
LOGIN_REQUIRED_STATUS = (401, 403, 428)


class LoginRequired(Exception):
    pass


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def latlon_to_mesh2(lat: float, lon: float) -> str:
    """緯度経度から基盤地図情報の2次メッシュコード（6桁、約10km四方）を求める"""
    lat_min = lat * 60
    p = int(lat_min // 40)
    a = lat_min - p * 40
    q = int(a // 5)

    lon_deg = lon - 100
    u = int(lon_deg)
    d = lon_deg - u
    v = int(d // 0.125)

    return f"{p:02d}{u:02d}{q}{v}"


def mesh2_bounds(mesh: str):
    """2次メッシュコードから(lon_min, lat_min, lon_max, lat_max)を求める"""
    p = int(mesh[0:2])
    u = int(mesh[2:4])
    q = int(mesh[4])
    v = int(mesh[5])
    lat_min = (p * 40 + q * 5) / 60
    lat_max = (p * 40 + (q + 1) * 5) / 60
    lon_min = 100 + u + v * 0.125
    lon_max = 100 + u + (v + 1) * 0.125
    return lon_min, lat_min, lon_max, lat_max


def mesh_codes_for_extent(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> list:
    """経緯度の範囲を覆う2次メッシュコードを列挙する。

    2次メッシュの行（緯度 5 分ごと）と列（経度 7.5 分ごと）の番号の範囲から数える。決まった幅で
    範囲を歩く数え方では、右端・上端の列や行が抜けることがあった（2026-11-04）"""
    row0, row1 = int(math.floor(lat_min * 12)), int(math.floor(lat_max * 12))
    col0, col1 = int(math.floor((lon_min - 100) * 8)), int(math.floor((lon_max - 100) * 8))
    codes = []
    for row in range(row0, row1 + 1):
        for col in range(col0, col1 + 1):
            codes.append(f"{row // 8:02d}{col // 8:02d}{row % 8}{col % 8}")
    return sorted(codes)


def check_login(session: requests.Session) -> bool:
    resp = session.get(f"{API_BASE}/isLogin", timeout=30)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return False
    try:
        data = resp.json()
    except ValueError:
        return False
    return bool(data.get("results", {}).get("login"))


def query_latest(session: requests.Session, type_codes: list, mesh_codes: list, progress_cb=None) -> list:
    """種類・メッシュごとの最新データの一覧。要素は {id, type_code, place_code, file_update_date, file_name, ...}

    progress_cb(問い合わせ終えたメッシュの数, 全体の数) は、分けて問い合わせるたびに呼ぶ"""
    results = []
    # URL が長くなりすぎないよう、メッシュを分けて問い合わせる
    for start in range(0, len(mesh_codes), 40):
        params = {"type_codes": ",".join(type_codes), "mesh_codes": ",".join(mesh_codes[start:start + 40])}
        resp = session.get(f"{API_BASE}/base/latest", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result", {}).get("status") != "success":
            raise RuntimeError(data.get("result", {}).get("message") or tr("API error", "APIエラー"))
        results.extend(data.get("results", []))
        if progress_cb:
            progress_cb(min(start + 40, len(mesh_codes)), len(mesh_codes))
    return results


def item_size(item: dict) -> int:
    """一覧に載っている大きさ（KB単位）をバイトで返す。載っていなければ0"""
    try:
        return int(item.get("file_size_kbyte") or 0) * 1024
    except (TypeError, ValueError):
        return 0


def item_date(item: dict) -> str:
    """一覧の日付（2026/07/01）を名前に使う形（20260701）にする"""
    return str(item.get("file_update_date") or "").replace("/", "").replace("-", "")


def download_file(session: requests.Session, file_id: int, output_path: str, cancel_cb=None, chunk_cb=None):
    """chunk_cb(受け取ったバイト数) は受け取るたびに呼ぶ（このファイル内の累計）"""
    url = f"{API_BASE}/download/file/{file_id}"
    with session.get(url, timeout=60, stream=True) as resp:
        if resp.status_code in LOGIN_REQUIRED_STATUS:
            raise LoginRequired()
        resp.raise_for_status()
        if "text/html" in resp.headers.get("content-type", "").lower():
            raise LoginRequired()
        received = 0
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=262144):
                if cancel_cb and cancel_cb():
                    raise InterruptedError()
                if chunk:
                    f.write(chunk)
                    received += len(chunk)
                    if chunk_cb:
                        chunk_cb(received)
    return output_path
