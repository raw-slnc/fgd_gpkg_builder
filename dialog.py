# -*- coding: utf-8 -*-
"""取得画面。

左に取得する内容（基盤地図情報＝要ログイン、最適化ベクトルタイル＝ログイン不要）、右に表示範囲に
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
from qgis.PyQt.QtCore import QPropertyAnimation, QSettings, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QKeySequence

try:  # Qt6（QGIS 4）は QtGui、Qt5（QGIS 3）は QtWidgets
    from qgis.PyQt.QtGui import QShortcut
except ImportError:
    from qgis.PyQt.QtWidgets import QShortcut
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QStyle, QTableWidget, QTableWidgetItem, QToolButton, QTreeWidget, QTreeWidgetItem,
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
# 取得・中止のボタン（押せないときは灰色）
_ACTION_STYLE = (
    "QPushButton {{ background:{base}; color:white; border:none; border-radius:4px; padding:4px 16px; }}"
    "QPushButton:hover {{ background:{hover}; }}"
    "QPushButton:disabled {{ background:#b8b8b8; color:#eeeeee; }}"
)


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
        self._center_tile_counts = {}  # {メッシュ: 中心がそのメッシュに入るタイルの数}
        self._preview_id = None
        self._open = False
        self._close_after_fetch = False  # 閉じるために取得を中止した（止まったら閉じる）
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
        self.setMinimumSize(960, 660)
        self.resize(1200, 760)

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
        splitter.addWidget(self._build_tree_panel())
        splitter.addWidget(self._build_mesh_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([400, 780])
        layout.addWidget(splitter, 1)

        layout.addWidget(self._build_output_box())
        layout.addWidget(self._build_progress_area())
        layout.addLayout(self._build_buttons())

        source = QLabel(tr(
            'Sources: <a href="{0}">{1}</a>, <a href="{2}">{3}</a> (trial release; the URL and contents may change). '
            'Preview map: <a href="{4}">{5}</a>',
            '出典：<a href="{0}">{1}</a>、<a href="{2}">{3}</a>（試験公開。URL やデータの内容が変わることがあります）、'
            'プレビュー地図は<a href="{4}">{5}</a>',
        ).format(FGD_SOURCE_PAGE, fgd_attribution(), BV_SOURCE_PAGE, bv_attribution(), PREVIEW_SOURCE_PAGE,
                 preview_attribution()))
        source.setOpenExternalLinks(True)
        source.setWordWrap(True)
        source.setStyleSheet("color:#555;")
        layout.addWidget(source)

        # Ctrl+W でも閉じる（Esc・閉じるボタン・窓の × と同じく closeEvent を通る）
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)

        self._update_login_state()
        self._update_summary()

    # ================= 言語の切り替え =================

    def take_state(self):
        """作り直す前の窓から、新しい窓へ引き継ぐもの"""
        self._save_settings()
        return {
            "session": self.session, "session_user": self.session_user,
            "listing_by_mesh": dict(self._listing_by_mesh), "log": self.logEdit.toPlainText(),
            "log_shown": self.logToggle.isChecked(), "geometry": self.saveGeometry(),
        }

    def restore_state(self, state):
        self.session = state["session"]
        self.session_user = state["session_user"]
        self._listing_by_mesh = state["listing_by_mesh"]
        if state["log"]:
            self.logEdit.setPlainText(state["log"])
        self.logToggle.setChecked(state["log_shown"])
        self.restoreGeometry(state["geometry"])
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
        column.addWidget(QLabel(tr("Contents to fetch", "取得する内容")))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumWidth(340)
        # 名前を「…」で切らず、入りきらないときは横に送れるようにする（英語の名前は長い）
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        checked = QSettings().value(SETTINGS + "checked", None)
        checked = None if checked is None else set(_as_list(checked))
        paren = tr("{0} ({1})", "{0}（{1}）")

        self._leaf_by_key = {}
        self._fgd_root = QTreeWidgetItem([tr("Fundamental Geospatial Data (login required)", "基盤地図情報（要ログイン）")])
        self._fgd_root.setData(0, ROLE, ("root", "fgd"))
        for type_info in FGD_TYPES:
            type_item = QTreeWidgetItem([paren.format(fgd_type_name(type_info), type_info["code"])])
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
        self._bv_root = QTreeWidgetItem([tr("Optimized vector tiles (no login)", "最適化ベクトルタイル（ログイン不要）")])
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
        for text, state in ((tr("Select all", "すべて選ぶ"), Qt.CheckState.Checked),
                            (tr("Clear all", "すべて外す"), Qt.CheckState.Unchecked)):
            button = QToolButton()
            button.setText(text)
            button.clicked.connect(lambda _checked=False, s=state: self._set_all(s))
            buttons.addWidget(button)
        buttons.addStretch(1)
        column.addLayout(buttons)
        return panel

    def _build_mesh_panel(self):
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.meshLabel = QLabel("")
        self.meshLabel.setWordWrap(True)
        header.addWidget(self.meshLabel, 1)
        self.listButton = QPushButton(tr("Check latest status", "最新の状況を確認"))
        self.listButton.clicked.connect(lambda _checked=False: self._start_list(refresh=True))
        header.addWidget(self.listButton)
        column.addLayout(header)

        map_row = QHBoxLayout()
        self.previewCheckbox = QCheckBox(tr("Show preview map (GSI Tiles, pale map)",
                                            "プレビュー地図（地理院タイル・淡色地図）を表示"))
        self.previewCheckbox.setToolTip(tr(
            "A background for choosing the area to fetch. It is removed from the Layers panel when this window "
            "is closed.",
            "取得する範囲を選ぶための背景です。この窓を閉じるとレイヤーパネルから外します。"))
        self.previewCheckbox.setChecked(QSettings().value(SETTINGS + "preview_map", True, type=bool))
        self.previewCheckbox.toggled.connect(self._sync_preview)
        map_row.addWidget(self.previewCheckbox)
        map_row.addStretch(1)
        column.addLayout(map_row)

        self.table = QTableWidget(0, len(FGD_TYPES) + 1)
        self.table.setHorizontalHeaderLabels([tr("Mesh", "メッシュ")] + [fgd_type_short(t) for t in FGD_TYPES])
        for index, type_info in enumerate(FGD_TYPES):
            self.table.horizontalHeaderItem(index + 1).setToolTip(
                tr("{0} ({1})", "{0}（{1}）").format(fgd_type_name(type_info), type_info["code"]))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # 日付が切れないよう欄の幅は中身に合わせる（狭いときは横に送れる）。合わせるのは表を埋め終えたとき（_fill_table）
        self.table.horizontalHeader().setStretchLastSection(True)
        column.addWidget(self.table, 1)

        # 凡例は表の色と地図の塗りを1行ずつ（チェックボックスと同じ行に置くと文字が切れた）
        for title, entries in (
            (tr("Table:", "表："), (
                (COLOR_CURRENT, tr("Stored (latest)", "保存済み（最新）")),
                (COLOR_UPDATE, tr("Newer data", "新しいデータあり")),
                (QColor("white"), tr("Not fetched", "未取得")), (COLOR_NONE, tr("No data", "データなし")))),
            (tr("Map:", "地図："), (
                (COLOR_MAP_FULL, tr("All checked contents stored", "チェックした内容がそろっている")),
                (COLOR_MAP_PART, tr("Partly stored", "一部だけ")))),
        ):
            legend = QHBoxLayout()
            legend.addWidget(QLabel(title))
            for color, text in entries:
                swatch = QLabel("  ")
                swatch.setStyleSheet("background:rgba({0},{1},{2},{3}); border:1px solid #bbb;".format(
                    color.red(), color.green(), color.blue(), color.alpha()))
                legend.addWidget(swatch)
                legend.addWidget(QLabel(text))
                legend.addSpacing(8)
            legend.addStretch(1)
            column.addLayout(legend)
        return panel

    def _build_output_box(self):
        box = QGroupBox(tr("Storage and layers", "保存とレイヤー"))
        form = QFormLayout(box)
        path_row = QHBoxLayout()
        default_path = os.path.join(os.path.expanduser("~"), "fgd_gpkg_builder.gpkg")
        self.pathEdit = QLineEdit(QSettings().value(SETTINGS + "gpkg_path", default_path))
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
        self.skipCheckbox = QCheckBox(tr("Do not refetch stored data that is up to date",
                                         "保存済みで最新のものは取り直さない"))
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
        texts.setAlignment(Qt.AlignmentFlag.AlignTop)
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
        bars = QHBoxLayout()
        self.progressBar = QProgressBar()
        self.progressBar.setFormat(tr("Meshes %v / %m", "メッシュ %v / %m"))
        bars.addWidget(self.progressBar, 3)
        self.fileBar = QProgressBar()
        self.fileBar.setFormat(tr("Current step %p%", "今の作業 %p%"))
        bars.addWidget(self.fileBar, 2)
        texts.addLayout(bars)
        for bar in (self.progressBar, self.fileBar):
            bar.setVisible(False)
        # 保存先の読み込み・最新の状況の問い合わせでは、進捗バーの値を動かして見せる（取得のときは使わない）
        self._barAnimation = QPropertyAnimation(self.progressBar, b"value", self)
        self._barAnimation.finished.connect(self._on_bar_animation_finished)
        action_row.addWidget(texts_widget, 1)

        # 取得・中止は同じ場所で入れ替わる。画面のいちばん大事な操作なので大きく、色を付ける
        bold = QFont()
        bold.setBold(True)
        self.fetchButton = QPushButton(tr("Fetch", "取得"))
        self.fetchButton.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.fetchButton.setStyleSheet(_ACTION_STYLE.format(base="#1f6fb2", hover="#2a82cc"))
        self.fetchButton.clicked.connect(self._start_fetch)
        self.cancelButton = QPushButton(tr("Stop", "中止"))
        self.cancelButton.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop))
        self.cancelButton.setStyleSheet(_ACTION_STYLE.format(base="#c0392b", hover="#d9483a"))
        self.cancelButton.clicked.connect(self._cancel_fetch)
        self.cancelButton.setVisible(False)
        for button in (self.fetchButton, self.cancelButton):
            button.setFont(bold)
            # 高さはほかのボタンと同じ。幅だけ広げる（横に広がると見込みの文が細い列に押し込まれたので固定する）
            button.setMinimumWidth(160)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            # 区域の下端にそろえる（取得中は進み具合の棒と同じ高さに並ぶ）
            action_row.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        column.addWidget(action)

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
        column.addLayout(toggle_row)
        self.logEdit = QPlainTextEdit()
        self.logEdit.setReadOnly(True)
        self.logEdit.setMaximumHeight(120)
        self.logEdit.setVisible(False)
        column.addWidget(self.logEdit)
        return area

    def _build_buttons(self):
        row = QHBoxLayout()
        self.placeButton = QPushButton(tr("Place layers", "レイヤーへ配置"))
        self.placeButton.setToolTip(tr("Places the stored data in the Layers panel without fetching.",
                                       "保存先にあるデータを、取得せずにレイヤーパネルへ置きます。"))
        self.placeButton.clicked.connect(lambda _checked=False: self._place_layers())
        row.addWidget(self.placeButton)
        self.placeScope = QComboBox()
        self.placeScope.addItems([tr("Visible meshes only", "可視範囲のメッシュだけ"),
                                  tr("All stored areas", "取得済みの範囲すべて")])
        self.placeScope.setToolTip(tr("The area shown by the layers, also when placing them after fetching.",
                                      "レイヤーで見せる範囲。取得後に配置するときもこの範囲です。"))
        scope = QSettings().value(SETTINGS + "place_scope", PLACE_VISIBLE, type=int)
        self.placeScope.setCurrentIndex(scope if scope in (PLACE_VISIBLE, PLACE_ALL) else PLACE_VISIBLE)
        row.addWidget(self.placeScope)
        row.addStretch(1)
        # 今の言語を出し、押すと切り替える
        self.languageButton = QPushButton(tr("Language: English", "言語：日本語"))
        self.languageButton.setToolTip(tr("Switch to Japanese (the window is rebuilt).",
                                          "英語に切り替えます（窓を作り直します）。"))
        self.languageButton.clicked.connect(self._switch_language)
        row.addWidget(self.languageButton)
        # 閉じるボタンは置かない（窓の ×・Esc・Ctrl+W で閉じる。× と役目が重なるため）
        for button in (self.placeButton, self.fetchButton, self.cancelButton, self.languageButton):
            button.setAutoDefault(False)
        return row

    # ================= 取得する内容 =================

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
            "Delete the login ID and password saved for this plugin?\n(Those saved for Morizon Next are kept.)",
            "このプラグインに保存したログインID・パスワードを消しますか？\n（Morizon Next に保存したものは消えません）"))
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
        # 窓を先に出す。プレビュー地図は出たあとに置き、保存先の記録は別スレッドで読む（読み終わったら描き直す）
        QTimer.singleShot(0, self._sync_preview)
        self._invalidate_stored()
        self._update_meshes(force=True)
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
            return {"fgd": {}, "bv": {}}
        return self._stored_cache

    def _stored_loading(self):
        return self._stored_cache is None

    def _load_stored(self):
        if self._stored_thread is not None:
            self._stored_again = True
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
        return (tr("Querying the latest status (no login needed)…", "最新の状況を問い合わせています（ログイン不要）…"),
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
        header_view.setStretchLastSection(True)
        for column, type_info in enumerate(FGD_TYPES, start=1):
            header = self.table.horizontalHeaderItem(column)
            header.setForeground(QBrush(QColor("black") if type_info["code"] in checked_types else COLOR_GRAY_TEXT))
        self.table.resizeRowsToContents()

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
        if self._stored_loading():
            # 読む前の空の記録で見込みを出さない
            reason = tr("Reading the GeoPackage…", "保存先を読んでいます…")
        elif not fgd_layers and not self._checked_bv_items():
            reason = tr("Check the contents to fetch.", "取得する内容にチェックを入れてください。")
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
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("GeoPackage to save to", "保存先の GeoPackage"), self.pathEdit.text(), "GeoPackage (*.gpkg)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            if not path.lower().endswith(".gpkg"):
                path += ".gpkg"
            self.pathEdit.setText(path)
            self._on_path_changed()

    def _on_path_changed(self):
        self._invalidate_stored()
        self._fill_table()
        self._update_summary()
        self._draw_status()
        self._update_size()

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
        settings.setValue(SETTINGS + "gpkg_path", self.pathEdit.text().strip())
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
            QMessageBox.information(self, self.windowTitle(), tr("Check the contents to fetch.",
                                                                 "取得する内容にチェックを入れてください。"))
            return
        if not self._meshes:
            QMessageBox.information(self, self.windowTitle(), self.meshLabel.text())
            return
        path = self._path()
        if not path:
            QMessageBox.information(self, self.windowTitle(), tr("Specify the GeoPackage to save to.",
                                                                 "保存先の GeoPackage を指定してください。"))
            return
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            QMessageBox.warning(self, self.windowTitle(), tr("The folder to save to does not exist:\n{0}",
                                                             "保存先のフォルダがありません：\n{0}").format(folder))
            return
        self.pathEdit.setText(path)
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
        # ダウンロードがあると分かっていて、まだログインしていなければ先にログインする
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
        for widget in (self.tree, self.pathEdit, self.pathButton, self.groupEdit, self.skipCheckbox,
                       self.placeCheckbox, self.placeButton, self.placeScope, self.listButton, self.loginButton,
                       self.logoutButton, self.forgetButton, self.languageButton):
            widget.setEnabled(not running)
        if not running:
            self._update_login_state()
        self.fetchButton.setVisible(not running)
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

        self._set_stage("\n".join(thread.summary)
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
        if self.placeCheckbox.isChecked() and not thread.error:
            self._place_layers(self._fetch_meshes)
        self._fill_table()
        self._update_summary()
        self._draw_status()

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
        placed = store.place_layers(path, group_name, codes, self._checked_bv_items(), meshes)
        if placed:
            self._log(tr("Placed layers: ", "レイヤーへ配置しました：") + tr(", ", "、").join(placed))
        else:
            self._log(tr("Nothing to place (the checked contents are not in the GeoPackage).",
                         "配置できるデータがありませんでした（チェックした内容が保存先にありません）。"))

    # ================= 記録 =================

    def _toggle_log(self, shown):
        self.logEdit.setVisible(shown)
        self.logToggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)

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


def _mark_exclusive(leaf, other_name):
    leaf.setText(0, leaf.text(0) + " ⇄")
    tip = leaf.toolTip(0)
    note = tr("Same features as {0}. Only one of the two can be selected.",
              "{0}と同じ地物です。どちらか一方だけを選べます。").format(other_name)
    leaf.setToolTip(0, note + ("\n" + tip if tip else ""))


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
