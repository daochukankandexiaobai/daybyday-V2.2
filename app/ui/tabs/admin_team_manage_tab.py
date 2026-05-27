from __future__ import annotations

from app.utils.qt_compat import QDate, Signal
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import settlement_cycle_for_date
from app.utils.validators import validate_non_negative_decimal_input


class AdminTeamManageTab(QWidget):
    team_changed = Signal()

    STATUS_ALL = "全部"
    STATUS_ACTIVE = "启用中"
    STATUS_INACTIVE = "已归档"

    def __init__(self, admin_team_service, team_service, operator_getter=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.admin_team_service = admin_team_service
        self.team_service = team_service
        self.operator_getter = operator_getter
        self.current_team_id: int | None = None
        self.current_team_active = True
        self.teams: list[dict] = []
        self._build_ui()
        self.reload_teams()

    def _operator(self) -> str:
        if callable(self.operator_getter):
            text = str(self.operator_getter() or "").strip()
            if text:
                return text
        return "admin"

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("状态"))
        self.status_combo = QComboBox()
        self.status_combo.addItems([self.STATUS_ALL, self.STATUS_ACTIVE, self.STATUS_INACTIVE])
        top.addWidget(self.status_combo)

        top.addWidget(QLabel("团队"))
        self.team_picker = QComboBox()
        top.addWidget(self.team_picker, 1)

        self.new_btn = QPushButton("新建团队")
        self.reload_btn = QPushButton("刷新")
        self.archive_delete_btn = QPushButton("归档团队")
        self.restore_btn = QPushButton("恢复")
        top.addWidget(self.new_btn)
        top.addWidget(self.reload_btn)
        top.addWidget(self.archive_delete_btn)
        top.addWidget(self.restore_btn)
        root.addLayout(top)

        base_group = QGroupBox("团队基础信息")
        base_form = QFormLayout(base_group)
        self.region_edit = QLineEdit()
        self.team_name_edit = QLineEdit()
        self.team_manager_edit = QLineEdit()
        self.base_date = QDateEdit()
        self.base_date.setCalendarPopup(True)
        self.base_date.setDate(QDate.currentDate())
        self.cycle_code_label = QLabel("-")
        self.current_state_label = QLabel("-")
        self.dependency_label = QLabel("")
        self.dependency_label.setWordWrap(True)

        base_form.addRow("区域", self.region_edit)
        base_form.addRow("团队名称", self.team_name_edit)
        base_form.addRow("团队经理", self.team_manager_edit)
        base_form.addRow("周期基准日期", self.base_date)
        base_form.addRow("结算周期", self.cycle_code_label)
        base_form.addRow("当前状态", self.current_state_label)
        base_form.addRow("删除检查", self.dependency_label)
        root.addWidget(base_group)

        member_group = QGroupBox("客户经理与结算周期目标")
        member_layout = QVBoxLayout(member_group)
        member_actions = QHBoxLayout()
        self.add_member_btn = QPushButton("新增成员")
        self.remove_member_btn = QPushButton("删除成员")
        self.save_btn = QPushButton("保存团队配置")
        member_actions.addWidget(self.add_member_btn)
        member_actions.addWidget(self.remove_member_btn)
        member_actions.addWidget(self.save_btn)
        member_actions.addStretch()

        self.member_table = QTableWidget(0, 2)
        self.member_table.setHorizontalHeaderLabels(["客户经理", "结算周期目标"])
        self.member_table.setAlternatingRowColors(True)

        member_layout.addLayout(member_actions)
        member_layout.addWidget(self.member_table)
        root.addWidget(member_group, 1)

        self.status_combo.currentTextChanged.connect(self.reload_teams)
        self.team_picker.currentIndexChanged.connect(self.on_team_changed)
        self.new_btn.clicked.connect(self.on_new_team)
        self.reload_btn.clicked.connect(self.reload_teams)
        self.archive_delete_btn.clicked.connect(self.on_archive_or_delete)
        self.restore_btn.clicked.connect(self.on_restore)
        self.add_member_btn.clicked.connect(self.on_add_member)
        self.remove_member_btn.clicked.connect(self.on_remove_member)
        self.save_btn.clicked.connect(self.on_save)
        self.base_date.dateChanged.connect(self.refresh_cycle_related)

    def _cycle_code(self) -> str:
        return settlement_cycle_for_date(self.base_date.date().toPython()).code

    def _set_current_state(self, team: dict | None) -> None:
        if not team:
            self.current_state_label.setText("新建")
            self.current_team_active = True
            return
        active = int(team.get("is_active", 1)) == 1
        self.current_team_active = active
        self.current_state_label.setText("启用中" if active else "已归档")
        self.restore_btn.setEnabled(not active)

    def _clear_editor(self) -> None:
        self.current_team_id = None
        self.region_edit.clear()
        self.team_name_edit.clear()
        self.team_manager_edit.clear()
        self.member_table.setRowCount(0)
        self.dependency_label.setText("")
        self.cycle_code_label.setText(self._cycle_code())
        self._set_current_state(None)

    def reload_teams(self, *_args) -> None:
        status = self.status_combo.currentText()
        if status == self.STATUS_ACTIVE:
            self.teams = self.admin_team_service.list_teams(status="active")
        elif status == self.STATUS_INACTIVE:
            self.teams = self.admin_team_service.list_teams(status="inactive")
        else:
            self.teams = self.admin_team_service.list_teams(status="all")

        selected_id = self.current_team_id
        self.team_picker.blockSignals(True)
        self.team_picker.clear()
        for team in self.teams:
            suffix = "" if int(team.get("is_active", 1)) == 1 else " [已归档]"
            label = f"{team['region']} / {team['team_name']} / {team['team_manager_name']}{suffix}"
            self.team_picker.addItem(label, int(team["id"]))
        self.team_picker.blockSignals(False)

        if not self.teams:
            self._clear_editor()
            self.team_picker.setEnabled(False)
            self.archive_delete_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            return

        self.team_picker.setEnabled(True)
        target_index = 0
        if selected_id:
            for idx in range(self.team_picker.count()):
                if int(self.team_picker.itemData(idx) or 0) == int(selected_id):
                    target_index = idx
                    break
        self.team_picker.setCurrentIndex(target_index)
        self.load_team(int(self.team_picker.itemData(target_index) or 0))

    def on_team_changed(self, _index: int) -> None:
        team_id = int(self.team_picker.currentData() or 0)
        if team_id > 0:
            self.load_team(team_id)

    def load_team(self, team_id: int) -> None:
        team = self.admin_team_service.get_team(team_id)
        if team is None:
            self._clear_editor()
            return

        self.current_team_id = int(team["id"])
        self.region_edit.setText(str(team.get("region", "")))
        self.team_name_edit.setText(str(team.get("team_name", "")))
        self.team_manager_edit.setText(str(team.get("team_manager_name", "")))
        self._set_current_state(team)
        self.refresh_cycle_related()
        self._refresh_delete_hint()
        self.archive_delete_btn.setEnabled(True)

    def refresh_cycle_related(self, *_args) -> None:
        cycle_code = self._cycle_code()
        self.cycle_code_label.setText(cycle_code)

        if not self.current_team_id:
            return

        members = self.team_service.list_members_with_targets(self.current_team_id, cycle_code)
        self.member_table.setRowCount(len(members))
        for row_idx, row in enumerate(members):
            self.member_table.setItem(row_idx, 0, QTableWidgetItem(str(row.get("account_manager_name", ""))))
            self.member_table.setItem(row_idx, 1, QTableWidgetItem(f"{float(row.get('target_amount', 0) or 0):.2f}"))
        self.member_table.resizeColumnsToContents()

    def _collect_members(self) -> list[dict]:
        members: list[dict] = []
        seen_names: set[str] = set()
        for row in range(self.member_table.rowCount()):
            name_item = self.member_table.item(row, 0)
            target_item = self.member_table.item(row, 1)
            name = (name_item.text() if name_item else "").strip()
            target = (target_item.text() if target_item else "0").strip()
            if not name:
                continue
            name_key = name.casefold()
            if name_key in seen_names:
                raise ValueError(f"第{row + 1}行客户经理重复：{name}")
            seen_names.add(name_key)

            ok, amount, err = validate_non_negative_decimal_input(target)
            if not ok:
                raise ValueError(f"第{row + 1}行目标值无效：{err}")
            members.append({"account_manager_name": name, "target_amount": amount})
        return members

    def _refresh_delete_hint(self) -> None:
        if not self.current_team_id:
            self.dependency_label.setText("")
            return
        info = self.admin_team_service.inspect_delete_team(self.current_team_id)
        if not info.get("ok"):
            self.dependency_label.setText(str(info.get("message", "")))
            return
        counts = info.get("counts", {})
        hint = (
            f"daily_records={counts.get('daily_records', 0)}; "
            f"import_logs={counts.get('import_logs', 0)}; "
            f"migration_logs={counts.get('migration_logs', 0)}; "
            f"account_managers={counts.get('account_managers', 0)}; "
            f"cycle_targets={counts.get('cycle_targets', 0)}"
        )
        self.dependency_label.setText(hint)

    def on_new_team(self) -> None:
        self._clear_editor()
        self.archive_delete_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)

    def on_add_member(self) -> None:
        row = self.member_table.rowCount()
        self.member_table.insertRow(row)
        self.member_table.setItem(row, 0, QTableWidgetItem(""))
        self.member_table.setItem(row, 1, QTableWidgetItem("0"))

    def on_remove_member(self) -> None:
        row = self.member_table.currentRow()
        if row >= 0:
            self.member_table.removeRow(row)

    def on_save(self) -> None:
        try:
            members = self._collect_members()
        except ValueError as exc:
            QMessageBox.warning(self, "校验失败", str(exc))
            return

        if not members:
            QMessageBox.warning(self, "提示", "请至少保留一位客户经理")
            return

        ok, msg, saved_team_id = self.admin_team_service.save_team_config(
            team_id=self.current_team_id,
            region=self.region_edit.text().strip(),
            team_name=self.team_name_edit.text().strip(),
            team_manager_name=self.team_manager_edit.text().strip(),
            settlement_cycle_code=self._cycle_code(),
            members=members,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "保存失败", msg)
            return

        QMessageBox.information(self, "提示", msg)
        self.current_team_id = int(saved_team_id or 0) or None
        self.reload_teams()
        self.team_changed.emit()

    def on_archive_or_delete(self) -> None:
        team_id = int(self.current_team_id or 0)
        if team_id <= 0:
            QMessageBox.warning(self, "提示", "请先选择团队")
            return

        info = self.admin_team_service.inspect_delete_team(team_id)
        if not info.get("ok"):
            QMessageBox.warning(self, "提示", str(info.get("message", "团队不存在")))
            return

        team = info.get("team", {}) or {}
        counts = info.get("counts", {}) or {}
        confirm_text = (
            "该操作将归档（停用）团队，不会物理删除任何历史数据。\n\n"
            f"团队：{team.get('region', '')} / {team.get('team_name', '')}\n"
            f"daily_records={counts.get('daily_records', 0)}\n"
            f"cycle_targets={counts.get('cycle_targets', 0)}\n"
            f"import_logs={counts.get('import_logs', 0)}\n"
            f"migration_logs={counts.get('migration_logs', 0)}\n\n"
            "归档后该团队和下属客户经理将停用，不能继续录入新日报；历史数据仍可查询。\n\n是否继续？"
        )

        answer = QMessageBox.question(
            self,
            "二次确认",
            confirm_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        ok, msg, mode = self.admin_team_service.delete_team_safely(team_id=team_id, operator=self._operator())
        if not ok:
            QMessageBox.warning(self, "操作失败", msg)
            return

        QMessageBox.information(self, "提示", f"{msg}\n执行方式：{mode}")
        self.current_team_id = None
        self.reload_teams()
        self.team_changed.emit()

    def on_restore(self) -> None:
        team_id = int(self.current_team_id or 0)
        if team_id <= 0:
            QMessageBox.warning(self, "提示", "请先选择团队")
            return
        ok, msg = self.admin_team_service.restore_team(team_id=team_id, operator=self._operator())
        if not ok:
            QMessageBox.warning(self, "恢复失败", msg)
            return
        QMessageBox.information(self, "提示", msg)
        self.reload_teams()
        self.team_changed.emit()

    def apply_view_scale(self, factor: float) -> None:
        row_height = max(22, int(round(30 * factor)))
        header_height = max(24, int(round(34 * factor)))
        self.member_table.verticalHeader().setDefaultSectionSize(row_height)
        self.member_table.horizontalHeader().setMinimumHeight(header_height)
