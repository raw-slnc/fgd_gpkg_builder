# -*- coding: utf-8 -*-
# Copyright (C) 2026 Hideharu Masai
# Taken from fgd_login_dialog.py of Morizon Next (same author), with the credentials kept for this plugin.
# Licensed under the GNU General Public License v2 or later. See LICENSE.

from qgis.PyQt.QtCore import Qt, QThread, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from . import fgd_api, fgd_auth
from .credentials import CredentialsManager
from .i18n import tr


class LoginThread(QThread):
    succeeded = pyqtSignal(object)  # requests.Session（ログイン済み）
    failed = pyqtSignal(str)

    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password

    def run(self):
        try:
            session = fgd_api.new_session()
            action_url = fgd_auth.start_login(session)
            ok, error, chain = fgd_auth.submit_login(session, action_url, self.username, self.password)
            if not ok:
                self.failed.emit(error or tr("Login failed.", "ログインに失敗しました。"))
                return
            if not fgd_api.check_login(session):
                self.failed.emit(
                    tr("The login finished, but its state could not be confirmed.\nRoute:\n",
                       "ログイン処理は完了しましたが、状態を確認できませんでした。\n経路:\n") + "\n".join(chain)
                )
                return
            self.succeeded.emit(session)
        except Exception as e:  # 通信の失敗も理由をそのまま見せる
            self.failed.emit(str(e))


class LoginDialog(QDialog):
    """基盤地図情報ダウンロードサービスへのログイン。

    埋め込みブラウザは使わず、Keycloak の標準フォームへ requests で直接送る（Morizon Next と同じ方式）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Log in to the Fundamental Geospatial Data download service",
                               "基盤地図情報ダウンロードサービス ログイン"))
        self.setMinimumWidth(460)
        self.session = None
        self._thread = None

        layout = QVBoxLayout(self)
        info = QLabel(tr(
            "Enter the login ID and password of the GSI Fundamental Geospatial Data download service.\n"
            "They are sent directly to the GSI login server.",
            "基盤地図情報ダウンロードサービスのログインID・パスワードを入力してください。\n"
            "入力内容は国土地理院のログインサーバーへ直接送信されます。",
        ))
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.usernameEdit = QLineEdit()
        self.passwordEdit = QLineEdit()
        self.passwordEdit.setEchoMode(QLineEdit.EchoMode.Password)
        self.usernameEdit.returnPressed.connect(self.passwordEdit.setFocus)
        self.passwordEdit.returnPressed.connect(self._on_login_clicked)
        form.addRow(tr("Login ID", "ログインID"), self.usernameEdit)
        form.addRow(tr("Password", "パスワード"), self.passwordEdit)
        layout.addLayout(form)

        saved = CredentialsManager().load()
        if saved["auto_fill"] and saved["username"] and saved["password"]:
            self.usernameEdit.setText(saved["username"])
            self.passwordEdit.setText(saved["password"])

        # ログインに成功したとき、このチェックの状態を保存に当てはめる
        self.autoFillCheckbox = QCheckBox(tr("Save the ID and password and fill them in next time",
                                             "ID・パスワードを保存し、次回から自動入力する"))
        self.autoFillCheckbox.setChecked(bool(saved["auto_fill"]))
        layout.addWidget(self.autoFillCheckbox)
        note = QLabel(tr("Note: the password is saved in the QGIS settings without encryption. "
                         "Not recommended on a shared PC.",
                         "※パスワードは暗号化せず QGIS の設定に保存されます。共有PCでは推奨しません。"))
        note.setStyleSheet("color:#c00;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.errorLabel = QLabel("")
        self.errorLabel.setStyleSheet("color:#c00;")
        self.errorLabel.setWordWrap(True)
        layout.addWidget(self.errorLabel)

        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.loginButton = self.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.cancelButton = self.buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        self.loginButton.setText(tr("Log in", "ログイン"))
        self.cancelButton.setText(tr("Cancel", "キャンセル"))
        for button in (self.loginButton, self.cancelButton):
            button.setAutoDefault(False)
            button.setDefault(False)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.buttonBox.accepted.connect(self._on_login_clicked)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

        self._focus_order = [
            self.usernameEdit, self.passwordEdit, self.autoFillCheckbox, self.loginButton, self.cancelButton
        ]
        for first, second in zip(self._focus_order, self._focus_order[1:]):
            self.setTabOrder(first, second)
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._set_initial_focus)

    def _set_initial_focus(self):
        if self.usernameEdit.text() and not self.passwordEdit.text():
            self.passwordEdit.setFocus()
        else:
            self.usernameEdit.setFocus()

    def keyPressEvent(self, event):
        # Enter・スペースはフォーカスのあるボタンだけを押す（既定のボタンが勝手に押されないように）
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            current = QApplication.focusWidget()
            if current in (self.loginButton, self.cancelButton):
                current.click()
                return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next):
        current = QApplication.focusWidget()
        if current in self._focus_order:
            step = 1 if next else -1
            index = (self._focus_order.index(current) + step) % len(self._focus_order)
            reason = Qt.FocusReason.TabFocusReason if next else Qt.FocusReason.BacktabFocusReason
            self._focus_order[index].setFocus(reason)
            return True
        return super().focusNextPrevChild(next)

    def _on_login_clicked(self):
        if self._thread is not None:
            return
        username = self.usernameEdit.text().strip()
        password = self.passwordEdit.text()
        if not username or not password:
            self.errorLabel.setStyleSheet("color:#c00;")
            self.errorLabel.setText(tr("Enter the login ID and password.", "ログインIDとパスワードを入力してください。"))
            (self.passwordEdit if username else self.usernameEdit).setFocus()
            return
        self.errorLabel.setStyleSheet("color:#444;")
        self.errorLabel.setText(tr("Logging in…", "ログイン中…"))
        self.buttonBox.setEnabled(False)
        self._thread = LoginThread(username, password)
        self._thread.succeeded.connect(self._on_succeeded)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_succeeded(self, session):
        self._thread = None
        self.session = session
        # チェックあり：ログインできたID・パスワードで保存し直す。チェックなし：自動入力だけ止め、入力したパスワードは保存しない
        manager = CredentialsManager()
        if self.autoFillCheckbox.isChecked():
            manager.store(self.usernameEdit.text().strip(), self.passwordEdit.text(), True)
        else:
            saved = manager.load()
            if saved["auto_fill"]:
                manager.store(saved["username"], saved["password"], False)
        self.accept()

    def _on_failed(self, message):
        self._thread = None
        self.errorLabel.setStyleSheet("color:#c00;")
        self.errorLabel.setText(message)
        self.buttonBox.setEnabled(True)
        self.passwordEdit.setFocus()

    def reject(self):
        if self._thread is not None:
            # ログインの通信中は閉じない（終わってから結果を受け取る）
            return
        super().reject()

    def username(self):
        return self.usernameEdit.text().strip()
