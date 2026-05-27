from __future__ import annotations

from app.utils.qt_compat import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class LoginDialog(QDialog):
    def __init__(self, auth_service, parent=None) -> None:
        super().__init__(parent)
        self.auth_service = auth_service
        self.setWindowTitle("管理员登录")
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.username_edit = QLineEdit("admin")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        form.addRow("用户名", self.username_edit)
        form.addRow("密码", self.password_edit)

        btns = QHBoxLayout()
        self.ok_btn = QPushButton("登录")
        self.cancel_btn = QPushButton("取消")
        btns.addStretch()
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)

        root.addLayout(form)
        root.addLayout(btns)

        self.ok_btn.clicked.connect(self.on_login)
        self.cancel_btn.clicked.connect(self.reject)

    def on_login(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if self.auth_service.login(username, password):
            self.accept()
        else:
            QMessageBox.warning(self, "登录失败", "用户名或密码错误")
