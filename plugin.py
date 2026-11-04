# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .catalog import PLUGIN_NAME
from .i18n import tr


class FgdGpkgBuilder:
    """基盤地図情報（要ログイン）と最適化ベクトルタイル（ログイン不要）を取得し、1つの GeoPackage にまとめる"""

    MENU = "fgd_gpkg_builder"

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def _action_text(self):
        # 名前（G.S.I. = Grid Sheet Importer）は言語によらず同じ。日本語では何をする道具かを添える
        return tr(PLUGIN_NAME, PLUGIN_NAME + "（基盤地図情報を GeoPackage へ）")

    def initGui(self):
        self.action = QAction(
            QIcon(os.path.join(self.plugin_dir, "icon.png")), self._action_text(), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        # ウェブのデータを取得するプラグインなので Web のメニュー・ツールバーに置く
        self.iface.addPluginToWebMenu(self.MENU, self.action)
        self.iface.addWebToolBarIcon(self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginWebMenu(self.MENU, self.action)
            self.iface.removeWebToolBarIcon(self.action)
            self.action = None
        self._close_dialog()

    def _close_dialog(self):
        if self.dialog is not None:
            self.dialog.cleanup()
            self.dialog.hide()
            self.dialog.deleteLater()
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self._create_dialog()
            _center_on(self.dialog, self.iface.mainWindow())
        if self.dialog.isMinimized():
            self.dialog.showNormal()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _create_dialog(self):
        from .dialog import FgdGpkgDialog
        # QGIS の窓を親にすると常に QGIS の手前に出るので、親を持たない独立した窓にする（後ろに回せる）
        self.dialog = FgdGpkgDialog(self.iface, None)
        self.dialog.setWindowIcon(QIcon(os.path.join(self.plugin_dir, "icon.png")))
        self.dialog.languageChanged.connect(self._rebuild_dialog)

    def _rebuild_dialog(self):
        """言語を切り替えたので、ログイン状態・問い合わせ済みの一覧・記録・窓の位置を引き継いで作り直す"""
        state = self.dialog.take_state()
        self._close_dialog()
        if self.action is not None:
            self.action.setText(self._action_text())
        self._create_dialog()
        self.dialog.restore_state(state)
        self.run()


def _center_on(window, main_window):
    # 親が無いと置き場所を窓の仕組みに任せることになるので、初めは QGIS の窓の真ん中に置く
    if main_window is None:
        return
    center = main_window.frameGeometry().center()
    geometry = window.frameGeometry()
    geometry.moveCenter(center)
    window.move(geometry.topLeft())
