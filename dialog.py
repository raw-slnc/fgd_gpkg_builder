# -*- coding: utf-8 -*-
"""取得画面。

左に使用データ（基盤地図情報・最適化ベクトルタイル）、右に表示範囲に
掛かる2次メッシュごとの最新データと保存済みの状況を並べる。範囲は表示範囲に掛かる2次メッシュ全体。
地図には、取得済みの範囲すべてを今のチェックに対する状況で塗る（そろっている／一部だけ）。
文字は英語が基本で日本語は訳（i18n.tr）。言語を切り替えると窓を作り直す（plugin.py）。
"""

import os
import time

from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCsException, QgsGeometry,
    QgsLayerMetadata, QgsPointXY, QgsProject, QgsRasterLayer,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtCore import QEvent, QPropertyAnimation, QSettings, Qt, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QDesktopServices, QFont, QKeySequence, QPalette

try:  # Qt6（QGIS 4）は QtGui、Qt5（QGIS 3）は QtWidgets
    from qgis.PyQt.QtGui import QShortcut
except ImportError:
    from qgis.PyQt.QtWidgets import QShortcut
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QProgressDialog,
    QPushButton,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import fgd_api, store
from .catalog import (
    BV_BY_LAYER, BV_CATEGORIES, BV_ITEMS, BV_SOURCE_PAGE, BV_ZOOM, DEFAULT_GROUP_NAMES_ALL, FGD_GROUP_NAME,
    FGD_GROUP_NAME_EN, FGD_SOURCE_PAGE, FGD_TO_BV, FGD_TYPES, PLUGIN_NAME, PREVIEW_PROPERTY, PREVIEW_SOURCE_PAGE,
    PREVIEW_URI,
    admin_group_name, bv_attribution, bv_category, bv_group_name, bv_title, default_group_name, fgd_attribution,
    fgd_group_name, fgd_layer_name, fgd_type_name, fgd_type_short, preview_attribution, preview_name, rights_text,
)
from .credentials import CredentialsManager
from .i18n import ENGLISH, JAPANESE, is_japanese, set_language, tr
from .login_dialog import LoginDialog
from .tiles import tile_center_lonlat, tile_range
from .worker import FetchThread, ListThread, StoredThread, mesh_tiles, plan_fgd_downloads

SETTINGS = "fgd_gpkg_builder/"
ROLE = Qt.ItemDataRole.UserRole
# これを超えるメッシュ数・タイル数は取得前に確かめる（上限ではない）
CONFIRM_MESHES = 30
CONFIRM_TILES = 600
# 地図を動かしたとき、まだ確かめていないメッシュがこれ以下なら最新の状況を自動で問い合わせる
# （超えたときは「最新の状況を確認」で問い合わせる）
AUTO_LIST_MESHES = 120
# 保存先の読み込み・最新の状況の問い合わせの進捗バーを最後まで進める最短の時間（秒）。すぐ終わっても進んだことが見えるように
LIST_MIN_SHOW = {"stored": 1.0, "list": 1.2}
# 区切りごとの値の間を動かす時間（秒）
LIST_STEP_ANIMATION = 0.15
# 進み具合を見せる処理の順（同時に走るときは先のものから見せる）。保存先の読み込みは、読み終わるまで取得を
# 押せないので先に見せる
ACTIVITY_ORDER = ("stored", "list")
# 実行の区域で確保する文の行数（これより多いときは伸びる）
ACTION_MIN_LINES = 4
# 表に並べるメッシュの数（超えたら表は省き、地図の色で見てもらう）
TABLE_MAX_ROWS = 300
# 「レイヤーを更新しています…」の知らせを出してから、配置を始めるまでの時間（秒）。窓が画面に出て描かれる間
NOTICE_SETTLE = 0.2
# 記録（ログ）の欄の高さ。開くときは、この分だけ窓の高さを伸ばす
LOG_HEIGHT = 120
# マニュアル（プラグインのフォルダの HTML。英語と日本語を中で切り替える）
MANUAL_FILE = "manual_fgd_gpkg_builder.html"
# 保存先：プロジェクトと同じ階層のフォルダとその中の GeoPackage。使う保存先はプロジェクトファイルに記録する
DATA_DIR_NAME = "gsi_fgd_builder"
DATA_FILE_NAME = "gsi_fgd_builder.gpkg"
PROJECT_SCOPE = "fgd_gpkg_builder"
PROJECT_KEY = "gpkg_path"
# 使用データのロック（プロジェクトごと）：ロックしているか、ロックしたときのチェック（"fgd:RdEdg" などの並び）
PROJECT_LOCKED_KEY = "lock_checked"
PROJECT_LOCK_KEY = "locked"
# 配置する範囲（コンボボックスの並び）
PLACE_VISIBLE, PLACE_ALL = 0, 1

# 状況の色
COLOR_CURRENT = QColor("#d6efd6")   # 保存済み・最新
COLOR_UPDATE = QColor("#ffe0b0")    # 新しいデータあり
COLOR_NONE = QColor("#efefef")      # データなし
COLOR_GRAY_TEXT = QColor("#9a9a9a")
# 地図の塗り（今のチェックに対して）
COLOR_MAP_FULL = QColor(46, 157, 58, 70)     # チェックした内容がそろっている
COLOR_MAP_PART = QColor(240, 185, 0, 110)    # 一部だけ（チェックを足した範囲・新しいデータあり）
# 操作のボタンの色（パレットで付ける。文字は白）
ACTION_COLORS = {"fetch": "#2a6fb0", "place": "#2e8540", "cancel": "#c0392b"}


