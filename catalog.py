# -*- coding: utf-8 -*-
"""取得できるものの一覧と、レイヤーの並び・名前・表示の決まり。

基盤地図情報の種類の番号（type_code）は、ダウンロードサービスの一覧（/base/latest）が返すもの。
各 ZIP に入っているレイヤーは、道路縁（06）と建築物（11）以外はまだ実物で確かめていない。
一覧にないレイヤーが ZIP にあれば、取得の記録に名前を出す。
画面とレイヤーパネルに出す名前は英語と日本語を持ち、下の関数（fgd_layer_name など）で今の言語のものを返す。
"""

from .i18n import tr

# プラグインの名前（metadata.txt の name と同じ）。G.S.I. は Grid Sheet Importer（2次メッシュ＝図郭ごとに取り込む）の
# 頭文字で、国土地理院（GSI）の略ではない
PLUGIN_NAME = "G.S.I. Fundamental GeoPackage Builder"

# ---- 基盤地図情報（ログインが必要） ----

FGD_TYPES = [
    {"code": "01", "name": "測量の基準点", "short": "基準点", "layers": [("GCP", "基準点")]},
    {"code": "02", "name": "海岸線", "short": "海岸線", "layers": [("Cstline", "海岸線")]},
    {
        "code": "05", "name": "行政区画の境界線及び代表点", "short": "行政区画",
        "layers": [("AdmArea", "行政区画"), ("AdmBdy", "行政区画界線"), ("AdmPt", "行政区画代表点")],
    },
    {"code": "06", "name": "道路縁", "short": "道路縁", "layers": [("RdEdg", "道路縁"), ("RdCompt", "道路構成線")]},
    {"code": "08", "name": "軌道の中心線", "short": "軌道", "layers": [("RailCL", "軌道の中心線")]},
    {"code": "09", "name": "標高点", "short": "標高点", "layers": [("ElevPt", "標高点"), ("Cntr", "等高線")]},
    {
        "code": "10", "name": "水涯線", "short": "水涯線",
        "layers": [("WL", "水涯線"), ("WA", "水域"), ("WStrL", "水部構造物線"), ("WStrA", "水部構造物面")],
    },
    {"code": "11", "name": "建築物の外周線", "short": "建築物", "layers": [("BldL", "建築物の外周線"), ("BldA", "建築物")]},
    {
        "code": "12", "name": "市町村の町若しくは字の境界線及び代表点", "short": "町字",
        "layers": [("CommBdy", "町字界線"), ("CommPt", "町字の代表点")],
    },
]

FGD_LAYER_NAMES = {code: name for t in FGD_TYPES for code, name in t["layers"]}
FGD_LAYER_TYPE = {code: t["code"] for t in FGD_TYPES for code, _name in t["layers"]}
FGD_TYPE_BY_CODE = {t["code"]: t for t in FGD_TYPES}

# 画面とレイヤーパネルの英語の名前（日本語の名前は上の一覧。fgd_meshes の type_name などデータには日本語を書く）
FGD_TYPE_NAMES_EN = {
    "01": ("Survey control points", "Control pt"),
    "02": ("Coastline", "Coastline"),
    "05": ("Administrative boundaries and representative points", "Admin"),
    "06": ("Road edges", "Road edge"),
    "08": ("Railway track centerlines", "Railway"),
    "09": ("Elevation points", "Elev. pt"),
    "10": ("Waterlines", "Waterline"),
    "11": ("Building outlines", "Building"),
    "12": ("Town/aza boundaries and representative points", "Town/aza"),
}
FGD_LAYER_NAMES_EN = {
    "GCP": "Control point", "Cstline": "Coastline",
    "AdmArea": "Administrative area", "AdmBdy": "Administrative boundary", "AdmPt": "Administrative point",
    "RdEdg": "Road edge", "RdCompt": "Road component line", "RailCL": "Railway track centerline",
    "ElevPt": "Elevation point", "Cntr": "Contour",
    "WL": "Waterline", "WA": "Water area", "WStrL": "Water structure line", "WStrA": "Water structure area",
    "BldL": "Building outline", "BldA": "Building",
    "CommBdy": "Town/aza boundary", "CommPt": "Town/aza point",
}

