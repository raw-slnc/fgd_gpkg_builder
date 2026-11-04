# -*- coding: utf-8 -*-
"""基盤地図情報のログインID・パスワードの保存（このプラグイン専用。Morizon Next とは別に持つ）。

パスワードは暗号化せず QGIS の設定に入る。
"""

from qgis.PyQt.QtCore import QSettings

GROUP = "fgd_gpkg_builder/credentials"


class CredentialsManager:

    def load(self):
        settings = QSettings()
        return {
            "username": settings.value(GROUP + "/username", "", type=str),
            "password": settings.value(GROUP + "/password", "", type=str),
            "auto_fill": settings.value(GROUP + "/auto_fill", False, type=bool),
        }

    def store(self, username, password, auto_fill):
        settings = QSettings()
        settings.setValue(GROUP + "/username", username)
        settings.setValue(GROUP + "/password", password)
        settings.setValue(GROUP + "/auto_fill", bool(auto_fill))

    def clear(self):
        QSettings().remove(GROUP)

    def has_saved(self):
        saved = self.load()
        return bool(saved["username"] and saved["password"])