class FgdGpkgDialog(QDialog):

    # 言語ボタンが押された（plugin.py が新しい言語で窓を作り直す）
    languageChanged = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.session = None
        self.session_user = ""
        self._list_thread = None
        self._list_again = False
        self._fetch_thread = None
        self._listing_by_mesh = {}     # {メッシュ: [最新データの一覧の項目...]}（問い合わせたメッシュだけ）
        self._meshes = []
        self._mesh_bounds = None
        self._too_wide = False
        self._canvas_connected = False
        self._updating_tree = False
        self._stored_cache = None      # 保存先の取得の記録（読み直すときは None に）
        self._stored_thread = None
        self._stored_again = False
        self._stored_last = None       # (ファイルの状態, 読んだ結果)。ファイルが変わっていなければ読み直さない
        self._content_widths = []      # 状況の表の、中身に合わせた欄の幅（余りを配る元）
        self._center_tile_counts = {}  # {メッシュ: 中心がそのメッシュに入るタイルの数}
        self._preview_id = None
        self._open = False
        self._close_after_fetch = False  # 閉じるために取得を中止した（止まったら閉じる）
        self._summary_before = []        # 付け替えて取得し直す前の取得の結果（終わったら続けて出す）
        self._asking_shared = False      # 「共有データとして使用しますか？」を聞いている途中
        # 進み具合を出す処理（"stored"＝保存先の読み込み、"list"＝最新の状況の問い合わせ）
        self._activities = {}            # {処理: {"value", "max", "done", "shown"}}
        self._activity_shown = None      # 今、進捗バーに出している処理
        self._activity_end = None        # 最後まで進めている途中の処理（進み終えたら次へ）
        self._activity_display = False   # 実行の区域に進み具合を出している（見込みをどけている）
        self._stage_before_activity = ""  # 出す前の状態の行（前回の結果など。出し終えたら戻す）
        self._fetch_meshes = []

        self.setWindowTitle(PLUGIN_NAME)
        # 普通の窓として扱わせ、Alt+Tab やタスクバーに出し、最小化もできるようにする
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowCloseButtonHint)
        # 英語は日本語より文が長いので、少し広めにする
        # 大きさは決め打ちにしない。部品が入りきる最小の大きさで開き（圧迫感を出さない）、それより小さくはしない
        # （窓の最小はレイアウトが決める）。組み立てたあとで _fit_minimum する

        # 取得済みの範囲の塗り（下）と、可視範囲に掛かるメッシュの橙の枠（上）
        self.statusRubbers = {}
        for status, color in (("full", COLOR_MAP_FULL), ("part", COLOR_MAP_PART)):
            band = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
            band.setFillColor(color)
            band.setStrokeColor(QColor(color.red(), color.green(), color.blue(), 160))
            band.setWidth(1)
            self.statusRubbers[status] = band
        self.rubber = QgsRubberBand(self.canvas, Qgis.GeometryType.Line)
        self.rubber.setColor(QColor(230, 120, 0, 200))
        self.rubber.setWidth(2)

        self._listTimer = QTimer(self)
        self._listTimer.setSingleShot(True)
        self._listTimer.setInterval(1200)
        self._listTimer.timeout.connect(self._start_list)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_login_box())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter = splitter
        splitter.addWidget(self._build_tree_panel())
        splitter.addWidget(self._build_mesh_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([400, 780])
        layout.addWidget(splitter, 1)

        # 上から 使用データ・状況の表 → 保存とレイヤー → 取得・配置（実行の区域）→ 記録
        layout.addWidget(self._build_output_box())
        layout.addWidget(self._build_progress_area())
        layout.addWidget(self._build_log_area())
        self._disable_auto_default()

        # 出典は1つずつ1行（3行）。1つの文で折り返すと、切れ目が中途半端になった。
        # 「出典：」を左に分けて置き、2行目・3行目の頭を1行目の出典の頭にそろえる
        source_row = QHBoxLayout()
        source_title = QLabel(tr("Sources:", "出典："))
        source = QLabel(tr(
            '<a href="{0}">{1}</a><br>'
            '<a href="{2}">{3}</a> (trial release; the URL and contents may change)<br>'
            'Preview map: <a href="{4}">{5}</a>',
            '<a href="{0}">{1}</a><br>'
            '<a href="{2}">{3}</a>（試験公開。URL やデータの内容が変わることがあります）<br>'
            'プレビュー地図：<a href="{4}">{5}</a>',
        ).format(FGD_SOURCE_PAGE, fgd_attribution(), BV_SOURCE_PAGE, bv_attribution(), PREVIEW_SOURCE_PAGE,
                 preview_attribution()))
        source.setOpenExternalLinks(True)
        source.setWordWrap(True)
        for label in (source_title, source):
            label.setStyleSheet("color:#555;")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        source_row.setSpacing(0)
        source_row.addWidget(source_title, 0, Qt.AlignmentFlag.AlignTop)
        if not is_japanese():
            # 英語は「:」のあとに空きが無いと詰まって見える（日本語の「：」は字の中に空きがある）
            source_row.addSpacing(self.fontMetrics().horizontalAdvance(" "))
        source_row.addWidget(source, 1)
        layout.addLayout(source_row)

        # Ctrl+W でも閉じる（Esc・閉じるボタン・窓の × と同じく closeEvent を通る）
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)

        # プロジェクトを開き直した・初めて保存した・閉じたときは、保存先を決め直す（窓を開いている間だけ）
        project = QgsProject.instance()
        project.readProject.connect(self._resolve_project_path)
        project.fileNameChanged.connect(self._resolve_project_path)
        project.cleared.connect(self._resolve_project_path)

        self._update_login_state()
        self._update_summary()
        self._fitted = False  # 初めて表示したあとに、部品が入りきる最小の大きさに合わせる（showEvent）
        # 大きさと位置は表示してから決める（文の折り返しなどは表示しないと決まらない）。決める途中の
        # 「表示→移動」が見えないよう、決め終えるまで透明にしておく（_place_initially で戻す）
        self.setWindowOpacity(0.0)
        self._log_delta = 0   # 記録を開いたときに窓を伸ばした高さ（閉じるときに縮める）

    def _fit_minimum(self):
        """部品が入りきる最小の大きさにする。表示して部品の並び（文の折り返しなど）が決まってから呼ぶ"""
        self.layout().activate()
        self.resize(self.minimumSizeHint())
        # 窓の最小は、折り返す文（出典の行・実行の区域の文）を実際の幅で折り返したときの高さを少なく見積もる。
        # その分、真ん中の区域（使用データの木・状況の表）が最小より低くなり、表と凡例が重なったので、
        # 足りない分だけ窓を伸ばし、その高さを窓の最小にする
        self.layout().activate()
        shortage = self._splitter.minimumSizeHint().height() - self._splitter.height()
        if shortage > 0:
            # 先に高さを決める（最小を上げた時点で窓が伸びるので、そのあとの高さに足すと伸びすぎた）
            height = self.height() + shortage
            self.setMinimumHeight(height)
            self.resize(self.width(), height)
        self._place_initially()
        # 大きさと位置が決まったので見えるようにする
        self.setWindowOpacity(1.0)

    def _place_initially(self):
        """最初に置く位置。大きさが決まったので QGIS の窓の真ん中に置き直し、記録を開いて窓が伸びても
        画面の下に収まるよう、その分だけ上に置く（画面の上端より上には置かない）"""
        frame = self.frameGeometry()
        main = self.iface.mainWindow() if hasattr(self.iface, "mainWindow") else None
        if main is not None:
            frame.moveCenter(main.frameGeometry().center())
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is not None:
            area = screen.availableGeometry()
            spacing = self.layout().spacing() if self.layout() is not None else 0
            # 記録の分（欄の高さとその上の間隔）を下に空けておく
            bottom = frame.bottom() + LOG_HEIGHT + max(spacing, 0)
            if bottom > area.bottom():
                frame.moveTop(max(frame.top() - (bottom - area.bottom()), area.top()))
            if frame.top() < area.top():
                frame.moveTop(area.top())
        self.move(frame.topLeft())

    # ================= 言語の切り替え =================

    def take_state(self):
        """作り直す前の窓から、新しい窓へ引き継ぐもの"""
        self._save_settings()
        return {
            "session": self.session, "session_user": self.session_user,
            "listing_by_mesh": dict(self._listing_by_mesh), "log": self.logEdit.toPlainText(),
            "log_shown": self.logToggle.isChecked(), "geometry": self.saveGeometry(),
            "stored_last": self._stored_last,
        }

    def restore_state(self, state):
        self.session = state["session"]
        self.session_user = state["session_user"]
        self._listing_by_mesh = state["listing_by_mesh"]
        self._stored_last = state["stored_last"]
        if state["log"]:
            self.logEdit.setPlainText(state["log"])
        self.logToggle.setChecked(state["log_shown"])
        self.restoreGeometry(state["geometry"])
        # 前の窓の大きさを引き継いだので、最小の大きさに合わせ直さない（透明にしておく必要もない）
        self._fitted = True
        self.setWindowOpacity(1.0)
        self._update_login_state()

    def _switch_language(self):
        if self._fetch_thread is not None:
            return
        set_language(ENGLISH if is_japanese() else JAPANESE)
        self.languageChanged.emit()

    # ================= 画面の組み立て =================

    def _build_login_box(self):
        box = QGroupBox(tr("Fundamental Geospatial Data download service", "基盤地図情報ダウンロードサービス"))
        row = QHBoxLayout(box)
        self.loginLamp = QLabel("●")
        row.addWidget(self.loginLamp)
        self.loginLabel = QLabel("")
        self.loginLabel.setWordWrap(True)
        row.addWidget(self.loginLabel, 1)
        self.loginButton = QPushButton(tr("Log in…", "ログイン…"))
        self.loginButton.clicked.connect(self._login)
        row.addWidget(self.loginButton)
        self.logoutButton = QPushButton(tr("Log out", "ログアウト"))
        self.logoutButton.clicked.connect(self._logout)
        row.addWidget(self.logoutButton)
        self.forgetButton = QPushButton(tr("Forget saved ID/password", "保存したID・パスワードを消す"))
        self.forgetButton.clicked.connect(self._forget_credentials)
        row.addWidget(self.forgetButton)
        return box

    def _build_tree_panel(self):
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(QLabel(tr("Data to use", "使用データ")))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumWidth(340)
        # 窓を最小にしても、5行ほどは見えるようにする
        self.tree.setMinimumHeight(self.fontMetrics().lineSpacing() * 5 + 30)
        # 名前を「…」で切らず、入りきらないときは横に送れるようにする（英語の名前は長い）
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        checked = QSettings().value(SETTINGS + "checked", None)
        checked = None if checked is None else set(_as_list(checked))
        paren = tr("{0} ({1})", "{0}（{1}）")

        self._leaf_by_key = {}
        self._fgd_root = QTreeWidgetItem([tr("Fundamental Geospatial Data", "基盤地図情報")])
        self._fgd_root.setData(0, ROLE, ("root", "fgd"))
        for type_info in FGD_TYPES:
            type_item = QTreeWidgetItem([fgd_type_name(type_info)])
            type_item.setData(0, ROLE, ("type", type_info["code"]))
            for code, _name in type_info["layers"]:
                leaf = QTreeWidgetItem([paren.format(fgd_layer_name(code), code)])
                leaf.setData(0, ROLE, ("fgd", code))
                leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                is_checked = checked is None or "fgd:" + code in checked
                leaf.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
                if code in FGD_TO_BV:
                    _mark_exclusive(leaf, tr("the optimized vector tile layer \"{0}\"", "最適化ベクトルタイルの「{0}」")
                                    .format(bv_title(BV_BY_LAYER[FGD_TO_BV[code]])))
                type_item.addChild(leaf)
                self._leaf_by_key[("fgd", code)] = leaf
            self._fgd_root.addChild(type_item)

        # 最適化ベクトルタイルは分類ごとにまとめる。初めて開いたときは何も選ばない（タイルが多く時間がかかるため）
        self._bv_root = QTreeWidgetItem([tr("Optimized vector tiles", "最適化ベクトルタイル")])
        self._bv_root.setData(0, ROLE, ("root", "bv"))
        self._bv_categories = []
        for category in BV_CATEGORIES:
            category_item = QTreeWidgetItem([bv_category(category)])
            category_item.setData(0, ROLE, ("bv_category", category))
            for item in (i for i in BV_ITEMS if i["category"] == category):
                leaf = QTreeWidgetItem([paren.format(bv_title(item), item["source_layer"])])
                leaf.setData(0, ROLE, ("bv", item["source_layer"]))
                leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                # 基盤地図情報と同じ地物は、両方に印が付いていたら基盤地図情報の方を残す
                is_checked = checked is not None and "bv:" + item["source_layer"] in checked and not (
                    item["overlap"] and "fgd:" + item["overlap"] in checked)
                leaf.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
                # 種別の名前（vt_code の意味）はデータに書く日本語のまま見せる
                tips = ["{0}: {1}".format(code, name) for code, name in item["codes"].items()]
                leaf.setToolTip(0, "\n".join(tips) or tr(
                    "No type names yet (only the vt_code numbers)", "種別の名前はまだ入れていません（vt_code の番号だけ）"))
                if item["overlap"]:
                    _mark_exclusive(leaf, tr("the Fundamental Geospatial Data layer \"{0}\"", "基盤地図情報の「{0}」")
                                    .format(fgd_layer_name(item["overlap"])))
                category_item.addChild(leaf)
                self._leaf_by_key[("bv", item["source_layer"])] = leaf
            self._bv_root.addChild(category_item)
            self._bv_categories.append(category_item)

        bold = QFont()
        bold.setBold(True)
        for root in (self._fgd_root, self._bv_root):
            root.setFont(0, bold)
            self.tree.addTopLevelItem(root)
        # 親は子から自動で「すべて／一部／なし」になる
        for parent in self._all_parents():
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        self._fgd_root.setExpanded(True)
        self._bv_root.setExpanded(True)
        self.tree.itemChanged.connect(self._on_tree_changed)
        column.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self._select_buttons = []
        for text, state in ((tr("Select all", "すべて選ぶ"), Qt.CheckState.Checked),
                            (tr("Clear all", "すべて外す"), Qt.CheckState.Unchecked)):
            button = QToolButton()
            button.setText(text)
            button.clicked.connect(lambda _checked=False, s=state: self._set_all(s))
            buttons.addWidget(button)
            self._select_buttons.append(button)
        # 今のチェックを構成としてプロジェクトに記録し、変えられないようにする。同じ構成で別の場所を取得するときに
        self.lockButton = QToolButton()
        self.lockButton.setCheckable(True)
        self.lockButton.setToolTip(tr(
            "Records the checked items for this project and locks them. Press again to unlock.",
            "今のチェックをこのプロジェクトの構成として記録し、ロックします。もう一度押すと外します。"))
        self.lockButton.clicked.connect(self._toggle_lock)
        # 「ロック」「ロック中」で幅が変わると右の「構成を復元」がずれるので、長い方の幅に固定する
        widths = []
        for text in (tr("Lock", "ロック"), tr("Locked", "ロック中")):
            self.lockButton.setText(text)
            widths.append(self.lockButton.sizeHint().width())
        self.lockButton.setFixedWidth(max(widths))
        buttons.addWidget(self.lockButton)
        # ロックで最後に記録した構成のチェックに戻す（ロックは外したまま）。記録するロックの右に置く
        self.restoreButton = QToolButton()
        self.restoreButton.setText(tr("Restore", "構成を復元"))
        self.restoreButton.setToolTip(tr("Returns the checks to the configuration last recorded by the lock.",
                                         "チェックを、ロックで最後に記録した構成に戻します。"))
        self.restoreButton.clicked.connect(self._restore_locked)
        buttons.addWidget(self.restoreButton)
        self._update_lock_ui()
        buttons.addStretch(1)
        column.addLayout(buttons)
        return panel

    def _build_mesh_panel(self):
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        # 表の情報（メッシュの数など）は、表の凡例の下に置く（下で column に足す）
        self.meshLabel = QLabel("")
        self.meshLabel.setWordWrap(True)
        # 折り返す文の高さは部品の並びが少なく見積もり、窓を最小にすると3行目が切れた（英語は3行になる）
        self.meshLabel.setMinimumHeight(self.fontMetrics().lineSpacing() * 3)

        # プレビュー地図のチェックは、地図の凡例と同じ段（実行の区域の進捗バーの段）に置く
        self.previewCheckbox = QCheckBox(tr("Show preview map (GSI Tiles, pale map)",
                                            "プレビュー地図（地理院タイル・淡色地図）を表示"))
        self.previewCheckbox.setToolTip(tr(
            "A background for choosing the area to fetch. It is removed from the Layers panel when this window "
            "is closed.",
            "取得する範囲を選ぶための背景です。この窓を閉じるとレイヤーパネルから外します。"))
        self.previewCheckbox.setChecked(QSettings().value(SETTINGS + "preview_map", True, type=bool))
        self.previewCheckbox.toggled.connect(self._sync_preview)

        self.table = QTableWidget(0, len(FGD_TYPES) + 1)
        # 窓を最小にしても、見出しと2行（日付と状況の2段の行）は見えるようにする
        self.table.setMinimumHeight(self.fontMetrics().lineSpacing() * 6 + 40)
        self.table.setHorizontalHeaderLabels([tr("Mesh", "メッシュ")] + [fgd_type_short(t) for t in FGD_TYPES])
        for index, type_info in enumerate(FGD_TYPES):
            self.table.horizontalHeaderItem(index + 1).setToolTip(
                tr("{0} ({1})", "{0}（{1}）").format(fgd_type_name(type_info), type_info["code"]))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # 欄の幅は中身に合わせ（日付が切れないように）、表に余りがあれば全部の欄に均等に配る（_fit_columns）。
        # 最後の欄だけで埋めない。入りきらないときは横に送れる
        self.table.horizontalHeader().setStretchLastSection(False)
        # 表の中の表示部分の幅が変わったら（窓の大きさ・分割・縦のスクロールバーの出入り）、余りを配り直す
        self.table.viewport().installEventFilter(self)
        column.addWidget(self.table, 1)

        # 表の色の凡例（地図の塗りの凡例は、実行の区域の進捗バーの段に置く）
        table_legend = _legend_row("", (
            (COLOR_CURRENT, tr("Stored (latest)", "保存済み（最新）")),
            (COLOR_UPDATE, tr("Newer data", "新しいデータあり")),
            (QColor("white"), tr("Not fetched", "未取得")), (COLOR_NONE, tr("No data", "データなし"))))
        # 最新の状況の確認は、表の内容を新しくする操作なので、表の凡例の右に置く
        self.listButton = QPushButton(tr("Check latest status", "最新の状況を確認"))
        self.listButton.clicked.connect(lambda _checked=False: self._start_list(refresh=True))
        table_legend.addWidget(self.listButton)
        column.addLayout(table_legend)
        column.addWidget(self.meshLabel)
        return panel

    def _build_output_box(self):
        box = QGroupBox(tr("Storage and layers", "保存とレイヤー"))
        form = QFormLayout(box)
        path_row = QHBoxLayout()
        # 保存先はプロジェクトごとに決める（_resolve_project_path）。初めはプロジェクトの隣のフォルダの GeoPackage
        self.pathEdit = QLineEdit("")
        self.pathEdit.editingFinished.connect(self._on_path_changed)
        path_row.addWidget(self.pathEdit, 1)
        self.pathButton = QToolButton()
        self.pathButton.setText("…")
        self.pathButton.clicked.connect(self._choose_path)
        path_row.addWidget(self.pathButton)
        form.addRow(tr("Save to (GeoPackage)", "保存先（GeoPackage）"), path_row)

        group_name = QSettings().value(SETTINGS + "group_name", default_group_name())
        if group_name in ("", FGD_GROUP_NAME, FGD_GROUP_NAME_EN) or group_name in DEFAULT_GROUP_NAMES_ALL:
            # 初期値のままなら今の言語の初期値にする。前の版の初期値（基盤地図情報）は中の小グループと
            # 同じ名前になるので、これも新しい初期値にする
            group_name = default_group_name()
        self.groupEdit = QLineEdit(group_name)
        self.groupEdit.setToolTip(tr(
            "Name of the group created in the Layers panel. Subgroups \"{0}\", \"{1}\" and \"{2}\" are made in it.",
            "レイヤーパネルに作るグループの名前。中に「{0}」「{1}」「{2}」の小グループを作ります。",
        ).format(admin_group_name(), bv_group_name(), fgd_group_name()))
        form.addRow(tr("Group name", "グループ名"), self.groupEdit)

        options = QHBoxLayout()
        self.skipCheckbox = QCheckBox(tr("Skip up-to-date data", "最新のものは取り直さない"))
        self.skipCheckbox.setChecked(QSettings().value(SETTINGS + "skip_current", True, type=bool))
        self.skipCheckbox.toggled.connect(self._update_summary)
        options.addWidget(self.skipCheckbox)
        self.placeCheckbox = QCheckBox(tr("Place layers after fetching", "取得後にレイヤーへ配置する"))
        self.placeCheckbox.setChecked(QSettings().value(SETTINGS + "place_layers", True, type=bool))
        options.addWidget(self.placeCheckbox)
        options.addStretch(1)
        self.sizeLabel = QLabel("")
        self.sizeLabel.setStyleSheet("color:#555;")
        options.addWidget(self.sizeLabel)
        form.addRow("", options)
        return box

    def _build_progress_area(self):
        """実行の区域。待機中は取得の見込み、取得中は進み具合を出し、右のボタンは取得と中止が入れ替わる"""
        area = QWidget()
        column = QVBoxLayout(area)
        column.setContentsMargins(0, 0, 0, 0)

        action = QFrame()
        action.setFrameShape(QFrame.Shape.StyledPanel)
        action_row = QHBoxLayout(action)
        # 文の列は4行分の高さを確保し、それより多いときは伸びる（中身が入れ替わっても区域の高さが跳ねないように）
        texts_widget = QWidget()
        texts_widget.setMinimumHeight(self.fontMetrics().lineSpacing() * ACTION_MIN_LINES)
        texts = QVBoxLayout(texts_widget)
        texts.setContentsMargins(0, 0, 0, 0)
        # 文（見込み・状態の行）はいつも上から並べ、進捗バーだけを一番下に置く（右の列の一番下の取得・中止と
        # 同じ段に並ぶように）。間は伸び縮みする空き。下に詰めると状態の行が中ほどの段に来てしまった
        # 待機中：何が起きるか（件数・大きさ、押せないときはその理由）
        self.planLabel = QLabel("")
        self.planLabel.setWordWrap(True)
        texts.addWidget(self.planLabel)
        # 取得中の段階と、終わったあとの結果
        self.stageLabel = QLabel("")
        self.stageLabel.setWordWrap(True)
        self.stageLabel.setStyleSheet("font-weight:bold;")
        self.stageLabel.setVisible(False)
        texts.addWidget(self.stageLabel)
        # 折り返す文はボタンの横で最小の幅まで縮められたので、横に広がるようにする
        for label in (self.planLabel, self.stageLabel):
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            label.setMinimumWidth(360)
        texts.addStretch(1)
        bars = QHBoxLayout()
        self.progressBar = QProgressBar()
        self.progressBar.setFormat(tr("Meshes %v / %m", "メッシュ %v / %m"))
        bars.addWidget(self.progressBar, 3)
        self.fileBar = QProgressBar()
        self.fileBar.setFormat(tr("Current step %p%", "今の作業 %p%"))
        bars.addWidget(self.fileBar, 2)
        # 地図の塗りの凡例。進捗バーと同じ段に置き、進捗バーが出ている間は隠す（eventFilter）
        # 地図の凡例の段：プレビュー地図のチェック、地図の塗りの凡例（どちらも地図の見え方に関わるもの）
        self.mapLegend = QWidget()
        legend = _legend_row(tr("Map:", "地図："), (
            (COLOR_MAP_FULL, tr("All checked contents stored", "チェックした内容がそろっている")),
            (COLOR_MAP_PART, tr("Partly stored", "一部だけ"))))
        legend.insertWidget(0, self.previewCheckbox)
        legend.insertSpacing(1, 16)
        legend.setContentsMargins(0, 0, 0, 0)
        self.mapLegend.setLayout(legend)
        self.mapLegend.setFixedHeight(self.progressBar.sizeHint().height())
        bars.addWidget(self.mapLegend, 1)
        texts.addLayout(bars)
        for bar in (self.progressBar, self.fileBar):
            bar.setVisible(False)
        self.progressBar.installEventFilter(self)
        # 保存先の読み込み・最新の状況の問い合わせでは、進捗バーの値を動かして見せる（取得のときは使わない）
        self._barAnimation = QPropertyAnimation(self.progressBar, b"value", self)
        self._barAnimation.finished.connect(self._on_bar_animation_finished)
        action_row.addWidget(texts_widget, 1)

        # 取得・中止は同じ場所で入れ替わる。標準のボタンに文字だけ（アイコンは付けない。色は下でパレットで付ける）
        self.fetchButton = QPushButton(tr("Fetch", "取得"))
        self.fetchButton.clicked.connect(self._start_fetch)
        self.cancelButton = QPushButton(tr("Stop", "中止"))
        self.cancelButton.clicked.connect(self._cancel_fetch)
        self.cancelButton.setVisible(False)
        # レイヤーへの配置と、配置する範囲の選択も、取得と同じ操作の列に置く
        self.placeButton = QPushButton(tr("Place layers", "レイヤーへ配置"))
        self.placeButton.setToolTip(tr("Places the stored data in the Layers panel without fetching.",
                                       "保存先にあるデータを、取得せずにレイヤーパネルへ置きます。"))
        self.placeButton.clicked.connect(lambda _checked=False: self._place_layers())
        self.placeScope = QComboBox()
        self.placeScope.addItems([tr("Visible meshes only", "可視範囲のメッシュだけ"),
                                  tr("All stored areas", "取得済みの範囲すべて")])
        self.placeScope.setToolTip(tr("The area shown by the layers, also when placing them after fetching.",
                                      "レイヤーで見せる範囲。取得後に配置するときもこの範囲です。"))
        scope = QSettings().value(SETTINGS + "place_scope", PLACE_VISIBLE, type=int)
        self.placeScope.setCurrentIndex(scope if scope in (PLACE_VISIBLE, PLACE_ALL) else PLACE_VISIBLE)

        # 標準のボタンのまま、パレットで色を付ける（押せないときは標準の灰色）。範囲の選択は素の部品のまま
        _tint(self.fetchButton, ACTION_COLORS["fetch"])
        _tint(self.cancelButton, ACTION_COLORS["cancel"])
        _tint(self.placeButton, ACTION_COLORS["place"])
        # 上から 取得／レイヤーへ配置／配置する範囲（配置だけに効く）。取得してから配置する流れの順
        # （取得前に配置を押すと「保存先がまだない」になる）。取得中はこの3段を隠して中止だけを出す。
        # 隠したものは詰まり、下に寄せてあるので、中止は一番下の段（進捗バーと同じ段）に来る（_set_running）。
        # 幅はそろえて固定する（横に広がると見込みの文が細い列に押し込まれた）。高さは進捗バーと同じ
        actions_widget = QWidget()
        actions = QVBoxLayout(actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setAlignment(Qt.AlignmentFlag.AlignBottom)
        width = max(160, self.placeScope.sizeHint().width(), self.placeButton.sizeHint().width())
        row_height = self.progressBar.sizeHint().height()
        for widget in (self.fetchButton, self.placeButton, self.placeScope, self.cancelButton):
            widget.setFixedWidth(width)
            widget.setFixedHeight(row_height)
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            actions.addWidget(widget)
        # 取得中は中止の1段だけになるが、区域の高さが変わらないよう3段分の高さを確保しておく
        actions_widget.setMinimumHeight(row_height * 3 + max(actions.spacing(), 0) * 2)
        action_row.addWidget(actions_widget)
        column.addWidget(action)
        return area

    def _build_log_area(self):
        """記録の行（記録の開け閉め・マニュアル・言語）と記録の欄。窓の下の方に置く"""
        area = QWidget()
        column = QVBoxLayout(area)
        column.setContentsMargins(0, 0, 0, 0)
        toggle_row = QHBoxLayout()
        self.logToggle = QToolButton()
        self.logToggle.setText(tr("Log", "記録"))
        self.logToggle.setCheckable(True)
        self.logToggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.logToggle.setArrowType(Qt.ArrowType.RightArrow)
        self.logToggle.setAutoRaise(True)
        self.logToggle.toggled.connect(self._toggle_log)
        toggle_row.addWidget(self.logToggle)
        toggle_row.addStretch(1)
        # マニュアル（HTML）を、今の言語でブラウザに開く
        self.manualButton = QPushButton(tr("Manual", "マニュアル"))
        self.manualButton.clicked.connect(self._open_manual)
        toggle_row.addWidget(self.manualButton)
        # 今の言語を出し、押すと切り替える。記録の行の右端に置く（記録を開くと欄はこの行の下に伸びる）
        self.languageButton = QPushButton(tr("Language: English", "言語：日本語"))
        self.languageButton.setToolTip(tr("Switch to Japanese (the window is rebuilt).",
                                          "英語に切り替えます（窓を作り直します）。"))
        self.languageButton.clicked.connect(self._switch_language)
        toggle_row.addWidget(self.languageButton)
        column.addLayout(toggle_row)
        self.logEdit = QPlainTextEdit()
        self.logEdit.setReadOnly(True)
        # 開くときはこの高さの分だけ窓を伸ばす（ほかの区域を狭めない。_toggle_log）
        self.logEdit.setFixedHeight(LOG_HEIGHT)
        self.logEdit.setVisible(False)
        column.addWidget(self.logEdit)
        return area

    def _disable_auto_default(self):
        # Enter で勝手に押されないよう、どのボタンも既定のボタンにしない。
        # 閉じるボタンは置かない（窓の ×・Esc・Ctrl+W で閉じる。× と役目が重なるため）
        for button in (self.placeButton, self.fetchButton, self.cancelButton, self.manualButton, self.languageButton):
            button.setAutoDefault(False)

    def _open_manual(self):
        path = os.path.join(os.path.dirname(__file__), MANUAL_FILE)
        if not os.path.exists(path):
            QMessageBox.warning(self, self.windowTitle(), tr("The manual could not be found.",
                                                             "マニュアルが見つかりませんでした。"))
            return
        # ほかのプラグインと同じく、ファイルの URL をそのまま渡す。言語はブラウザの設定で決まり、マニュアルの中でも
        # 切り替えられる（URL に #lang=… を付けると、Flatpak の QGIS では開かなかった）
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ================= 使用データ（取得・配置・地図の塗りに使う項目） =================

    def _all_parents(self):
        parents = [self._fgd_root, self._bv_root]
        parents += [self._fgd_root.child(i) for i in range(self._fgd_root.childCount())]
        parents += self._bv_categories
        return parents

    def _counterpart(self, key):
        """基盤地図情報と最適化ベクトルタイルで同じ地物のもう一方"""
        kind, code = key
        if kind == "fgd" and code in FGD_TO_BV:
            return self._leaf_by_key.get(("bv", FGD_TO_BV[code]))
        if kind == "bv" and BV_BY_LAYER[code]["overlap"]:
            return self._leaf_by_key.get(("fgd", BV_BY_LAYER[code]["overlap"]))
        return None

    def _leaves(self):
        leaves = []
        for root in (self._fgd_root, self._bv_root):
            stack = [root]
            while stack:
                node = stack.pop()
                if node.childCount() == 0:
                    leaves.append(node)
                stack.extend(node.child(i) for i in range(node.childCount()))
        return leaves

    def _set_all(self, state):
        # 同じ地物はどちらか一方なので、すべて選ぶときは基盤地図情報を後に選び、基盤地図情報の方を残す
        for root in (self._bv_root, self._fgd_root):
            root.setCheckState(0, state)

    # ================= 使用データのロック（プロジェクトごと） =================

    def _checked_keys(self):
        keys = []
        for leaf in self._leaves():
            if leaf.checkState(0) == Qt.CheckState.Checked:
                keys.append("{0}:{1}".format(*leaf.data(0, ROLE)))
        return keys

    def _is_locked(self):
        return self.lockButton.isChecked()

    def _toggle_lock(self, locked):
        project = QgsProject.instance()
        if locked:
            keys = self._checked_keys()
            if not keys:
                self.lockButton.setChecked(False)
                QMessageBox.information(self, self.windowTitle(), tr(
                    "Check the data to use before locking.", "使用データにチェックを入れてからロックしてください。"))
                return
            project.writeEntry(PROJECT_SCOPE, PROJECT_LOCKED_KEY, keys)
        project.writeEntryBool(PROJECT_SCOPE, PROJECT_LOCK_KEY, bool(locked))
        self._update_lock_ui()

    def _apply_project_lock(self):
        """今のプロジェクトのロックを窓に移す。ロックしていれば、記録した構成のチェックにする"""
        project = QgsProject.instance()
        locked, _ok = project.readBoolEntry(PROJECT_SCOPE, PROJECT_LOCK_KEY, False)
        keys = self._locked_keys()
        locked = bool(locked and keys)
        if locked:
            self._set_checked_keys(keys)
        self.lockButton.setChecked(locked)
        self._update_lock_ui()
        self._fill_table()
        self._update_summary()
        self._draw_status()

    def _locked_keys(self):
        """ロックで最後に記録した構成（無ければ空）"""
        keys, _ok = QgsProject.instance().readListEntry(PROJECT_SCOPE, PROJECT_LOCKED_KEY, [])
        return list(keys)

    def _set_checked_keys(self, keys):
        wanted = set(keys)
        # 塗り直しは呼んだ側で1回だけ
        self._updating_tree = True
        try:
            for leaf in self._leaves():
                is_checked = "{0}:{1}".format(*leaf.data(0, ROLE)) in wanted
                leaf.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
        finally:
            self._updating_tree = False

    def _restore_locked(self):
        keys = self._locked_keys()
        if not keys:
            return
        answer = QMessageBox.question(
            self, self.windowTitle(), tr(
                "Returns the checks of \"Data to use\" to the configuration last recorded by the lock.\n"
                "The current checks are not kept. The lock stays off.",
                "使用データのチェックを、ロックで最後に記録した構成に戻します。\n"
                "今のチェックは残りません。ロックは外れたままです。"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Ok)
        if answer != QMessageBox.StandardButton.Ok:
            return
        self._set_checked_keys(keys)
        self._fill_table()
        self._update_summary()
        self._draw_status()

    def _update_lock_ui(self):
        """ロック中は、使用データのチェックと「すべて選ぶ」「すべて外す」を押せなくする（木は送れるまま）"""
        locked = self._is_locked()
        self.lockButton.setText(tr("Locked", "ロック中") if locked else tr("Lock", "ロック"))
        running = getattr(self, "_fetch_thread", None) is not None
        for button in self._select_buttons:
            button.setEnabled(not locked and not running)
        # 復元はロックを外しているときだけ（ロック中はすでに記録した構成）。記録が無ければ押せない
        self.restoreButton.setEnabled(not locked and not running and bool(self._locked_keys()))
        flag = Qt.ItemFlag.ItemIsEnabled
        self._updating_tree = True
        try:
            for root in (self._fgd_root, self._bv_root):
                stack = [root]
                while stack:
                    node = stack.pop()
                    node.setFlags(node.flags() & ~flag if locked else node.flags() | flag)
                    stack.extend(node.child(i) for i in range(node.childCount()))
        finally:
            self._updating_tree = False

    def _on_tree_changed(self, item, _column):
        # 同じ地物の一方に印を付けたら、もう一方を外す（親をまとめて選んだときも子ごとに呼ばれる）
        key = item.data(0, ROLE)
        if key and key[0] in ("fgd", "bv") and item.checkState(0) == Qt.CheckState.Checked:
            other = self._counterpart(key)
            if other is not None and other.checkState(0) != Qt.CheckState.Unchecked:
                other.setCheckState(0, Qt.CheckState.Unchecked)
        if self._updating_tree:
            return
        self._updating_tree = True
        try:
            self._fill_table()
            self._update_summary()
            self._draw_status()
        finally:
            self._updating_tree = False

    def _checked_fgd_layers(self):
        """{type_code: [レイヤー名...]}"""
        selected = {}
        for leaf in self._leaves():
            kind, code = leaf.data(0, ROLE)
            if kind == "fgd" and leaf.checkState(0) == Qt.CheckState.Checked:
                type_code = next(t["code"] for t in FGD_TYPES if code in dict(t["layers"]))
                selected.setdefault(type_code, []).append(code)
        return selected

    def _checked_bv_items(self):
        names = {leaf.data(0, ROLE)[1] for leaf in self._leaves()
                 if leaf.data(0, ROLE)[0] == "bv" and leaf.checkState(0) == Qt.CheckState.Checked}
        return [item for item in BV_ITEMS if item["source_layer"] in names]

    # ================= ログイン =================

    def _update_login_state(self):
        logged_in = self.session is not None
        self.loginLamp.setStyleSheet("color:{0}; font-size:16px;".format("#2e9d3a" if logged_in else "#b0b0b0"))
        if logged_in:
            self.loginLabel.setText(tr("Logged in ({0})", "ログインしています（{0}）").format(self.session_user))
        else:
            saved = CredentialsManager().load()
            note = tr(" (the saved ID/password will be filled in)", "（保存したID・パスワードで自動入力します）") \
                if saved["auto_fill"] and saved["username"] else ""
            self.loginLabel.setText(tr("Not logged in. Needed to download the Fundamental Geospatial Data.",
                                       "ログインしていません。基盤地図情報のダウンロードに必要です。") + note)
        self.loginButton.setEnabled(not logged_in)
        self.logoutButton.setEnabled(logged_in)
        self.forgetButton.setEnabled(CredentialsManager().has_saved())

    def _login(self):
        dialog = LoginDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.session is not None:
            self.session = dialog.session
            self.session_user = dialog.username()
            self._log(tr("Logged in ({0}).", "ログインしました（{0}）。").format(self.session_user))
        self._update_login_state()
        return self.session is not None

    def _logout(self):
        # サービス側のログアウトは呼ばず、このプラグインが持つログイン状態を捨てる
        self.session = None
        self.session_user = ""
        self._log(tr("Discarded the login state.", "ログイン状態を破棄しました。"))
        self._update_login_state()

    def _forget_credentials(self):
        answer = QMessageBox.question(self, self.windowTitle(), tr(
            "Delete the login ID and password saved for this plugin?",
            "このプラグインに保存したログインID・パスワードを消しますか？"))
        if answer == QMessageBox.StandardButton.Yes:
            CredentialsManager().clear()
            self._update_login_state()

    # ================= 表示範囲とメッシュ =================

    def showEvent(self, event):
        super().showEvent(event)
        if not self._canvas_connected:
            self.canvas.extentsChanged.connect(self._update_meshes)
            self.canvas.destinationCrsChanged.connect(self._update_meshes)
            self._canvas_connected = True
        self._open = True
        if not self._fitted:
            # 初めて表示したときだけ、部品が入りきる最小の大きさにする（以後は利用者が変えた大きさのまま）
            self._fitted = True
            QTimer.singleShot(0, self._fit_minimum)
        # 保存先はプロジェクトに記録したもの（無ければプロジェクトの隣の既定の場所）
        self._resolve_project_path()
        # 窓を先に出す。プレビュー地図は出たあとに置き、保存先の記録は別スレッドで読む（読み終わったら描き直す）
        QTimer.singleShot(0, self._sync_preview)
        self._invalidate_stored()
        self._update_meshes(force=True)
        # 保存先が前回から変わっていなければ前回の結果がすぐ使えるので、ここで塗る（読み直すときは読み終えてから）
        self._draw_status()
        self._update_size()

    def hideEvent(self, event):
        self._disconnect_canvas()
        if self.rubber is not None:
            self.rubber.reset(Qgis.GeometryType.Line)
        for band in self.statusRubbers.values():
            band.reset(Qgis.GeometryType.Polygon)
        super().hideEvent(event)

    # ================= プレビュー地図 =================

    def _preview_layer(self):
        if self._preview_id is None:
            return None
        return QgsProject.instance().mapLayer(self._preview_id)

    def _sync_preview(self, _checked=None):
        """チェックに合わせて、レイヤーパネルのいちばん下にプレビュー地図を置く・外す"""
        # 最小化しても外さない（窓を閉じたときに外す）
        wanted = self.previewCheckbox.isChecked() and self._open
        layer = self._preview_layer()
        if wanted and layer is None:
            layer = QgsRasterLayer(PREVIEW_URI, preview_name(), "wms")
            if not layer.isValid():
                self._log(tr("Could not open the preview map.", "プレビュー地図を開けませんでした。"))
                return
            layer.setCustomProperty(PREVIEW_PROPERTY, True)
            metadata = QgsLayerMetadata(layer.metadata())
            metadata.setRights([rights_text(preview_attribution(), PREVIEW_SOURCE_PAGE)])
            layer.setMetadata(metadata)
            project = QgsProject.instance()
            project.addMapLayer(layer, False)
            root = project.layerTreeRoot()
            root.insertLayer(len(root.children()), layer)
            self._preview_id = layer.id()
            self._refresh_canvas_later()
        elif not wanted:
            self._remove_preview()

    def _remove_preview(self):
        layer = self._preview_layer()
        if layer is not None:
            QgsProject.instance().removeMapLayer(layer.id())
            self._refresh_canvas_later()
        self._preview_id = None

    def _refresh_canvas_later(self):
        # レイヤーを足す・外すだけでは地図が描き直されず、地図を動かすまで変わらなかった。
        # レイヤーパネルから地図へレイヤーの並びが渡ったあとで描き直す
        QTimer.singleShot(0, self.canvas.refresh)

    def _disconnect_canvas(self):
        if self._canvas_connected:
            self.canvas.extentsChanged.disconnect(self._update_meshes)
            self.canvas.destinationCrsChanged.disconnect(self._update_meshes)
            self._canvas_connected = False

    def _canvas_crs(self):
        return self.canvas.mapSettings().destinationCrs()

    def _update_meshes(self, force=False):
        to_lonlat = QgsCoordinateTransform(
            self._canvas_crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        try:
            rect = to_lonlat.transformBoundingBox(self.canvas.extent())
        except QgsCsException:
            rect = None
        meshes = []
        self._too_wide = False
        if rect is not None and not rect.isEmpty():
            # 日本の範囲だけを見る（2次メッシュの計算が成り立つ範囲）
            lon0, lat0 = max(rect.xMinimum(), 122.0), max(rect.yMinimum(), 20.0)
            lon1, lat1 = min(rect.xMaximum(), 154.0), min(rect.yMaximum(), 46.0)
            if lon0 < lon1 and lat0 < lat1:
                # 日本全体が見えるほど広いとメッシュが数万になるので数えない（約 3800 メッシュまで）
                if (lon1 - lon0) * (lat1 - lat0) < 40:
                    meshes = fgd_api.mesh_codes_for_extent(lon0, lat0, lon1, lat1)
                else:
                    self._too_wide = True
        changed = meshes != self._meshes
        self._meshes = meshes
        self._draw_meshes()
        if changed or force:
            self._fill_table()
            self._update_summary()
            unknown = [m for m in meshes if m not in self._listing_by_mesh]
            if unknown and len(unknown) <= AUTO_LIST_MESHES:
                self._listTimer.start()

    def _draw_meshes(self):
        if self.rubber is None:
            return
        self.rubber.reset(Qgis.GeometryType.Line)
        self._mesh_bounds = None
        if not self._meshes:
            return
        lines = []
        bounds = None
        for mesh in self._meshes:
            lon0, lat0, lon1, lat1 = fgd_api.mesh2_bounds(mesh)
            lines.append([QgsPointXY(lon0, lat0), QgsPointXY(lon1, lat0), QgsPointXY(lon1, lat1),
                          QgsPointXY(lon0, lat1), QgsPointXY(lon0, lat0)])
            bounds = (lon0, lat0, lon1, lat1) if bounds is None else (
                min(bounds[0], lon0), min(bounds[1], lat0), max(bounds[2], lon1), max(bounds[3], lat1))
        self._mesh_bounds = bounds
        if not self._open:
            # 窓を閉じたあとは枠を描かない（範囲の計算だけ残す）
            return
        geometry = QgsGeometry.fromMultiPolylineXY(lines)
        to_canvas = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"), self._canvas_crs(), QgsProject.instance())
        try:
            geometry.transform(to_canvas)
        except QgsCsException:
            return
        self.rubber.setToGeometry(geometry, None)

    def _bv_tile_count(self):
        # 範囲の判定は2次メッシュに統一する。可視範囲のメッシュは矩形に並ぶので、覆うタイルはその外枠のタイル
        if self._mesh_bounds is None:
            return 0
        x0, x1, y0, y1 = tile_range(*self._mesh_bounds, BV_ZOOM)
        return (x1 - x0 + 1) * (y1 - y0 + 1)

    # ================= 取得済みの範囲（地図の塗り） =================

    def _stored_state(self):
        """{"fgd": {(mesh, type_code): data_date}, "bv": {source_layer: {メッシュ: タイル数}}}。

        読むのは別スレッド（StoredThread）。読み終わるまでは空を返し、読み終わったら表・見込み・地図を描き直す"""
        if self._stored_cache is None:
            self._load_stored()
            if self._stored_cache is None:
                return {"fgd": {}, "bv": {}}
        return self._stored_cache

    def _stored_loading(self):
        return self._stored_cache is None

    def _load_stored(self):
        if self._stored_thread is not None:
            # 読んでいる途中。読み直しが要るのは保存先が変わった・書き込んだとき（_invalidate_stored）だけ。
            # 読み終わるのを待つ間に記録を求められても、もう一度読むことはしない（1回開くたびに2回読んでいた）
            return
        # 保存先が前回読んだときから変わっていなければ（更新日時と大きさが同じなら）、前回の結果を使う
        key = _file_key(self._path())
        if key is not None and self._stored_last is not None and self._stored_last[0] == key:
            self._stored_cache = self._stored_last[1]
            return
        self._begin_activity("stored", 1)
        self._stored_thread = StoredThread(self._path())
        self._stored_thread.progress.connect(lambda done, total: self._activity_progress("stored", done, total))
        self._stored_thread.finished.connect(self._on_stored_loaded)
        self._stored_thread.start()

    def _on_stored_loaded(self):
        thread = self._stored_thread
        self._stored_thread = None
        if self._stored_again:
            # 読んでいる間に保存先が変わったり取得が終わったりしたので、読み直す
            self._stored_again = False
            self._load_stored()
            return
        self._stored_cache = thread.results
        # 読み終えた時点のファイルの状態を覚える（前の版の記録にメッシュ番号を足したときはファイルが変わっている）
        self._stored_last = (_file_key(thread.path), thread.results)
        self._end_activity("stored")
        self._fill_table()
        self._update_summary()
        self._draw_status()

    def _invalidate_stored(self):
        """保存先が変わった・書き込んだので、取得の記録を読み直す"""
        self._stored_cache = None
        if self._stored_thread is not None:
            self._stored_again = True

    def _center_tile_count(self, mesh):
        count = self._center_tile_counts.get(mesh)
        if count is None:
            count = 0
            for x, y in mesh_tiles(mesh):
                lon, lat = tile_center_lonlat(x, y, BV_ZOOM)
                if fgd_api.latlon_to_mesh2(lat, lon) == mesh:
                    count += 1
            self._center_tile_counts[mesh] = count
        return count

    def _mesh_status(self):
        """{メッシュ: "full" | "part"}。取得済みの範囲すべてを、今のチェックに対して判定する"""
        state = self._stored_state()
        types = set(self._checked_fgd_layers())
        names = [i["source_layer"] for i in self._checked_bv_items()]
        candidates = {mesh for mesh, type_code in state["fgd"] if type_code in types}
        for name in names:
            candidates |= set(state["bv"].get(name, {}))
        status = {}
        for mesh in candidates:
            listed = self._listing_by_mesh.get(mesh)
            latest = {}
            for item in listed or []:
                latest.setdefault(item["type_code"], fgd_api.item_date(item))
            have = 0
            for type_code in types:
                saved = state["fgd"].get((mesh, type_code))
                # 一覧を問い合わせたメッシュでは、新しいデータがあれば「そろっていない」とする
                if saved is not None and (listed is None or latest.get(type_code, saved) == saved):
                    have += 1
            expected = self._center_tile_count(mesh) if names else 0
            for name in names:
                if state["bv"].get(name, {}).get(mesh, 0) >= expected:
                    have += 1
            total = len(types) + len(names)
            if have:
                status[mesh] = "full" if have == total else "part"
        return status

    def _draw_status(self):
        if not self.statusRubbers:
            return
        if not self._open:
            # 窓を閉じたあとに別スレッド（保存先の読み込み・最新の状況・取得）が終わっても地図に描かない
            for band in self.statusRubbers.values():
                band.reset(Qgis.GeometryType.Polygon)
            return
        groups = {"full": [], "part": []}
        for mesh, status in self._mesh_status().items():
            lon0, lat0, lon1, lat1 = fgd_api.mesh2_bounds(mesh)
            groups[status].append([[QgsPointXY(lon0, lat0), QgsPointXY(lon1, lat0), QgsPointXY(lon1, lat1),
                                    QgsPointXY(lon0, lat1), QgsPointXY(lon0, lat0)]])
        to_canvas = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"), self._canvas_crs(), QgsProject.instance())
        for status, band in self.statusRubbers.items():
            band.reset(Qgis.GeometryType.Polygon)
            if not groups[status]:
                continue
            geometry = QgsGeometry.fromMultiPolygonXY(groups[status])
            try:
                geometry.transform(to_canvas)
            except QgsCsException:
                continue
            band.setToGeometry(geometry, None)

    # ================= 最新データの一覧 =================

    def _start_list(self, refresh=False):
        """最新の状況を問い合わせる。refresh のときは可視範囲のメッシュすべて、ほかは未確認のメッシュだけ"""
        self._listTimer.stop()
        meshes = self._meshes if refresh else [m for m in self._meshes if m not in self._listing_by_mesh]
        if not meshes:
            return
        if self._list_thread is not None:
            self._list_again = True
            return
        self.listButton.setEnabled(False)
        self.listButton.setText(tr("Checking…", "確認しています…"))
        self._begin_activity("list", len(meshes))
        self._list_thread = ListThread(meshes)
        self._list_thread.progress.connect(lambda done, total: self._activity_progress("list", done, total))
        self._list_thread.finished.connect(self._on_list_finished)
        self._list_thread.start()

    # ================= 進み具合（保存先の読み込み・最新の状況の問い合わせ） =================
    #
    # どちらも実行の区域の進捗バーに出す。出している間は見込みなどほかの文をどけ、処理中のものだけを見せる。
    # 同時に走るときは ACTIVITY_ORDER の順（保存先の読み込みが先。読み終わるまで取得を押せないため）に見せる。
    # 取得中は取得の進み具合を優先し、これらは出さない。

    def _activity_texts(self, kind):
        """(状態の行, 進捗バーの書式)"""
        if kind == "stored":
            return (tr("Reading the GeoPackage…", "保存先を読んでいます…"),
                    tr("GeoPackage %v / %m records", "保存先 %v / %m 件"))
        return (tr("Querying the latest status…", "最新の状況を問い合わせています…"),
                tr("Latest status %v / %m meshes", "最新の状況 %v / %m メッシュ"))

    def _begin_activity(self, kind, total):
        if self._activity_end == kind:
            # 最後まで進めている途中で同じ処理がまた始まった（読み直しなど）
            self._activity_end = None
            self._barAnimation.stop()
        self._activities[kind] = {"value": 0, "max": max(total, 1), "done": False, "shown": 0.0}
        if self._activity_shown == kind:
            self._activity_shown = None
        self._show_next_activity()

    def _activity_progress(self, kind, done, total):
        info = self._activities.get(kind)
        if info is None:
            return
        info["value"], info["max"] = done, max(total, 1)
        if self._activity_shown == kind and self._activity_end is None:
            self.progressBar.setMaximum(info["max"])
            self._animate_bar(done, LIST_STEP_ANIMATION)

    def _end_activity(self, kind):
        info = self._activities.get(kind)
        if info is None:
            return
        if self._fetch_thread is not None:
            # 取得中に終わったものは見せない
            self._activities.pop(kind, None)
            return
        info["done"] = True
        if self._activity_shown == kind:
            self._finish_shown_activity()

    def _finish_shown_activity(self):
        # すぐ終わっても進み具合が見えるよう、見せ始めてから最低 LIST_MIN_SHOW 秒かけて最後まで進める。
        # 進み終えたら（_on_bar_animation_finished）次の処理か、前の表示に戻す
        info = self._activities[self._activity_shown]
        remaining = LIST_MIN_SHOW[self._activity_shown] - (time.monotonic() - info["shown"])
        self._activity_end = self._activity_shown
        self.progressBar.setMaximum(info["max"])
        self._animate_bar(info["max"], max(remaining, LIST_STEP_ANIMATION))

    def _on_bar_animation_finished(self):
        kind = self._activity_end
        self._activity_end = None
        if kind is None:
            return  # 途中の区切りのアニメーション
        self._activities.pop(kind, None)
        self._activity_shown = None
        self._show_next_activity()

    def _show_next_activity(self):
        if self._fetch_thread is not None or self._activity_end is not None:
            # 取得中、または今のものを最後まで進めている途中（終わったらここへ戻る）
            return
        kind = next((k for k in ACTIVITY_ORDER if k in self._activities), None)
        if kind is None:
            self._restore_after_activity()
            return
        if kind == self._activity_shown:
            return
        if not self._activity_display:
            self._stage_before_activity = self.stageLabel.text()
            self._activity_display = True
        self._activity_shown = kind
        info = self._activities[kind]
        info["shown"] = time.monotonic()
        stage, bar_format = self._activity_texts(kind)
        self.planLabel.setVisible(False)
        self._set_stage(stage)
        self._barAnimation.stop()
        self.progressBar.setFormat(bar_format)
        self.progressBar.setRange(0, info["max"])
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)
        if info["done"]:
            self._finish_shown_activity()
        elif info["value"]:
            self._animate_bar(info["value"], LIST_STEP_ANIMATION)

    def _restore_after_activity(self):
        """進み具合をどけ、前の表示（見込み・前回の結果）に戻す"""
        if not self._activity_display:
            return
        self._activity_display = False
        self.progressBar.setVisible(False)
        self.progressBar.setFormat(tr("Meshes %v / %m", "メッシュ %v / %m"))
        self.planLabel.setVisible(True)
        self._set_stage(self._stage_before_activity)

    def _animate_bar(self, target, duration):
        """進捗バーを、今の値から target まで duration 秒かけて動かす（値を飛ばさない）"""
        self._barAnimation.stop()
        self._barAnimation.setStartValue(self.progressBar.value())
        self._barAnimation.setEndValue(target)
        self._barAnimation.setDuration(max(1, int(duration * 1000)))
        self._barAnimation.start()

    def _reset_activity_display(self):
        """取得を始めるので、進み具合の表示をやめる（走っている処理は続き、取得中に終わったものは見せない）"""
        self._barAnimation.stop()
        if self._activity_end is not None:
            self._activities.pop(self._activity_end, None)
            self._activity_end = None
        self._activity_shown = None
        self._activity_display = False

    def _on_list_finished(self):
        thread = self._list_thread
        self._list_thread = None
        self._end_activity("list")
        self.listButton.setEnabled(True)
        self.listButton.setText(tr("Check latest status", "最新の状況を確認"))
        if thread.error:
            self._log(tr("Could not check the list of the latest data: ", "最新データの一覧を確認できませんでした：")
                      + thread.error)
        else:
            for mesh in thread.meshes:
                self._listing_by_mesh[mesh] = []
            for item in thread.results:
                self._listing_by_mesh.setdefault(item.get("place_code"), []).append(item)
        self._fill_table()
        self._update_summary()
        self._draw_status()
        if self._list_again:
            self._list_again = False
            self._start_list()

    def _listing_for_current(self):
        """可視範囲のメッシュの一覧。まだ問い合わせていないメッシュがあれば None"""
        if not self._meshes or any(m not in self._listing_by_mesh for m in self._meshes):
            return None
        return [i for m in self._meshes for i in self._listing_by_mesh[m]]

    # ================= 状況の表 =================

    def _stored_dates(self):
        return self._stored_state()["fgd"]

    def _fill_table(self):
        meshes = self._meshes if len(self._meshes) <= TABLE_MAX_ROWS else []
        current = self._listing_for_current()
        listing = current or []
        latest = {}
        for item in listing:
            latest.setdefault((item["place_code"], item["type_code"]), []).append(item)
        stored = self._stored_dates()
        checked_types = set(self._checked_fgd_layers())
        stored_label = tr("Stored: {0}", "保存済み：{0}")

        # 欄の幅を「中身に合わせる」のままだと、セルを入れるたびに幅を測り直して遅かった（182 メッシュで十数秒）。
        # 入れ終えるまで止め、最後に一度だけ合わせる
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setUpdatesEnabled(False)
        try:
            self._fill_rows(meshes, latest, stored, checked_types, stored_label, current is not None)
        finally:
            self.table.setUpdatesEnabled(True)
        self.table.resizeColumnsToContents()
        self._content_widths = [self.table.columnWidth(c) for c in range(self.table.columnCount())]
        self._fit_columns()
        for column, type_info in enumerate(FGD_TYPES, start=1):
            header = self.table.horizontalHeaderItem(column)
            header.setForeground(QBrush(QColor("black") if type_info["code"] in checked_types else COLOR_GRAY_TEXT))
        self.table.resizeRowsToContents()

    def _fit_columns(self):
        """中身に合わせた幅に、表の余りを全部の欄へ均等に足す。余りが無ければ中身に合わせた幅のまま（横に送る）"""
        widths = self._content_widths
        if not widths or len(widths) != self.table.columnCount():
            return
        spare = self.table.viewport().width() - sum(widths)
        extra, rest = divmod(max(spare, 0), len(widths))
        for column, width in enumerate(widths):
            # 割り切れない分は前の欄から1つずつ足し、右端までぴったり埋める
            self.table.setColumnWidth(column, width + extra + (1 if column < rest else 0))

    def eventFilter(self, watched, event):
        # 表の中の表示部分の幅が変わったら（窓の大きさ・分割・縦のスクロールバーの出入り）、余りを配り直す
        # 窓を組み立てている途中にも届くので、まだ作っていない部品は見ない
        table = getattr(self, "table", None)
        bar = getattr(self, "progressBar", None)
        if table is not None and watched is table.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_columns()
        # 進捗バーが出ている間は地図の凡例を隠し、隠れたら凡例を出す（同じ段を入れ替える）
        if bar is not None and watched is bar and event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self.mapLegend.setVisible(event.type() == QEvent.Type.Hide)
        return super().eventFilter(watched, event)

    def _fill_rows(self, meshes, latest, stored, checked_types, stored_label, listed):
        self.table.setRowCount(len(meshes))
        for row, mesh in enumerate(meshes):
            mesh_item = QTableWidgetItem(mesh)
            mesh_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, mesh_item)
            for column, type_info in enumerate(FGD_TYPES, start=1):
                key = (mesh, type_info["code"])
                items = latest.get(key)
                saved = stored.get(key)
                cell = QTableWidgetItem()
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tips = []
                if items:
                    date = fgd_api.item_date(items[0])
                    size_mb = sum(fgd_api.item_size(i) for i in items) / 1024 / 1024
                    tips.append(tr("Latest: {0} ({1:.1f} MB)", "最新：{0}（{1:.1f} MB）").format(date, size_mb))
                    tips.extend(i["file_name"] for i in items)
                    if saved == date:
                        cell.setText(_short_date(date) + "\n" + tr("Stored", "保存済み"))
                        cell.setBackground(QBrush(COLOR_CURRENT))
                    elif saved:
                        cell.setText(_short_date(date) + "\n" + tr("Newer", "更新あり"))
                        cell.setBackground(QBrush(COLOR_UPDATE))
                        tips.append(stored_label.format(saved))
                    else:
                        cell.setText(_short_date(date) + "\n" + tr("Not fetched", "未取得"))
                elif listed:
                    cell.setText("—")
                    cell.setBackground(QBrush(COLOR_NONE))
                    tips.append(tr("No data for this mesh", "このメッシュにはデータがありません"))
                    if saved:
                        tips.append(stored_label.format(saved))
                elif saved == "":
                    # 前に取得したとき、このメッシュにはデータが無かった
                    cell.setText("—")
                    cell.setBackground(QBrush(COLOR_NONE))
                    tips.append(tr("There was no data when it was fetched (latest status not checked)",
                                   "取得したときはデータがありませんでした（最新の状況は未確認です）"))
                else:
                    cell.setText((tr("Stored", "保存済み") + "\n" + _short_date(saved)) if saved else "…")
                    tips.append(tr("Latest status not checked", "最新の状況は未確認です"))
                if type_info["code"] not in checked_types:
                    cell.setForeground(QBrush(COLOR_GRAY_TEXT))
                cell.setToolTip("\n".join(tips))
                self.table.setItem(row, column, cell)

    def _update_summary(self):
        meshes = self._meshes
        if self._too_wide:
            self.meshLabel.setText(tr("The map view is too wide to count the meshes. Zoom in.",
                                      "表示範囲が広すぎてメッシュを数えられません。地図を拡大してください。"))
        elif not meshes:
            self.meshLabel.setText(tr("The map view does not cover Japan.", "表示範囲が日本の範囲に掛かっていません。"))
        else:
            text = tr(
                "2nd-level meshes (about 10 km square) covering the map view: {0} (orange frames on the map). "
                "Optimized vector tiles for the same area at zoom {1}: {2}.",
                "表示範囲に掛かる2次メッシュ（約10km四方）：{0} 枚（地図の橙の枠）。"
                "最適化ベクトルタイルは同じ範囲をズーム{1}で {2} 枚。",
            ).format(len(meshes), BV_ZOOM, self._bv_tile_count())
            if len(meshes) > TABLE_MAX_ROWS:
                text += "\n" + tr("More than {0} meshes, so the table is left out (see the colours on the map).",
                                  "メッシュが {0} 枚を超えるので表は省いています（地図の色で見てください）。").format(
                    TABLE_MAX_ROWS)
            unknown = sum(1 for m in meshes if m not in self._listing_by_mesh)
            if unknown > AUTO_LIST_MESHES:
                text += "\n" + tr(
                    "The latest status is not queried automatically ({0} meshes unchecked). "
                    "Use \"Check latest status\".",
                    "最新の状況は自動では問い合わせません（{0} 枚が未確認）。「最新の状況を確認」で問い合わせます。",
                ).format(unknown)
            self.meshLabel.setText(text)

        lines = []
        listing = self._listing_for_current()
        fgd_layers = self._checked_fgd_layers()
        if fgd_layers and listing is not None:
            plan = plan_fgd_downloads(listing, self._stored_dates(), set(fgd_layers), self.skipCheckbox.isChecked())
            size_mb = sum(fgd_api.item_size(i) for _m, _t, items in plan for i in items) / 1024 / 1024
            if plan:
                lines.append(tr("Fundamental Geospatial Data: fetching {0} meshes, {1} items (about {2:.1f} MB).",
                                "基盤地図情報：{0} メッシュ・{1} 件（約 {2:.1f} MB）を取得します。").format(
                    len({m for m, _t, _i in plan}), len(plan), size_mb))
            else:
                lines.append(tr("Fundamental Geospatial Data: nothing needs fetching.",
                                "基盤地図情報：取得の必要なものはありません。"))
        elif fgd_layers and meshes:
            lines.append(tr("Fundamental Geospatial Data: check the latest status to see how many items are fetched.",
                            "基盤地図情報：最新の状況を確認すると、取得する件数を表示します。"))
        tile_count = self._bv_tile_count()
        if self._checked_bv_items() and tile_count:
            if self.skipCheckbox.isChecked():
                lines.append(tr("Optimized vector tiles: up to {0} (tiles stored from the same release are skipped).",
                                "最適化ベクトルタイル：最大 {0} 枚（同じ配信データで取得済みのタイルは飛ばします）。").format(
                    tile_count))
            else:
                lines.append(tr("Optimized vector tiles: {0}.", "最適化ベクトルタイル：{0} 枚。").format(tile_count))
        # 押せないときは、その理由を見込みの欄に出す
        reason = ""
        if not self._project_saved():
            # 保存先はプロジェクトの隣に作るので、先にプロジェクトを保存してもらう
            reason = tr("Save the project first. The GeoPackage is created in a folder next to the project file.",
                        "先にプロジェクトを保存してください。GeoPackage はプロジェクトの隣のフォルダに作ります。")
        elif self._stored_loading():
            # 読む前の空の記録で見込みを出さない
            reason = tr("Reading the GeoPackage…", "保存先を読んでいます…")
        elif not fgd_layers and not self._checked_bv_items():
            reason = tr("Check the data to use.", "使用データにチェックを入れてください。")
        elif not meshes:
            reason = self.meshLabel.text()
        elif not self._path():
            reason = tr("Specify the GeoPackage to save to.", "保存先の GeoPackage を指定してください。")
        if reason:
            lines = [reason]
        else:
            lines.insert(0, tr("{0} meshes in the map view.", "表示範囲の2次メッシュ {0} 枚。").format(len(meshes)))
            lines.append(tr("Fetching goes mesh by mesh. Stopping finishes the mesh being imported first.",
                            "取得はメッシュごとに進めます。中止すると、取り込み中のメッシュを終えてから止めます。"))
        self.planLabel.setText("\n".join(lines))
        self.fetchButton.setEnabled(not reason)

    # ================= 取得 =================

    def _path(self):
        path = self.pathEdit.text().strip()
        if path and not path.lower().endswith(".gpkg"):
            path += ".gpkg"
        return path

    def _choose_path(self):
        """保存先を選ぶ（別の場所の GeoPackage を使う・別の名前にする）。選んだらプロジェクトに記録する。選んだら True"""
        start = self._path() or self._default_project_path() or os.path.expanduser("~")
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("GeoPackage to save to", "保存先の GeoPackage"), start, "GeoPackage (*.gpkg)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return False
        if not path.lower().endswith(".gpkg"):
            path += ".gpkg"
        self.pathEdit.setText(path)
        self._on_path_changed()
        return True

    def _on_path_changed(self):
        """利用者が保存先を変えた（入力・選択）。プロジェクトに記録して読み直す"""
        self._record_path(self._path())
        self._refresh_for_path()

    def _refresh_for_path(self):
        self._invalidate_stored()
        self._fill_table()
        self._update_summary()
        self._draw_status()
        self._update_size()

    # ---- 保存先（プロジェクトごと） ----
    #
    # プロジェクトと同じ階層のフォルダ（DATA_DIR_NAME）の GeoPackage（DATA_FILE_NAME）を基本にし、使う保存先は
    # プロジェクトファイルに記録する（プロジェクトの中なら相対パスになり、フォルダごと移しても切れない）。
    # 既定の場所にすでにデータがあれば、共有データとして使うかを聞く。別の場所の GeoPackage も選べる。

    def _project_saved(self):
        return bool(QgsProject.instance().fileName())

    def _default_project_path(self):
        if not self._project_saved():
            return ""
        return os.path.join(QgsProject.instance().absolutePath(), DATA_DIR_NAME, DATA_FILE_NAME)

    def _recorded_path(self):
        value, _ok = QgsProject.instance().readEntry(PROJECT_SCOPE, PROJECT_KEY, "")
        return QgsProject.instance().pathResolver().readPath(value) if value else ""

    def _record_path(self, path):
        project = QgsProject.instance()
        if not path or not self._project_saved():
            return
        stored = project.pathResolver().writePath(path)
        old, _ok = project.readEntry(PROJECT_SCOPE, PROJECT_KEY, "")
        if old != stored:
            project.writeEntry(PROJECT_SCOPE, PROJECT_KEY, stored)

    def _apply_path(self, path):
        """保存先の欄を変える（プロジェクトには記録しない）"""
        self.pathEdit.setPlaceholderText(
            "" if self._project_saved() else tr("Save the project first; the GeoPackage is created next to it.",
                                                "プロジェクトを保存すると、その隣に作ります。"))
        if self.pathEdit.text() != path:
            self.pathEdit.setText(path)
            self._refresh_for_path()

    def _resolve_project_path(self, *_args):
        """今のプロジェクトの保存先を欄に入れる。記録が無ければプロジェクトの隣の既定の場所にし、
        そこにすでにデータがあれば、共有データとして使うかを聞く（窓を開いたあとに）"""
        if not self._open:
            return
        self._apply_project_lock()
        recorded = self._recorded_path()
        if recorded:
            self._apply_path(recorded)
            return
        default = self._default_project_path()
        self._apply_path(default)
        if default and os.path.exists(default):
            QTimer.singleShot(0, self._ask_shared)

    def _ask_shared(self):
        path = self._path()
        if self._asking_shared or not self._open or not path or not os.path.exists(path) or self._recorded_path():
            return
        self._asking_shared = True
        try:
            answer = QMessageBox.question(self, self.windowTitle(), tr(
                "There is existing data:\n{0}\n\nUse it as shared data?",
                "既存のデータがあります：\n{0}\n\n共有データとして使用しますか？").format(path))
            if answer == QMessageBox.StandardButton.Yes:
                self._record_path(path)
                return
            QMessageBox.information(self, self.windowTitle(), tr(
                "Set another location, or another name.", "場所を設定するか、別の名前を設定してください。"))
            if not self._choose_path():
                # 選ばなかったときは、既存のデータへ書き込まないよう欄を空にする（取得の前に指定してもらう）
                self._apply_path("")
        finally:
            self._asking_shared = False

    def _update_size(self):
        """保存先の GeoPackage の大きさ。書き込み途中の分（-wal）があれば足す"""
        path = self._path()
        if not path or not os.path.exists(path):
            self.sizeLabel.setText(tr("GeoPackage: not created yet", "GeoPackage：まだありません"))
            return
        size = sum(os.path.getsize(p) for p in (path, path + "-wal") if os.path.exists(p))
        if size >= 1024 ** 3:
            text = "{0:.2f} GB".format(size / 1024 ** 3)
        else:
            text = "{0:.1f} MB".format(size / 1024 ** 2)
        self.sizeLabel.setText(tr("GeoPackage: ", "GeoPackage：") + text)

    def _save_settings(self):
        settings = QSettings()
        # 保存先はプロジェクトに記録する（_record_path）ので、ここでは覚えない
        settings.setValue(SETTINGS + "group_name", self.groupEdit.text().strip())
        settings.setValue(SETTINGS + "skip_current", self.skipCheckbox.isChecked())
        settings.setValue(SETTINGS + "place_layers", self.placeCheckbox.isChecked())
        settings.setValue(SETTINGS + "place_scope", self.placeScope.currentIndex())
        settings.setValue(SETTINGS + "preview_map", self.previewCheckbox.isChecked())
        keys = []
        for leaf in self._leaves():
            kind, code = leaf.data(0, ROLE)
            if leaf.checkState(0) == Qt.CheckState.Checked:
                keys.append("{0}:{1}".format(kind, code))
        settings.setValue(SETTINGS + "checked", keys)

    def _start_fetch(self):
        fgd_layers = self._checked_fgd_layers()
        bv_items = self._checked_bv_items()
        if not fgd_layers and not bv_items:
            QMessageBox.information(self, self.windowTitle(), tr("Check the data to use.",
                                                                 "使用データにチェックを入れてください。"))
            return
        if not self._meshes:
            QMessageBox.information(self, self.windowTitle(), self.meshLabel.text())
            return
        if not self._project_saved():
            QMessageBox.information(self, self.windowTitle(), tr(
                "Save the project first. The GeoPackage is created in a folder next to the project file.",
                "先にプロジェクトを保存してください。GeoPackage はプロジェクトの隣のフォルダに作ります。"))
            return
        path = self._path()
        if not path:
            QMessageBox.information(self, self.windowTitle(), tr("Specify the GeoPackage to save to.",
                                                                 "保存先の GeoPackage を指定してください。"))
            return
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            if os.path.abspath(path) == os.path.abspath(self._default_project_path()):
                # プロジェクトの隣のフォルダは、最初に取得するときに作る
                os.makedirs(folder, exist_ok=True)
            else:
                QMessageBox.warning(self, self.windowTitle(), tr("The folder to save to does not exist:\n{0}",
                                                                 "保存先のフォルダがありません：\n{0}").format(folder))
                return
        self.pathEdit.setText(path)
        self._record_path(path)
        listing = self._listing_for_current()
        plan = None
        if fgd_layers and listing is not None:
            plan = plan_fgd_downloads(listing, self._stored_dates(), set(fgd_layers), self.skipCheckbox.isChecked())
        # 上限は設けず、多いときだけ確かめる
        tile_count = self._bv_tile_count() if bv_items else 0
        if len(self._meshes) > CONFIRM_MESHES or tile_count > CONFIRM_TILES:
            lines = [tr("Fetching the {0} 2nd-level meshes of the map view, mesh by mesh.",
                        "表示範囲の2次メッシュ {0} 枚を、メッシュごとに取得します。").format(len(self._meshes))]
            if plan is not None:
                lines.append(tr("Fundamental Geospatial Data: {0} items (about {1:.1f} MB)",
                                "基盤地図情報：{0} 件（約 {1:.1f} MB）").format(
                    len(plan), sum(fgd_api.item_size(i) for _m, _t, items in plan for i in items) / 1024 / 1024))
            elif fgd_layers:
                lines.append(tr("Fundamental Geospatial Data: the number of items is queried when fetching starts.",
                                "基盤地図情報：件数は取得を始めてから問い合わせます。"))
            if tile_count:
                lines.append(tr("Optimized vector tiles: up to {0}", "最適化ベクトルタイル：最大 {0} 枚").format(tile_count))
            lines.append(tr("This can take a while. Stopping finishes the mesh being imported first. Continue?",
                            "時間がかかることがあります。中止すると、取り込み中のメッシュを終えてから止めます。続けますか？"))
            answer = QMessageBox.question(self, self.windowTitle(), "\n".join(lines))
            if answer != QMessageBox.StandardButton.Yes:
                return
        if plan and self.session is None and not self._login():
            return
        self._save_settings()
        self._run_fetch(path, fgd_layers, bv_items, list(self._meshes))

    def _run_fetch(self, path, fgd_layers, bv_items, meshes):
        self._fetch_args = (path, fgd_layers, bv_items, meshes)
        # 取得中に地図を動かしても、置くときは取得を始めたときの可視範囲のグリッドで見せる
        self._fetch_meshes = list(meshes)
        thread = FetchThread(self.session, path, meshes, fgd_layers, bv_items, self.skipCheckbox.isChecked())
        thread.stage.connect(self._on_thread_stage)
        thread.progress.connect(self._on_progress)
        thread.file_progress.connect(self._on_file_progress)
        thread.log.connect(self._log)
        thread.finished.connect(self._on_fetch_finished)
        self._fetch_thread = thread
        self._set_running(True)
        thread.start()

    def _set_running(self, running):
        for widget in (self.tree, self.lockButton, self.pathEdit, self.pathButton, self.groupEdit, self.skipCheckbox,
                       self.placeCheckbox, self.listButton, self.loginButton,
                       self.logoutButton, self.forgetButton, self.languageButton):
            widget.setEnabled(not running)
        if not running:
            self._update_login_state()
        # すべて選ぶ・すべて外すは、取得中とロック中は押せない
        self._update_lock_ui()
        # 取得中は 取得／レイヤーへ配置／配置する範囲 の3段を隠し、中止だけを一番下の段に出す。終わったら戻す
        for widget in (self.fetchButton, self.placeButton, self.placeScope):
            widget.setVisible(not running)
        self.cancelButton.setVisible(running)
        self.cancelButton.setEnabled(True)
        self.cancelButton.setText(tr("Stop", "中止"))
        self.cancelButton.setToolTip(tr("Stops after the mesh being imported is finished.",
                                        "取り込み中のメッシュを終えてから止めます。"))
        self.progressBar.setVisible(running)
        self.fileBar.setVisible(running)
        # 待機中は見込み、取得中は進み具合（同じ区域を入れ替える）
        self.planLabel.setVisible(not running)
        if running:
            # 保存先の読み込み・問い合わせの進み具合を出していたら、取得の表示に切り替える。
            # 動かしている途中の値で、取得の進み具合を上書きしないようアニメーションも止める
            self._reset_activity_display()
            self._set_stage("")
            self.progressBar.setFormat(tr("Meshes %v / %m", "メッシュ %v / %m"))
            self.progressBar.setRange(0, 0)
            self.fileBar.setRange(0, 100)
            self.fileBar.setValue(0)
        else:
            # 取得中も走っていた読み込み・問い合わせがあれば、その進み具合を出す
            self._show_next_activity()

    def _on_thread_stage(self, text):
        # 「このメッシュを終えて中止」を選んだあとも進み具合は届くので、止まるのを待っていることを上の行に残す
        thread = self._fetch_thread
        if thread is not None and thread.is_stopping() and not thread.is_cancelled():
            text = self._closing_note() + tr("Stopping after this mesh.", "このメッシュを終えたら止めます。") + "\n" + text
        self._set_stage(text)

    def _set_stage(self, text):
        # 空のときは行ごと隠す（実行の区域に空いた行を残さない）
        self.stageLabel.setText(text)
        self.stageLabel.setVisible(bool(text))

    def _on_progress(self, done, total):
        self.progressBar.setRange(0, max(total, 1))
        self.progressBar.setValue(done)

    def _on_file_progress(self, received, size):
        self.fileBar.setValue(min(100, int(received * 100 / size)) if size else 0)

    def _cancel_fetch(self):
        thread = self._fetch_thread
        if thread is None:
            return
        if not thread.is_stopping():
            # 1回目：取り込み中のメッシュを終えてから止める（中途半端な範囲を残さない）
            self._stop_after_block()
        else:
            # 2回目：すぐに止める。途中のメッシュは書き込まない
            self._stop_now()

    def _stop_after_block(self):
        self._fetch_thread.stop_after_block()
        self.cancelButton.setText(tr("Stop now", "すぐに止める"))
        self.cancelButton.setToolTip(tr("Stops now; the mesh being imported is left as it was before the fetch.",
                                        "取り込み中のメッシュは取得する前の状態のまま止めます。"))
        self._set_stage(self._closing_note() + tr(
            "Stopping after the mesh being imported (\"Stop now\" stops at once).",
            "取り込み中のメッシュを終えたら止めます（「すぐに止める」で今すぐ止めます）。"))

    def _stop_now(self):
        self._fetch_thread.cancel()
        self.cancelButton.setEnabled(False)
        self._set_stage(self._closing_note() + tr("Stopping…", "止めています…"))

    def _closing_note(self):
        if not self._close_after_fetch:
            return ""
        return tr("The window closes when the fetch has stopped. ", "止まったら窓を閉じます。")

    def _on_fetch_finished(self):
        thread = self._fetch_thread
        self._fetch_thread = None
        self._set_running(False)
        if thread is None:
            return
        path, fgd_layers, bv_items, meshes = self._fetch_args
        store.refresh_project_layers(path)
        self._invalidate_stored()
        self._update_size()

        if thread.need_login and not thread.is_stopping():
            self.session = None
            self._update_login_state()
            self._set_stage(tr("Downloading the Fundamental Geospatial Data needs a login.",
                               "基盤地図情報のダウンロードにはログインが必要です。"))
            if self._login():
                # 取り込み終えたメッシュは保存の記録から飛ばされるので、同じ範囲で始め直せばよい
                self._run_fetch(path, fgd_layers, bv_items, meshes)
                return

        summary = self._summary_before + thread.summary
        self._summary_before = []
        self._set_stage("\n".join(summary)
                        or (tr("Stopped.", "中止しました。") if thread.is_stopping() else ""))
        if thread.error:
            self._log(tr("Stopped: ", "止まりました：") + thread.error)
            QMessageBox.warning(self, self.windowTitle(), tr(
                "The fetch stopped partway. The meshes already imported are saved "
                "(the mesh where it stopped is left as it was before the fetch).\n",
                "取得の途中で止まりました。取り込み終えたメッシュは保存してあります"
                "（止まったメッシュは取得する前の状態のままです）。\n") + thread.error)
        if self._close_after_fetch:
            # 閉じるために止めたので、配置はせずに閉じる（取り込み終えた分は GeoPackage に残る）
            self._close_after_fetch = False
            self.close()
            return
        if thread.bv_failed and not thread.error and not thread.is_stopping() and self._swap_to_fgd(thread.bv_failed):
            # 付け替えた基盤地図情報を、同じ範囲で取得する（最適化ベクトルタイルは開けないので取りに行かない）。
            # 今回の結果は、付け替えて取得した結果の前に残す
            self._run_fetch(path, self._checked_fgd_layers(), [], meshes)
            self._summary_before = list(thread.summary)
            return
        if self.placeCheckbox.isChecked() and not thread.error:
            self._place_layers(self._fetch_meshes)
        self._fill_table()
        self._update_summary()
        self._draw_status()

    def _swap_to_fgd(self, failed_items):
        """最適化ベクトルタイルを開けなかったとき、基盤地図情報にも同じ地物がある項目（⇄）のチェックを
        基盤地図情報へ付け替える。ロック中でも付け替える（ロックの記録は変えない）。付け替えたら True"""
        swaps = []
        for item in failed_items:
            leaf = self._leaf_by_key.get(("bv", item["source_layer"]))
            other = self._counterpart(("bv", item["source_layer"]))
            if leaf is not None and other is not None and leaf.checkState(0) == Qt.CheckState.Checked:
                swaps.append((item, other))
        if not swaps:
            return False
        QMessageBox.information(self, self.windowTitle(), tr(
            "The optimized vector tiles could not be opened.\n"
            "Some checked items also exist in the Fundamental Geospatial Data (⇄), so the checks are moved there "
            "and they are fetched:\n{0}",
            "最適化ベクトルタイルを開けませんでした。\n"
            "基盤地図情報と排他的なチェック（⇄）があるので、基盤地図情報に付け替えて取得します：\n{0}",
        ).format(tr(", ", "、").join(fgd_layer_name(other.data(0, ROLE)[1]) for _item, other in swaps)))
        # 印を付けると、もう一方（最適化ベクトルタイル）は _on_tree_changed で外れる
        self._updating_tree = True
        try:
            for _item, other in swaps:
                other.setCheckState(0, Qt.CheckState.Checked)
        finally:
            self._updating_tree = False
        self._log(tr("Moved the checks to the Fundamental Geospatial Data: ", "基盤地図情報に付け替えました：")
                  + tr(", ", "、").join(fgd_layer_name(other.data(0, ROLE)[1]) for _item, other in swaps))
        self._fill_table()
        self._update_summary()
        self._draw_status()
        return True

    def _place_layers(self, fetched_meshes=None):
        path = self._path()
        if not path or not os.path.exists(path):
            QMessageBox.information(self, self.windowTitle(), tr("The GeoPackage to save to does not exist yet.",
                                                                 "保存先の GeoPackage がまだありません。"))
            return
        if self.placeScope.currentIndex() == PLACE_ALL:
            meshes = None
        elif fetched_meshes is not None:
            meshes = list(fetched_meshes)
        else:
            # ボタンから置くときは、いまの可視範囲のグリッドで見せる
            if not self._meshes:
                QMessageBox.information(self, self.windowTitle(), self.meshLabel.text())
                return
            meshes = list(self._meshes)
        codes = [code for codes in self._checked_fgd_layers().values() for code in codes]
        group_name = self.groupEdit.text().strip() or default_group_name()
        # 配置は画面の処理と同じ流れで動き、その間は窓が止まって見えるので、手前に知らせを出しておき、
        # 終わったら閉じる（出したあと一度画面を描かせてから始める）
        notice = QProgressDialog(tr("Updating the layers…", "レイヤーを更新しています…"), "", 0, 0, self)
        notice.setWindowTitle(self.windowTitle())
        notice.setCancelButton(None)
        notice.setMinimumDuration(0)
        notice.setWindowModality(Qt.WindowModality.WindowModal)
        notice.setMinimumWidth(360)
        notice.show()
        # 窓が画面に出て中身が描かれるまで、少しの間だけ画面の処理を回す（一度だけでは、Flatpak・Wayland などで
        # 中身の無い小さな窓のまま配置の処理に入ってしまった）
        shown_at = time.monotonic()
        while time.monotonic() - shown_at < NOTICE_SETTLE:
            QApplication.processEvents()
            time.sleep(0.01)
        try:
            placed = store.place_layers(path, group_name, codes, self._checked_bv_items(), meshes)
        finally:
            notice.close()
            notice.deleteLater()
        if placed:
            self._log(tr("Placed layers: ", "レイヤーへ配置しました：") + tr(", ", "、").join(placed))
        else:
            self._log(tr("Nothing to place (the checked contents are not in the GeoPackage).",
                         "配置できるデータがありませんでした（チェックした内容が保存先にありません）。"))

    # ================= 記録 =================

    def _toggle_log(self, shown):
        # 記録を開くときは、ほかの区域を狭めずに記録の分だけ窓の高さを伸ばし、閉じたら縮める
        if shown == self.logEdit.isVisible():
            return
        # 基準は出す・隠す前の高さ（出した時点で窓の最小が上がり、窓が先に伸びることがあるため）
        before = self.height()
        min_before = self.minimumSizeHint().height()
        self.logEdit.setVisible(shown)
        self.logToggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)
        if self.isMaximized() or self.isFullScreen():
            return
        if shown:
            # 伸ばす量は、記録を出す前と後の窓の最小の高さの差（記録の欄と、その上下の間隔の分）。閉じるときに使う
            self.layout().activate()
            self._log_delta = max(self.minimumSizeHint().height() - min_before, 0)
            self.resize(self.width(), before + self._log_delta)
        else:
            # 隠した直後は窓の最小がまだ古く縮められないので、決め直されたあとで、開いたときに伸ばした分だけ縮める
            QTimer.singleShot(0, lambda: self._shrink_after_log(before - self._log_delta))

    def _shrink_after_log(self, height):
        # 窓の並びを決め直してから（決め直す前は最小がまだ記録のある高さのままで縮まらなかった）縮める
        self.layout().invalidate()
        self.layout().activate()
        self.resize(self.width(), max(height, self.minimumSizeHint().height()))

    def _log(self, message):
        self.logEdit.appendPlainText(message)

    # ================= 終了 =================

    def _ask_stop_and_close(self):
        thread = self._fetch_thread
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.windowTitle())
        box.setText(tr("A fetch is running. To close the window, stop the fetch first.\n"
                       "The window closes when it has stopped. The meshes already imported are kept "
                       "(they are not placed as layers).",
                       "取得の途中です。閉じるには取得を中止します。\n"
                       "止まったら窓を閉じます。取り込み終えたメッシュは残ります（レイヤーへの配置はしません）。"))
        after_block = None
        if not thread.is_stopping():
            after_block = box.addButton(tr("Stop after this mesh", "このメッシュを終えて中止"),
                                        QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Stop now", "すぐに中止"), QMessageBox.ButtonRole.DestructiveRole)
        keep = box.addButton(tr("Continue (do not close)", "続ける（閉じない）"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        box.setEscapeButton(keep)
        box.exec()
        clicked = box.clickedButton()
        if self._fetch_thread is not thread or clicked is keep or clicked is None:
            # 迷っている間に取得が終わったときも、閉じずにそのまま
            return
        self._close_after_fetch = True
        if clicked is after_block:
            self._stop_after_block()
        else:
            self._stop_now()

    def reject(self):
        # Esc は QDialog では閉じる処理（closeEvent）を通らず隠すだけで、プレビュー地図が残り設定も保存されなかった。
        # 閉じるボタン・窓の × と同じ道を通す
        self.close()

    def closeEvent(self, event):
        if self._fetch_thread is not None:
            # 取得中はすぐには閉じない。中止（このメッシュを終えて／すぐに）を通し、止まったら閉じる
            event.ignore()
            self._ask_stop_and_close()
            return
        self._save_settings()
        self._open = False
        self._remove_preview()
        # QDialog の closeEvent は reject() を呼ぶが、reject() はここへ来るよう close() にしてあるので、
        # 渡さずにここで閉じる（渡すと閉じる途中の close() が無視され、窓が閉じなくなった）
        event.accept()

    def cleanup(self):
        self._listTimer.stop()
        project = QgsProject.instance()
        for signal in (project.readProject, project.fileNameChanged, project.cleared):
            try:
                signal.disconnect(self._resolve_project_path)
            except TypeError:
                pass
        for thread in (self._fetch_thread, self._list_thread):
            if thread is not None:
                if hasattr(thread, "cancel"):
                    thread.cancel()
                thread.wait(15000)
        if self._stored_thread is not None:
            self._stored_thread.finished.disconnect(self._on_stored_loaded)
            self._stored_thread.wait(15000)
        self._fetch_thread = None
        self._list_thread = None
        self._stored_thread = None
        self._disconnect_canvas()
        self._open = False
        self._remove_preview()
        for band in [self.rubber] + list(self.statusRubbers.values()):
            if band is not None:
                self.canvas.scene().removeItem(band)
        self.rubber = None
        self.statusRubbers = {}


def _legend_row(title, entries):
    """凡例の1行（見出し、色の見本と説明の並び）。見出しが空なら付けない（表のすぐ下の凡例）"""
    row = QHBoxLayout()
    title_label = QLabel(title)
    if title:
        row.addWidget(title_label)
    # 色の見本は文字の高さの正方形（文字の幅で決めると横長になった）
    side = title_label.fontMetrics().height()
    for color, text in entries:
        swatch = QLabel()
        swatch.setFixedSize(side, side)
        swatch.setStyleSheet("background:rgba({0},{1},{2},{3}); border:1px solid #bbb;".format(
            color.red(), color.green(), color.blue(), color.alpha()))
        row.addWidget(swatch)
        row.addWidget(QLabel(text))
        row.addSpacing(8)
    row.addStretch(1)
    return row


def _tint(button, color):
    """標準のボタンの地の色をパレットで変える。押せないとき（Disabled）は標準の色のまま。
    パレットを使わないテーマ（Windows の標準の見た目など）では色が出ないことがある"""
    palette = button.palette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.Button, QColor(color))
        palette.setColor(group, QPalette.ColorRole.ButtonText, QColor("white"))
    button.setPalette(palette)


def _mark_exclusive(leaf, other_name):
    leaf.setText(0, leaf.text(0) + " ⇄")
    tip = leaf.toolTip(0)
    note = tr("Same features as {0}. Only one of the two can be selected.",
              "{0}と同じ地物です。どちらか一方だけを選べます。").format(other_name)
    leaf.setToolTip(0, note + ("\n" + tip if tip else ""))


def _file_key(path):
    """保存先のファイルの状態（更新日時と大きさ）。書き込み途中の分（-wal）も含める。ファイルが無ければ None"""
    if not path or not os.path.exists(path):
        return None
    key = [os.path.abspath(path)]
    for name in (path, path + "-wal"):
        if os.path.exists(name):
            stat = os.stat(name)
            key.extend([stat.st_mtime_ns, stat.st_size])
    return tuple(key)


def _short_date(date):
    # 表の欄に収まるよう 20260701 → 26/07/01（全体の日付は欄の説明に出す）
    if date and len(date) == 8:
        return "{0}/{1}/{2}".format(date[2:4], date[4:6], date[6:])
    return date or ""


def _as_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if value in (None, ""):
        return []
    return [value]