# 行政データの小グループに入れるもの（これまで手で作っていたグループと同じ分け方）
ADMIN_GROUP_NAME = "基盤地図情報・行政データ"
ADMIN_GROUP_NAME_EN = "FGD administrative data"
ADMIN_LAYERS = ["ElevPt", "GCP", "CommPt", "CommBdy", "AdmPt", "AdmBdy", "AdmArea"]
# 行政データ以外の並び
MAIN_LAYERS = ["RdEdg", "RdCompt", "RailCL", "BldA", "BldL", "WStrA", "WStrL", "WA", "WL", "Cntr", "Cstline"]

# 属性の別名（基盤地図情報の項目名の意味）
FIELD_ALIASES = {
    "src_fid": "地物ID",
    "lfSpanFr": "整備データ登録日",
    "lfSpanTo": "整備データ削除日",
    "devDate": "整備完了日",
    "orgGILvl": "出典地図情報レベル",
    "orgMDId": "出典メタデータ",
    "vis": "表示区分",
    "type": "種別",
    "name": "名称",
    "admCode": "行政コード",
    "alti": "標高値",
    "mesh_code": "2次メッシュ",
    "data_date": "データの日付",
}

# 表示の決まり：(色, 線の太さ mm または点の大きさ mm, 面の塗り色 / None は塗らない)
FGD_STYLES = {
    "GCP": ("#b22222", 2.4, None),
    "ElevPt": ("#8b4513", 1.2, None),
    "CommPt": ("#555555", 1.4, None),
    "AdmPt": ("#7b3294", 1.8, None),
    "CommBdy": ("#9a9a9a", 0.2, None),
    "AdmBdy": ("#7b3294", 0.5, None),
    "AdmArea": ("#7b3294", 0.3, None),
    "RdEdg": ("#505050", 0.25, None),
    "RdCompt": ("#8a8a8a", 0.2, None),
    "RailCL": ("#222222", 0.5, None),
    "BldA": ("#808080", 0.1, "#c8c8c8"),
    "BldL": ("#707070", 0.15, None),
    "WStrA": ("#4a6fa5", 0.15, "#9fb6d6"),
    "WStrL": ("#1f4e9c", 0.4, None),
    "WA": ("#7fb8e0", 0.1, "#bfe3f7"),
    "WL": ("#3a8fd0", 0.25, None),
    "Cntr": ("#b07a3a", 0.15, None),
    "Cstline": ("#1f5fa8", 0.4, None),
}

# 道路・鉄道関係・等高線・地形表記線はレイヤーの不透明度（レンダリング）を下げて置く。
# 基盤地図情報・最適化ベクトルタイル共通のレイヤー名
DIMMED_LAYERS = {"RdEdg", "RdCompt", "RdCL", "RailCL", "RailTrCL", "Cntr", "TpgphLine"}
DIMMED_OPACITY = 0.6
# 道路関係は不透明度を少し上げ、線の色を少し濃くする（QColor.darker の値。100 で元の色）
ROAD_LAYERS = {"RdEdg", "RdCompt", "RdCL"}
ROAD_OPACITY = 0.65
ROAD_DARKER = 125
ROAD_WIDTH_MM = {"RdEdg": 0.15, "RdCompt": 0.15, "RdCL": 0.1}
# この縮尺（分母）よりズームアウトしたら描かないレイヤー
HIDE_BEYOND_SCALE = {"TpgphLine": 15000}

# ---- 最適化ベクトルタイル（ログイン不要） ----

