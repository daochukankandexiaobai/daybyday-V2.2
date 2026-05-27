from __future__ import annotations

from pathlib import Path

from app.utils.qt_compat import Signal
from app.utils.qt_compat import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SettingsTab(QWidget):
    view_scale_changed = Signal(str)

    def __init__(
        self,
        settings_service,
        auth_service,
        template_service,
        view_scale_service,
        db_path: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_service = settings_service
        self.auth_service = auth_service
        self.template_service = template_service
        self.view_scale_service = view_scale_service
        self.db_path = db_path
        self._build_ui()
        self.load_settings()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        basic_group = QGroupBox("基础设置")
        basic_layout = QFormLayout(basic_group)

        self.company_name_edit = QLineEdit()

        export_row = QHBoxLayout()
        self.default_export_dir_edit = QLineEdit()
        self.browse_export_btn = QPushButton("选择")
        export_row.addWidget(self.default_export_dir_edit)
        export_row.addWidget(self.browse_export_btn)

        self.app_version_edit = QLineEdit()
        self.strict_mode_edit = QLineEdit()
        self.view_scale_combo = QComboBox()
        self.view_scale_combo.addItem("自动", "auto")
        self.view_scale_combo.addItem("70%", "70%")
        self.view_scale_combo.addItem("100%", "100%")
        self.view_scale_combo.addItem("130%", "130%")
        self.apply_view_scale_btn = QPushButton("应用视图调整")

        basic_layout.addRow("公司名称", self.company_name_edit)
        basic_layout.addRow("默认导出目录", export_row)
        basic_layout.addRow("应用版本", self.app_version_edit)
        basic_layout.addRow("严格模板模式(1/0)", self.strict_mode_edit)
        basic_layout.addRow("视图调整", self.view_scale_combo)
        basic_layout.addRow(self.apply_view_scale_btn)

        self.save_basic_btn = QPushButton("保存设置")
        basic_layout.addRow(self.save_basic_btn)

        info_group = QGroupBox("系统信息")
        info_layout = QFormLayout(info_group)
        self.db_path_label = QLabel(self.db_path)
        self.current_template_label = QLabel("-")
        self.schema_version_label = QLabel("-")
        self.rules_version_label = QLabel("-")
        info_layout.addRow("数据库路径", self.db_path_label)
        info_layout.addRow("当前模板版本", self.current_template_label)
        info_layout.addRow("Schema版本", self.schema_version_label)
        info_layout.addRow("业务规则版本", self.rules_version_label)

        password_group = QGroupBox("管理员密码")
        password_layout = QFormLayout(password_group)

        self.username_edit = QLineEdit("admin")
        self.old_password_edit = QLineEdit()
        self.old_password_edit.setEchoMode(QLineEdit.Password)
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        self.change_pwd_btn = QPushButton("修改密码")

        password_layout.addRow("用户名", self.username_edit)
        password_layout.addRow("旧密码", self.old_password_edit)
        password_layout.addRow("新密码", self.new_password_edit)
        password_layout.addRow("确认新密码", self.confirm_password_edit)
        password_layout.addRow(self.change_pwd_btn)

        root.addWidget(basic_group)
        root.addWidget(info_group)
        root.addWidget(password_group)
        root.addStretch()

        self.browse_export_btn.clicked.connect(self.on_browse_export_dir)
        self.save_basic_btn.clicked.connect(self.on_save_basic)
        self.change_pwd_btn.clicked.connect(self.on_change_password)
        self.apply_view_scale_btn.clicked.connect(self.on_apply_view_scale)

    def load_settings(self) -> None:
        self.company_name_edit.setText(self.settings_service.get("company_name", "示例公司"))
        self.default_export_dir_edit.setText(self.settings_service.get("default_export_dir", ""))
        self.app_version_edit.setText(self.settings_service.get("app_version", "1.0.0"))
        strict_value = "1" if self.settings_service.is_strict_template_mode() else "0"
        self.strict_mode_edit.setText(strict_value)
        mode = self.view_scale_service.get_mode()
        index = self.view_scale_combo.findData(mode)
        if index < 0:
            index = self.view_scale_combo.findData("auto")
        self.view_scale_combo.setCurrentIndex(max(0, index))
        self.current_template_label.setText(self.template_service.get_active_template_version())
        self.schema_version_label.setText(self.settings_service.get_schema_version() or "-")
        self.rules_version_label.setText(self.settings_service.get_business_rules_version() or "-")

    def on_browse_export_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择默认导出目录",
            self.default_export_dir_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.default_export_dir_edit.setText(path)

    def on_save_basic(self) -> None:
        strict_raw = self.strict_mode_edit.text().strip()
        if strict_raw not in {"0", "1"}:
            QMessageBox.warning(self, "输入错误", "严格模板模式只能填写 0 或 1")
            return

        self.settings_service.save_basic_settings(
            company_name=self.company_name_edit.text().strip(),
            default_export_dir=self.default_export_dir_edit.text().strip(),
            app_version=self.app_version_edit.text().strip() or "1.0.0",
        )
        self.settings_service.set_view_scale_mode(str(self.view_scale_combo.currentData() or "auto"))
        self.settings_service.set_strict_template_mode(strict_raw == "1")
        self.load_settings()
        QMessageBox.information(self, "提示", "设置已保存")
        self.view_scale_changed.emit(self.settings_service.get_view_scale_mode())

    def on_apply_view_scale(self) -> None:
        mode = str(self.view_scale_combo.currentData() or "auto")
        self.settings_service.set_view_scale_mode(mode)
        self.view_scale_changed.emit(mode)

    def on_change_password(self) -> None:
        username = self.username_edit.text().strip()
        old_password = self.old_password_edit.text()
        new_password = self.new_password_edit.text()
        confirm_password = self.confirm_password_edit.text()

        if not username or not old_password or not new_password:
            QMessageBox.warning(self, "输入错误", "请完整填写用户名和密码")
            return

        if new_password != confirm_password:
            QMessageBox.warning(self, "输入错误", "两次输入的新密码不一致")
            return

        ok, message = self.auth_service.change_password(username, old_password, new_password)
        if ok:
            QMessageBox.information(self, "提示", message)
            self.old_password_edit.clear()
            self.new_password_edit.clear()
            self.confirm_password_edit.clear()
        else:
            QMessageBox.warning(self, "失败", message)

    def apply_view_scale(self, factor: float) -> None:
        for edit in [
            self.company_name_edit,
            self.default_export_dir_edit,
            self.app_version_edit,
            self.strict_mode_edit,
            self.username_edit,
            self.old_password_edit,
            self.new_password_edit,
            self.confirm_password_edit,
        ]:
            edit.setMinimumHeight(max(20, int(round(30 * factor))))
