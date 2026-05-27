from __future__ import annotations

from app.utils.qt_compat import QDate, Qt, Signal, dialog_exec
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.validators import (
    validate_non_negative_decimal_input,
    validate_non_negative_int_input,
)


class DailyRecordEditDialog(QDialog):
    INT_FIELDS = [
        ("intention_daily", "当日意向"),
        ("wechat_count_daily", "当日微信量"),
        ("visit_count_daily", "当日上门量"),
        ("invalid_visit_count_daily", "当日无效上门"),
        ("signing_count_daily", "当日签约量"),
        ("quality_visit_count_daily", "当日优质上门"),
        ("approval_customer_count_daily", "当日批复客户数"),
        ("repayment_customer_count_daily", "当日回款客户数"),
        ("debt_case_submit_count_daily", "当日债重进件数"),
        ("debt_case_repayment_count_daily", "当日债重回款件数"),
        ("large_order_repayment_count_daily", "当日大单回款笔数"),
    ]
    DECIMAL_FIELDS = [
        ("repayment_amount_daily", "当日回款金额"),
        ("loan_amount_daily", "当日放款金额"),
        ("debt_case_repayment_amount_daily", "当日债重回款金额"),
        ("large_order_repayment_amount_daily", "当日大单回款金额"),
    ]

    def __init__(self, record: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = record
        self._inputs: dict[str, QLineEdit] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("编辑日报记录")
        root = QVBoxLayout(self)

        info = QLabel(
            f"id={self.record.get('id', '')} | date={self.record.get('record_date', '')} | "
            f"team={self.record.get('team_name_snapshot', '')} | manager={self.record.get('account_manager_name_snapshot', '')}"
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()

        source_type_text = QLineEdit(str(self.record.get("source_type", "") or ""))
        source_type_text.setReadOnly(True)
        form.addRow("数据来源", source_type_text)

        source_file_text = QLineEdit(str(self.record.get("source_file", "") or ""))
        source_file_text.setReadOnly(True)
        form.addRow("来源文件", source_file_text)

        self.remark_edit = QLineEdit(str(self.record.get("remark", "") or ""))
        form.addRow("备注", self.remark_edit)

        for key, label in self.DECIMAL_FIELDS:
            edit = QLineEdit(str(float(self.record.get(key, 0) or 0)))
            self._inputs[key] = edit
            form.addRow(label, edit)
        for key, label in self.INT_FIELDS:
            edit = QLineEdit(str(int(self.record.get(key, 0) or 0)))
            self._inputs[key] = edit
            form.addRow(label, edit)

        root.addLayout(form)

        actions = QHBoxLayout()
        self.cancel_btn = QPushButton("取消")
        self.save_btn = QPushButton("保存")
        actions.addStretch()
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.save_btn)
        root.addLayout(actions)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)

    def collect_updates(self) -> tuple[bool, str, dict]:
        updates: dict = {"remark": self.remark_edit.text().strip()}

        for key, _ in self.DECIMAL_FIELDS:
            ok, value, err = validate_non_negative_decimal_input(self._inputs[key].text().strip())
            if not ok:
                return False, f"{key} 无效：{err}", {}
            updates[key] = value
        for key, _ in self.INT_FIELDS:
            ok, value, err = validate_non_negative_int_input(self._inputs[key].text().strip())
            if not ok:
                return False, f"{key} 无效：{err}", {}
            updates[key] = value

        if int(updates.get("invalid_visit_count_daily", 0)) > int(updates.get("visit_count_daily", 0)):
            return False, "无效上门不能大于上门量", {}
        if int(updates.get("quality_visit_count_daily", 0)) > int(updates.get("visit_count_daily", 0)):
            return False, "优质上门不能大于上门量", {}
        return True, "ok", updates