BV_SOURCE_URL = (
    "https://cyberjapandata.gsi.go.jp/xyz/optimal_bvmap-v1/"
    "optimal_bvmap-v1.pmtiles"
)
BV_SOURCE_PAGE = "https://github.com/gsi-cyberjapan/optimal_bvmap"
BV_ZOOM = 16
# レイヤーパネルのグループの形（ユーザーが作った「GSI・基盤地図情報」の構成）
#   GSI・基盤地図情報（名前は画面で変えられる）
#     ├ 基盤地図情報・行政データ
#     ├ 最適化ベクトルタイル
#     └ 基盤地図情報
DEFAULT_GROUP_NAME = "GSI・基盤地図情報"
FGD_GROUP_NAME = "基盤地図情報"
BV_GROUP_NAME = "最適化ベクトルタイル"
DEFAULT_GROUP_NAME_EN = "GSI Fundamental Geospatial Data"
# 前の英語の初期値（設定に残っていれば今の初期値にし、空で残ったグループは片づける）
OLD_DEFAULT_GROUP_NAMES_EN = {"GSI base data"}
FGD_GROUP_NAME_EN = "Fundamental Geospatial Data"
BV_GROUP_NAME_EN = "Optimized vector tiles"
# 前の版で基盤地図情報のグループの中に作っていた小グループ（空になったら片づける）
OLD_BV_SUBGROUP_NAME = "最適化ベクトルタイル（ログイン不要）"
# 基盤地図情報の表と名前が重ならないよう、表の名前に付ける
BV_TABLE_PREFIX = "bv_"

# 最適化ベクトルタイル（ズーム16）にあるレイヤーすべて。属性はタイルにある vt_ で始まるもの。
# codes（vt_code の意味）は国土地理院「注記分類コード・地物種別コード一覧」（optbv_featurecodes.pdf）から
# 読み取れたものだけを入れた。入っていないレイヤーは「種別」が空で、vt_code の番号だけになる。
# overlap は基盤地図情報の同じ地物（どちらか一方だけを選べるようにする）
_I = "Integer"
_S = "String"
_R = "Real"


def _bv(source_layer, title, category, geometry, fields, style, codes=None, overlap=None, code_colors=None):
    return {
        "source_layer": source_layer, "title": title, "category": category, "geometry": geometry,
        "fields": [("vt_code", _I)] + fields, "style": style, "codes": codes or {},
        "overlap": overlap, "code_colors": code_colors or {},
    }


BV_CATEGORIES = ["行政", "道路・鉄道", "建物・構造物", "水", "地形", "注記"]
BV_CATEGORIES_EN = {
    "行政": "Administrative", "道路・鉄道": "Roads and railways", "建物・構造物": "Buildings and structures",
    "水": "Water", "地形": "Terrain", "注記": "Annotations",
}
BV_TITLES_EN = {
    "AdmArea": "Administrative area", "AdmBdry": "Administrative boundary", "SpcfArea": "Special district boundary",
    "RdCL": "Road centerline", "RdEdg": "Road edge", "RdCompt": "Road component line",
    "RailCL": "Railway centerline", "RailTrCL": "Railway track centerline",
    "BldA": "Building", "StrctLine": "Structure line", "StrctArea": "Structure area",
    "PwrTrnsmL": "Power transmission line",
    "WA": "Water area", "WL": "Waterline", "RvrCL": "River centerline", "WStrL": "Water structure line",
    "WStrA": "Water structure area", "WRltLine": "Water notation line", "Cstline": "Coastline", "Isbt": "Isobath",
    "Cntr": "Contour", "TpgphLine": "Topographic line", "TpgphArea": "Topographic area",
    "Anno": "Annotation",
}

