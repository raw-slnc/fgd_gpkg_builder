# -*- coding: utf-8 -*-
"""ウェブメルカトルのタイル番号の計算。"""

import math

HALF_WORLD = math.pi * 6378137.0
MAX_LAT = 85.0511287798


def _tile_x(lon, n):
    return min(n - 1, max(0, int((lon + 180.0) / 360.0 * n)))


def _tile_y(lat, n):
    lat = math.radians(max(-MAX_LAT, min(MAX_LAT, lat)))
    y = (1.0 - math.log(math.tan(lat) + 1.0 / math.cos(lat)) / math.pi) / 2.0 * n
    return min(n - 1, max(0, int(y)))


def tile_range(lon_min, lat_min, lon_max, lat_max, z):
    """経緯度の範囲を覆うタイルの範囲 (x0, x1, y0, y1)。両端を含む"""
    n = 2 ** z
    return (
        _tile_x(lon_min, n), _tile_x(lon_max, n),
        _tile_y(lat_max, n), _tile_y(lat_min, n),
    )


def tile_bounds_3857(x, y, z):
    size = 2.0 * HALF_WORLD / 2 ** z
    return (
        -HALF_WORLD + x * size, HALF_WORLD - (y + 1) * size,
        -HALF_WORLD + (x + 1) * size, HALF_WORLD - y * size,
    )


def tile_lon(x, z):
    return x / 2 ** z * 360.0 - 180.0


def tile_lat(y, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / 2 ** z))))


def tile_bounds_lonlat(x, y, z):
    return tile_lon(x, z), tile_lat(y + 1, z), tile_lon(x + 1, z), tile_lat(y, z)


def tiles_for_bounds(lon_min, lat_min, lon_max, lat_max, z):
    """経緯度の範囲を覆うタイル [(x, y), ...]"""
    x0, x1, y0, y1 = tile_range(lon_min, lat_min, lon_max, lat_max, z)
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def tile_center_lonlat(x, y, z):
    return tile_lon(x + 0.5, z), tile_lat(y + 0.5, z)