class LocalDataManageTab(QWidget):
    records_changed = Signal()

    SOURCE_OPTIONS = ["全部", "local", "local_submit", "imported", "legacy_migration"]

    def __init__(self, admin_data_service, operator_getter=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.admin_data_service = admin_data_service
        self.operator_getter = operator_getter
        self._rows: list[dict] = []
        self._updating_team_filter = False
        self._build_ui()
        self.reload_team_filters()
        self.on_query()

    def _operator(self) -> str:
        if callable(self.operator_getter):
            text = str(self.operator_getter() or "").strip()
            if text:
                return text
        return "admin"

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("开始日期"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        filters.addWidget(self.start_date)

        filters.addWidget(QLabel("结束日期"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        filters.addWidget(self.end_date)

        filters.addWidget(QLabel("客户经理"))
        self.manager_combo = QComboBox()
        filters.addWidget(self.manager_combo)

        filters.addWidget(QLabel("数据来源"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(self.SOURCE_OPTIONS)
        filters.addWidget(self.source_combo)

        filters.addWidget(QLabel("来源文件"))
        self.source_file_edit = QLineEdit()
        self.source_file_edit.setPlaceholderText("包含关键字")
        filters.addWidget(self.source_file_edit)

        self.query_btn = QPushButton("查询")
        self.reset_btn = QPushButton("重置")
        filters.addWidget(self.query_btn)
        filters.addWidget(self.reset_btn)
        root.addLayout(filters)

        team_row = QHBoxLayout()
        team_row.addWidget(QLabel("团队（可多选）"))
        self.team_list = QListWidget()
        self.team_list.setMaximumHeight(96)
        team_row.addWidget(self.team_list, 1)
        self.check_all_btn = QPushButton("全选")
        self.uncheck_all_btn = QPushButton("清空")
        team_row.addWidget(self.check_all_btn)
        team_row.addWidget(self.uncheck_all_btn)
        root.addLayout(team_row)

        actions = QHBoxLayout()
        self.edit_btn = QPushButton("编辑选中记录")
        self.delete_btn = QPushButton("删除选中记录")
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch()
        root.addLayout(actions)

        self.table = QTableWidget(0, 18)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "日期",
                "区域",
                "团队",
                "团队经理",
                "客户经理",
                "数据来源",
                "来源文件",
                "当日回款金额",
                "当日放款金额",
                "当日意向",
                "当日上门量",
                "当日签约量",
                "当日优质上门",
                "当日债重进件数",
                "版本",
                "更新时间",
                "备注",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        self.query_btn.clicked.connect(self.on_query)
        self.reset_btn.clicked.connect(self.on_reset)
        self.check_all_btn.clicked.connect(lambda: self._set_all_team_checked(True))
        self.uncheck_all_btn.clicked.connect(lambda: self._set_all_team_checked(False))
        self.team_list.itemChanged.connect(self.on_team_changed)
        self.edit_btn.clicked.connect(self.on_edit_selected)
        self.delete_btn.clicked.connect(self.on_delete_selected)

    def _selected_team_ids(self) -> list[int]:
        ids: list[int] = []
        for i in range(self.team_list.count()):
            item = self.team_list.item(i)
            if item is not None and item.checkState() == Qt.Checked:
                ids.append(int(item.data(Qt.UserRole) or 0))
        return [x for x in ids if x > 0]

    def _set_all_team_checked(self, checked: bool) -> None:
        self._updating_team_filter = True
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.team_list.count()):
            item = self.team_list.item(i)
            if item is not None:
                item.setCheckState(state)
        self._updating_team_filter = False
        self.reload_manager_options()

    def reload_team_filters(self) -> None:
        teams = self.admin_data_service.list_team_options()
        self._updating_team_filter = True
        self.team_list.clear()
        for team in teams:
            suffix = "" if int(team.get("is_active", 1)) == 1 else " [已归档]"
            label = f"{team.get('region', '')} / {team.get('team_name', '')}{suffix}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, int(team.get("id", 0) or 0))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.team_list.addItem(item)
        self._updating_team_filter = False
        self.reload_manager_options()

    def reload_manager_options(self) -> None:
        team_ids = self._selected_team_ids()
        managers = self.admin_data_service.list_account_manager_options(team_ids=team_ids)
        current = int(self.manager_combo.currentData() or 0)
        self.manager_combo.blockSignals(True)
        self.manager_combo.clear()
        self.manager_combo.addItem("全部", 0)
        for item in managers:
            suffix = "" if int(item.get("is_active", 1)) == 1 else " [已归档]"
            label = f"{item.get('name', '')}{suffix}"
            self.manager_combo.addItem(label, int(item.get("id", 0) or 0))
        target = 0
        for idx in range(self.manager_combo.count()):
            if int(self.manager_combo.itemData(idx) or 0) == current:
                target = idx
                break
        self.manager_combo.setCurrentIndex(target)
        self.manager_combo.blockSignals(False)

    def on_team_changed(self, _item: QListWidgetItem) -> None:
        if self._updating_team_filter:
            return
        self.reload_manager_options()

    def on_query(self) -> None:
        team_ids = self._selected_team_ids()
        manager_id = int(self.manager_combo.currentData() or 0)
        source_type = self.source_combo.currentText()
        rows = self.admin_data_service.list_daily_records(
            start_date=self.start_date.date().toString("yyyy-MM-dd"),
            end_date=self.end_date.date().toString("yyyy-MM-dd"),
            team_ids=team_ids,
            account_manager_id=manager_id if manager_id > 0 else None,
            source_type=source_type,
            source_file_keyword=self.source_file_edit.text().strip(),
        )
        self._rows = rows
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                str(row.get("id", "")),
                str(row.get("record_date", "")),
                str(row.get("region", "")),
                str(row.get("team_name_snapshot", "")),
                str(row.get("team_manager_name_snapshot", "")),
                str(row.get("account_manager_name_snapshot", "")),
                str(row.get("source_type", "")),
                str(row.get("source_file", "")),
                f"{float(row.get('repayment_amount_daily', 0) or 0):.2f}",
                f"{float(row.get('loan_amount_daily', 0) or 0):.2f}",
                str(int(row.get("intention_daily", 0) or 0)),
                str(int(row.get("visit_count_daily", 0) or 0)),
                str(int(row.get("signing_count_daily", 0) or 0)),
                str(int(row.get("quality_visit_count_daily", 0) or 0)),
                str(int(row.get("debt_case_submit_count_daily", 0) or 0)),
                str(int(row.get("version", 0) or 0)),
                str(row.get("updated_at", "")),
                str(row.get("remark", "")),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _selected_row_ids(self) -> list[int]:
        ids: list[int] = []
        for idx in self.table.selectionModel().selectedRows():
            row = idx.row()
            item = self.table.item(row, 0)
            if item is not None:
                ids.append(int(item.text() or 0))
        return [x for x in ids if x > 0]

    def on_edit_selected(self) -> None:
        ids = self._selected_row_ids()
        if len(ids) != 1:
            QMessageBox.warning(self, "提示", "请仅选择一条记录进行编辑")
            return
        row_id = ids[0]
        record = self.admin_data_service.get_daily_record(row_id)
        if record is None:
            QMessageBox.warning(self, "提示", "记录不存在")
            return

        dialog = DailyRecordEditDialog(record, self)
        if dialog_exec(dialog) != QDialog.Accepted:
            return

        ok, message, updates = dialog.collect_updates()
        if not ok:
            QMessageBox.warning(self, "校验失败", message)
            return

        ok, message, _after = self.admin_data_service.update_daily_record(
            row_id=row_id,
            updates=updates,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "保存失败", message)
            return

        QMessageBox.information(self, "提示", message)
        self.on_query()
        self.records_changed.emit()

    def on_delete_selected(self) -> None:
        ids = self._selected_row_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先选择要删除的记录")
            return

        answer = QMessageBox.question(
            self,
            "二次确认",
            f"确定删除 {len(ids)} 条选中记录？删除后不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        success, failed = self.admin_data_service.delete_daily_records(ids, operator=self._operator())
        QMessageBox.information(self, "提示", f"删除完成：成功 {success}，失败 {failed}")
        self.on_query()
        self.records_changed.emit()

    def on_reset(self) -> None:
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        self.end_date.setDate(QDate.currentDate())
        self.source_combo.setCurrentText("全部")
        self.source_file_edit.clear()
        self.reload_team_filters()
        self.on_query()
