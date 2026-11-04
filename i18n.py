# -*- coding: utf-8 -*-
"""画面の言語（英語が基本、日本語は訳）。

文字は tr("English", "日本語") のように英語と日本語を並べて書く。言語は取得画面のボタンで切り替え、
QGIS の設定に覚える。初めて使うときは英語。
GeoPackage に書き込むデータ（種別の値・vt_code の名前・属性の別名など）は言語によらず日本語のまま。
"""

from qgis.PyQt.QtCore import QSettings

SETTING = "fgd_gpkg_builder/language"
ENGLISH, JAPANESE = "en", "ja"

_language = None


def language():
    global _language
    if _language is None:
        value = QSettings().value(SETTING, ENGLISH)
        _language = JAPANESE if value == JAPANESE else ENGLISH
    return _language


def set_language(value):
    global _language
    _language = JAPANESE if value == JAPANESE else ENGLISH
    QSettings().setValue(SETTING, _language)


def is_japanese():
    return language() == JAPANESE


def tr(english, japanese):
    return japanese if language() == JAPANESE else english