BV_ITEMS = [
    _bv("AdmArea", "行政区画", "行政", "MultiPolygon", [], ("#7b3294", 0.3, None), overlap="AdmArea"),
    _bv("AdmBdry", "行政区画界線", "行政", "MultiLineString", [], ("#7b3294", 0.5, None), overlap="AdmBdy"),
    _bv("SpcfArea", "特定地区界", "行政", "MultiLineString", [], ("#b05fa8", 0.3, None), {6101: "特定地区界"}),
    _bv("RdCL", "道路中心線", "道路・鉄道", "MultiLineString", [
        ("vt_drworder", _I), ("vt_flag17", _I), ("vt_lvorder", _I), ("vt_motorway", _I), ("vt_rdctg", _S),
        ("vt_rnkwidth", _S), ("vt_tollsect", _S), ("vt_width", _I)], ("#808080", 0.4, None)),
    _bv("RdEdg", "道路縁", "道路・鉄道", "MultiLineString", [("vt_drworder", _I)], ("#505050", 0.25, None),
        overlap="RdEdg"),
    _bv("RdCompt", "道路構成線", "道路・鉄道", "MultiLineString", [], ("#8a8a8a", 0.2, None), overlap="RdCompt"),
    _bv("RailCL", "鉄道中心線", "道路・鉄道", "MultiLineString", [
        ("vt_flag17", _I), ("vt_lvorder", _I), ("vt_railstate", _S), ("vt_rtcode", _S), ("vt_sngldbl", _S)],
        ("#222222", 0.5, None), {8201: "鉄道中心線"}),
    _bv("RailTrCL", "軌道の中心線", "道路・鉄道", "MultiLineString", [("vt_drworder", _I)], ("#444444", 0.4, None),
        overlap="RailCL"),
    _bv("BldA", "建築物", "建物・構造物", "MultiPolygon", [("vt_lvorder", _I)], ("#808080", 0.1, "#c8c8c8"),
        {3101: "普通建物", 3102: "堅ろう建物", 3103: "高層建物", 3111: "普通無壁舎", 3112: "堅ろう無壁舎"},
        overlap="BldA"),
    _bv("StrctLine", "構造物線", "建物・構造物", "MultiLineString", [], ("#666666", 0.4, None),
        {4201: "高塔", 4202: "坑口"}),
    _bv("StrctArea", "構造物面", "建物・構造物", "MultiPolygon", [], ("#808080", 0.15, "#d0d0d0"),
        {4301: "巨大構造物", 4302: "タンク"}),
    _bv("PwrTrnsmL", "送電線", "建物・構造物", "MultiLineString", [], ("#9a5c2e", 0.4, None), {8202: "送電線"}),
    _bv("WA", "水域", "水", "MultiPolygon", [], ("#7fb8e0", 0.1, "#bfe3f7"), overlap="WA"),
    _bv("WL", "水涯線", "水", "MultiLineString", [], ("#3a8fd0", 0.25, None), overlap="WL"),
    _bv("RvrCL", "河川中心線", "水", "MultiLineString", [], ("#2f7fd0", 0.35, None),
        {5301: "一条河川（通常部）", 5302: "一条河川（枯れ川部）", 5321: "人工水路（空間）", 5322: "人工水路（地下）",
         5331: "用水路"}),
    _bv("WStrL", "水部構造物線", "水", "MultiLineString", [("vt_flag17", _I)], ("#1f4e9c", 0.8, None),
        {5501: "ダム", 5511: "桟橋（鉄、コンクリート）", 5514: "せき", 5515: "水門", 5521: "滝", 5532: "透過水制"},
        overlap="WStrL",
        code_colors={5501: "#555555", 5511: "#8c6d31", 5514: "#d62728", 5515: "#ff7f0e", 5521: "#1f77b4",
                     5532: "#2ca02c"}),
    _bv("WStrA", "水部構造物面", "水", "MultiPolygon", [], ("#4a6fa5", 0.15, "#9fb6d6"),
        {5401: "ダム", 5411: "桟橋（鉄、コンクリート）"}, overlap="WStrA"),
    _bv("WRltLine", "水部表記線", "水", "MultiLineString", [("vt_angle", _R)], ("#6aa0d8", 0.3, None),
        {5901: "水上・海上交通（船舶）", 5902: "水上・海上交通（航路の軌跡）", 5911: "流水方向"}),
    _bv("Cstline", "海岸線", "水", "MultiLineString", [], ("#1f5fa8", 0.4, None), overlap="Cstline"),
    _bv("Isbt", "等深線", "水", "MultiLineString", [("vt_depth", _R)], ("#7fb2e5", 0.2, None)),
    _bv("Cntr", "等高線", "地形", "MultiLineString", [("vt_alti", _I)], ("#b07a3a", 0.15, None),
        {7351: "等高線（通常部）", 7352: "等高線（数値部）", 7353: "等高線（崖部）", 7371: "等深線（湖池）"},
        overlap="Cntr"),
    _bv("TpgphLine", "地形表記線", "地形", "MultiLineString", [], ("#8b5a2b", 0.3, None),
        {7521: "雨裂（上部）", 7531: "凹地方向線（大凹地）", 7532: "凹地方向線（小凹地）", 7541: "隠顕岩",
         7551: "干潟界", 7561: "枯れ川水涯線", 7571: "湖底急斜面", 7572: "水部凹地方向線"}),
    _bv("TpgphArea", "地形表記面", "地形", "MultiPolygon", [("vt_flag17", _I)], ("#a08050", 0.15, "#e8d8b8")),
    # 注記は点と文字（地名・記号・植生・三角点など）。使い方は確かめてから決める
    # vt_arrngagl（文字の角度）は実際には小数（359.67 など）が入っているが、配信の一覧では整数とされているため
    # GDAL が読む時点で整数の度に切り捨てる（ラベルの角度としては差し支えない）
    _bv("Anno", "注記", "注記", "MultiPoint", [
        ("vt_arrng", _I), ("vt_arrngagl", _I), ("vt_dsppos", _S), ("vt_flag17", _I), ("vt_text", _S)],
        ("#333333", 1.2, None)),
]

