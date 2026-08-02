from __future__ import annotations

from datetime import date
from pathlib import Path

from app.utils.qt_compat import Signal
from app.utils.qt_compat import (
    QComboBox,
    QDate,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsTab(QWidget):
    view_scale_changed = Signal(str)
    settlement_cycle_rule_changed = Signal()

    def __init__(
        self,
        settings_service,
        auth_service,
        template_service,
        view_scale_service,
        db_path: str,
        settlement_cycle_service=None,
        operator_getter=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_service = settings_service
        self.auth_service = auth_service
        self.template_service = template_service
        self.view_scale_service = view_scale_service
        self.db_path = db_path
        self.settlement_cycle_service = settlement_cycle_service
        self.operator_getter = operator_getter or (lambda: "admin")
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

        self.cycle_rule_group = QGroupBox("结算周期规则")
        cycle_layout = QFormLayout(self.cycle_rule_group)
        self.cycle_mode_combo = QComboBox()
        self.cycle_mode_combo.addItem("自然月：每月1日至月底", "calendar_month")
        self.cycle_mode_combo.addItem("自定义：每月指定日期至次月前一日", "fixed_start_day")
        self.cycle_start_day_spin = QSpinBox()
        self.cycle_start_day_spin.setRange(1, 29)
        self.cycle_start_day_spin.setValue(1)
        self.cycle_rule_status_label = QLabel("-")
        self.cycle_rule_preview_label = QLabel("-")
        self.cycle_rule_preview_label.setWordWrap(True)
        self.save_cycle_rule_btn = QPushButton("保存周期规则")
        self.save_cycle_rule_btn.setProperty("buttonRole", "primary")
        self.lock_cycle_rule_btn = QPushButton("确认并锁定")
        self.lock_cycle_rule_btn.setProperty("buttonRole", "danger")

        cycle_button_row = QHBoxLayout()
        cycle_button_row.setContentsMargins(0, 0, 0, 0)
        cycle_button_row.setSpacing(6)
        cycle_button_row.addWidget(self.save_cycle_rule_btn)
        cycle_button_row.addWidget(self.lock_cycle_rule_btn)
        cycle_button_row.addStretch()

        cycle_hint = QLabel(
            "规则仅可在尚未录入日报、周目标或周期目标时调整；确认锁定后，"
            "系统不会重新归类历史数据。"
        )
        cycle_hint.setWordWrap(True)
        cycle_hint.setObjectName("statusText")

        self.future_cycle_mode_combo = QComboBox()
        self.future_cycle_mode_combo.addItem("自然月：每月1日至月底", "calendar_month")
        self.future_cycle_mode_combo.addItem("自定义：每月指定日期至次月前一日", "fixed_start_day")
        self.future_cycle_start_day_spin = QSpinBox()
        self.future_cycle_start_day_spin.setRange(1, 28)
        self.future_cycle_start_day_spin.setValue(1)
        self.future_effective_date_edit = QDateEdit()
        self.future_effective_date_edit.setCalendarPopup(True)
        self.future_effective_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.future_effective_date_edit.setDate(QDate.currentDate())
        self.future_rule_preview_label = QLabel("-")
        self.future_rule_preview_label.setWordWrap(True)
        self.future_rule_history_label = QLabel("-")
        self.future_rule_history_label.setWordWrap(True)
        self.add_future_cycle_rule_btn = QPushButton("新增未来规则")
        self.add_future_cycle_rule_btn.setProperty("buttonRole", "primary")
        future_hint = QLabel(
            "需要切换结算周期时，请新增一个未来生效规则。历史日报不会被重新归类；"
            "导入旧 JSON 前可先排期新规则，导入文件中的历史规则会保留。"
        )
        future_hint.setWordWrap(True)
        future_hint.setObjectName("statusText")

        cycle_layout.addRow("周期模式", self.cycle_mode_combo)
        cycle_layout.addRow("自定义起始日", self.cycle_start_day_spin)
        cycle_layout.addRow("当前状态", self.cycle_rule_status_label)
        cycle_layout.addRow("周期预览", self.cycle_rule_preview_label)
        cycle_layout.addRow(cycle_hint)
        cycle_layout.addRow(cycle_button_row)
        cycle_layout.addRow(QLabel("后续规则（按生效日期）"))
        cycle_layout.addRow("新周期模式", self.future_cycle_mode_combo)
        cycle_layout.addRow("新周期起始日", self.future_cycle_start_day_spin)
        cycle_layout.addRow("生效日期", self.future_effective_date_edit)
        cycle_layout.addRow("新规则预览", self.future_rule_preview_label)
        cycle_layout.addRow("规则时间线", self.future_rule_history_label)
        cycle_layout.addRow(future_hint)
        cycle_layout.addRow(self.add_future_cycle_rule_btn)

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
        root.addWidget(self.cycle_rule_group)
        root.addWidget(info_group)
        root.addWidget(password_group)
        root.addStretch()

        self.browse_export_btn.clicked.connect(self.on_browse_export_dir)
        self.save_basic_btn.clicked.connect(self.on_save_basic)
        self.change_pwd_btn.clicked.connect(self.on_change_password)
        self.apply_view_scale_btn.clicked.connect(self.on_apply_view_scale)
        self.cycle_mode_combo.currentIndexChanged.connect(self.on_cycle_mode_changed)
        self.cycle_start_day_spin.valueChanged.connect(self._refresh_cycle_rule_preview)
        self.save_cycle_rule_btn.clicked.connect(self.on_save_cycle_rule)
        self.lock_cycle_rule_btn.clicked.connect(self.on_lock_cycle_rule)
        self.future_cycle_mode_combo.currentIndexChanged.connect(self.on_future_cycle_mode_changed)
        self.future_cycle_start_day_spin.valueChanged.connect(self.on_future_cycle_start_day_changed)
        self.future_effective_date_edit.dateChanged.connect(self._refresh_future_cycle_preview)
        self.add_future_cycle_rule_btn.clicked.connect(self.on_add_future_cycle_rule)

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
        self._load_cycle_rule()

    def _operator(self) -> str:
        return str(self.operator_getter() or "admin")

    def _load_cycle_rule(self) -> None:
        if self.settlement_cycle_service is None:
            self.cycle_rule_group.setVisible(False)
            return

        status = self.settlement_cycle_service.get_rule_status()
        mode = str(status.get("rule_mode", "calendar_month") or "calendar_month")
        if mode == "legacy_29":
            self.cycle_mode_combo.clear()
            self.cycle_mode_combo.addItem("历史兼容：每月29日至次月28日", "legacy_29")
            self.cycle_mode_combo.addItem("自然月：每月1日至月底", "calendar_month")
            self.cycle_mode_combo.addItem("自定义：每月指定日期至次月前一日", "fixed_start_day")
        elif self.cycle_mode_combo.count() == 1:
            self.cycle_mode_combo.addItem("自然月：每月1日至月底", "calendar_month")
            self.cycle_mode_combo.addItem("自定义：每月指定日期至次月前一日", "fixed_start_day")

        index = self.cycle_mode_combo.findData(mode)
        self.cycle_mode_combo.blockSignals(True)
        self.cycle_mode_combo.setCurrentIndex(max(0, index))
        self.cycle_mode_combo.blockSignals(False)
        self.cycle_start_day_spin.setMaximum(29 if mode == "legacy_29" else 28)
        self.cycle_start_day_spin.setValue(int(status.get("start_day", 1) or 1))

        locked = bool(status.get("is_locked", False))
        has_business_data = bool(status.get("has_business_data", False))
        editable = bool(status.get("is_editable", False))
        label = str(status.get("label", "-") or "-")
        if locked:
            state_text = "已锁定：{}".format(label)
        elif has_business_data:
            state_text = "已有业务数据，规则已受保护：{}".format(label)
        else:
            state_text = "待确认：{}".format(label)
        self.cycle_rule_status_label.setText(state_text)
        self.cycle_mode_combo.setEnabled(editable and mode != "legacy_29")
        self.cycle_start_day_spin.setEnabled(editable and mode == "fixed_start_day")
        self.save_cycle_rule_btn.setEnabled(editable and mode != "legacy_29")
        self.lock_cycle_rule_btn.setEnabled(editable and mode != "legacy_29")
        self._refresh_cycle_rule_preview()
        self._refresh_future_rule_controls(status)

    def _refresh_future_rule_controls(self, status: dict) -> None:
        if self.settlement_cycle_service is None:
            return
        latest_business_date = str(status.get("latest_business_date", "") or "")
        if latest_business_date:
            latest = QDate.fromString(latest_business_date, "yyyy-MM-dd")
            if latest.isValid():
                self.future_effective_date_edit.setMinimumDate(latest.addDays(1))
        else:
            self.future_effective_date_edit.setMinimumDate(QDate(1900, 1, 1))

        rules = list(status.get("rules", []) or [])
        lines = []
        for item in rules:
            effective_from = str(item.get("effective_from", "") or "")
            label = str(item.get("rule_mode", "") or "")
            start_day = int(item.get("start_day", 1) or 1)
            if label == "calendar_month":
                label = "自然月"
            elif label == "fixed_start_day":
                label = "每月{}日开始".format(start_day)
            elif label == "legacy_29":
                label = "历史兼容：29日至次月28日"
            lines.append("{} 起：{}".format(effective_from, label))
        self.future_rule_history_label.setText("； ".join(lines) if lines else "-")
        self.on_future_cycle_mode_changed()

    def on_future_cycle_mode_changed(self, *_args) -> None:
        mode = str(self.future_cycle_mode_combo.currentData() or "calendar_month")
        if mode == "calendar_month":
            self.future_cycle_start_day_spin.setValue(1)
        self.future_cycle_start_day_spin.setEnabled(mode == "fixed_start_day")
        self._align_future_effective_date_to_start_day()
        self._refresh_future_cycle_preview()

    def _align_future_effective_date_to_start_day(self) -> None:
        mode = str(self.future_cycle_mode_combo.currentData() or "calendar_month")
        start_day = 1 if mode == "calendar_month" else int(self.future_cycle_start_day_spin.value())
        current = self.future_effective_date_edit.date()
        if not current.isValid():
            current = QDate.currentDate()
        day = min(start_day, current.daysInMonth())
        aligned = QDate(current.year(), current.month(), day)
        if aligned < self.future_effective_date_edit.minimumDate():
            minimum = self.future_effective_date_edit.minimumDate()
            day = min(start_day, minimum.daysInMonth())
            aligned = QDate(minimum.year(), minimum.month(), day)
            if aligned < minimum:
                next_month = minimum.addMonths(1)
                aligned = QDate(next_month.year(), next_month.month(), min(start_day, next_month.daysInMonth()))
        self.future_effective_date_edit.blockSignals(True)
        self.future_effective_date_edit.setDate(aligned)
        self.future_effective_date_edit.blockSignals(False)

    def on_future_cycle_start_day_changed(self, *_args) -> None:
        self._align_future_effective_date_to_start_day()
        self._refresh_future_cycle_preview()

    def _refresh_future_cycle_preview(self, *_args) -> None:
        mode = str(self.future_cycle_mode_combo.currentData() or "calendar_month")
        start_day = 1 if mode == "calendar_month" else int(self.future_cycle_start_day_spin.value())
        effective = self.future_effective_date_edit.date().toString("yyyy-MM-dd")
        try:
            from app.utils.date_utils import normalize_settlement_cycle_rule, settlement_cycle_for_date

            candidate = normalize_settlement_cycle_rule({"rule_mode": mode, "start_day": start_day})
            cycle = settlement_cycle_for_date(date.fromisoformat(effective), candidate)
            self.future_rule_preview_label.setText(
                "{} 生效后，第一个周期：{}（{} ~ {}）".format(
                    effective,
                    cycle.code,
                    cycle.start.isoformat(),
                    cycle.end_inclusive.isoformat(),
                )
            )
        except (TypeError, ValueError):
            self.future_rule_preview_label.setText("请输入有效的生效日期和周期起始日")

    def on_add_future_cycle_rule(self) -> None:
        if self.settlement_cycle_service is None:
            return
        mode = str(self.future_cycle_mode_combo.currentData() or "calendar_month")
        start_day = 1 if mode == "calendar_month" else int(self.future_cycle_start_day_spin.value())
        effective_from = self.future_effective_date_edit.date().toString("yyyy-MM-dd")
        mode_label = "自然月" if mode == "calendar_month" else "每月{}日开始".format(start_day)
        answer = QMessageBox.question(
            self,
            "确认新增未来规则",
            "将从 {} 起使用{}。\n\n"
            "历史日报、历史周目标和历史统计不会被重新归类。\n"
            "请确认该日期是新周期的第一个工作周期边界。".format(effective_from, mode_label),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        ok, message, _status = self.settlement_cycle_service.schedule_successor_rule(
            rule_mode=mode,
            start_day=start_day,
            effective_from=effective_from,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "无法新增", message)
            self._load_cycle_rule()
            return
        QMessageBox.information(self, "提示", message)
        self._load_cycle_rule()
        self.settlement_cycle_rule_changed.emit()

    def on_cycle_mode_changed(self, *_args) -> None:
        mode = str(self.cycle_mode_combo.currentData() or "calendar_month")
        if mode == "calendar_month":
            self.cycle_start_day_spin.setValue(1)
        status = self.settlement_cycle_service.get_rule_status() if self.settlement_cycle_service else {}
        self.cycle_start_day_spin.setEnabled(mode == "fixed_start_day" and bool(status.get("is_editable", False)))
        self._refresh_cycle_rule_preview()

    def _refresh_cycle_rule_preview(self, *_args) -> None:
        if self.settlement_cycle_service is None:
            return
        mode = str(self.cycle_mode_combo.currentData() or "calendar_month")
        start_day = int(self.cycle_start_day_spin.value())
        try:
            if mode == "legacy_29":
                preview = self.settlement_cycle_service.preview_cycles(date.today(), 3)
            else:
                from app.utils.date_utils import normalize_settlement_cycle_rule, settlement_cycle_for_date

                candidate = normalize_settlement_cycle_rule(
                    {"rule_mode": mode, "start_day": start_day}
                )
                current = settlement_cycle_for_date(date.today(), candidate)
                preview = []
                for _index in range(3):
                    preview.append(
                        {
                            "cycle_code": current.code,
                            "start_date": current.start.isoformat(),
                            "end_date": current.end_inclusive.isoformat(),
                        }
                    )
                    current = settlement_cycle_for_date(current.end_exclusive, candidate)
            text = "； ".join(
                "{}（{} ~ {}）".format(item["cycle_code"], item["start_date"], item["end_date"])
                for item in preview
            )
        except (TypeError, ValueError):
            text = "请输入有效的周期起始日"
        self.cycle_rule_preview_label.setText(text)

    def on_save_cycle_rule(self) -> None:
        if self.settlement_cycle_service is None:
            return
        mode = str(self.cycle_mode_combo.currentData() or "calendar_month")
        ok, message, _status = self.settlement_cycle_service.update_initial_rule(
            mode,
            int(self.cycle_start_day_spin.value()),
            self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "无法保存", message)
            self._load_cycle_rule()
            return
        QMessageBox.information(self, "提示", message)
        self._load_cycle_rule()
        self.settlement_cycle_rule_changed.emit()

    def on_lock_cycle_rule(self) -> None:
        if self.settlement_cycle_service is None:
            return
        reply = QMessageBox.question(
            self,
            "确认锁定周期规则",
            "锁定后不能在系统内直接修改结算周期规则，且不会重算历史数据。确定继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok, message, _status = self.settlement_cycle_service.lock_active_rule(self._operator())
        if ok:
            QMessageBox.information(self, "提示", message)
            self._load_cycle_rule()
            self.settlement_cycle_rule_changed.emit()
        else:
            QMessageBox.warning(self, "锁定失败", message)

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
        self.cycle_start_day_spin.setMinimumHeight(max(20, int(round(30 * factor))))
        self.future_cycle_start_day_spin.setMinimumHeight(max(20, int(round(30 * factor))))
        self.future_effective_date_edit.setMinimumHeight(max(20, int(round(30 * factor))))