BV_BY_LAYER = {item["source_layer"]: item for item in BV_ITEMS}

# 注記のうち文字（vt_text）を持たない記号のコードの名前（注記分類コード一覧の 4 桁のもの）。
# データには足さず、ラベルの表示にだけ使う（取得したデータはオリジナルのまま）
ANNO_SYMBOL_NAMES = {
    1301: "都市記号", 1302: "都市記号", 1303: "都市記号", 1401: "都道府県所在地", 1402: "市役所",
    1403: "町村役場", 2901: "国道番号", 2903: "都市高速道路番号", 2904: "高速道路番号",
    2941: "インターチェンジ", 2942: "ジャンクション", 2943: "サービスエリア", 2944: "パーキングエリア",
    2945: "スマートインターチェンジ",
    3201: "官公署", 3202: "裁判所", 3203: "税務署", 3204: "外国公館", 3205: "市役所", 3206: "町村役場",
    3211: "交番", 3212: "高等学校", 3213: "中学校", 3214: "小学校", 3215: "老人ホーム", 3216: "博物館",
    3217: "図書館", 3218: "郵便局", 3221: "灯台", 3231: "神社", 3232: "寺院", 3241: "警察署",
    3242: "消防署", 3243: "病院", 3244: "保健所", 3261: "工場",
    4101: "煙突", 4102: "風車", 4103: "油井・ガス井", 4104: "記念碑", 4105: "自然災害伝承碑",
    5801: "滝", 6301: "墓地", 6311: "田", 6312: "畑", 6313: "茶畑", 6314: "果樹園",
    6321: "広葉樹林", 6322: "針葉樹林", 6323: "竹林", 6324: "ヤシ科樹林", 6325: "ハイマツ地", 6326: "笹地",
    6327: "荒地", 6331: "温泉", 6332: "噴火口・噴気口", 6341: "史跡・名勝・天然記念物", 6342: "城跡",
    6351: "採鉱地", 6361: "港湾", 6362: "漁港", 6367: "特定重要港", 6368: "重要港", 6371: "空港",
    6373: "自衛隊等の飛行場", 6375: "国際空港", 6376: "拠点空港等", 6381: "自衛隊",
    7101: "電子基準点", 7102: "三角点", 7103: "水準点", 7201: "標高点", 7221: "標高（火山）",
    7601: "砂礫地", 7621: "雨裂", 7701: "水面標高", 7711: "水深", 8103: "発電所等", 8105: "電波塔",
}
# 注記のラベル（ポイント、縁取りの太さ mm）
ANNO_LABEL_SIZE = 5
ANNO_LABEL_BUFFER = 0.6
# 基盤地図情報のレイヤー名 → 同じ地物の最適化ベクトルタイルのレイヤー名
FGD_TO_BV = {item["overlap"]: item["source_layer"] for item in BV_ITEMS if item["overlap"]}

FGD_SOURCE_PAGE = "https://service.gsi.go.jp/kiban/"

# 取得する範囲を選ぶ間だけ置く背景（地理院タイルの淡色地図。ズーム 5〜18）。窓を閉じたら外す
PREVIEW_URI = "type=xyz&url=https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png&zmin=5&zmax=18"
PREVIEW_SOURCE_PAGE = "https://maps.gsi.go.jp/development/ichiran.html"
PREVIEW_PROPERTY = "fgd_gpkg_builder/preview"

# 言語を切り替えたあと、前の言語の名前のまま空で残った小グループ・グループを片づけるための名前
SUBGROUP_NAMES_ALL = {
    ADMIN_GROUP_NAME, ADMIN_GROUP_NAME_EN, FGD_GROUP_NAME, FGD_GROUP_NAME_EN, BV_GROUP_NAME, BV_GROUP_NAME_EN,
    OLD_BV_SUBGROUP_NAME,
}
DEFAULT_GROUP_NAMES_ALL = {DEFAULT_GROUP_NAME, DEFAULT_GROUP_NAME_EN} | OLD_DEFAULT_GROUP_NAMES_EN


def bv_table(item):
    return BV_TABLE_PREFIX + item["source_layer"]


# ---- 今の言語での名前（i18n の言語による） ----

def fgd_type_name(type_info):
    return tr(FGD_TYPE_NAMES_EN[type_info["code"]][0], type_info["name"])


def fgd_type_short(type_info):
    return tr(FGD_TYPE_NAMES_EN[type_info["code"]][1], type_info["short"])


def fgd_layer_name(code):
    return tr(FGD_LAYER_NAMES_EN.get(code, code), FGD_LAYER_NAMES.get(code, code))


def bv_title(item):
    return tr(BV_TITLES_EN.get(item["source_layer"], item["source_layer"]), item["title"])


def bv_category(category):
    return tr(BV_CATEGORIES_EN.get(category, category), category)


def default_group_name():
    return tr(DEFAULT_GROUP_NAME_EN, DEFAULT_GROUP_NAME)


def admin_group_name():
    return tr(ADMIN_GROUP_NAME_EN, ADMIN_GROUP_NAME)


def fgd_group_name():
    return tr(FGD_GROUP_NAME_EN, FGD_GROUP_NAME)


def bv_group_name():
    return tr(BV_GROUP_NAME_EN, BV_GROUP_NAME)


def fgd_attribution():
    return tr("Fundamental Geospatial Data (GSI Japan)", "基盤地図情報（国土地理院）")


def bv_attribution():
    return tr("GSI optimized vector tiles", "国土地理院最適化ベクトルタイル")


def preview_name():
    return tr("GSI Tiles (pale map) - fetch preview", "地理院タイル（淡色地図）※取得画面のプレビュー")


def preview_attribution():
    return tr("GSI Tiles (GSI Japan)", "地理院タイル（国土地理院）")


def rights_text(attribution, page):
    return tr("Source: {0} ({1})", "出典：{0}（{1}）").format(attribution, page)
