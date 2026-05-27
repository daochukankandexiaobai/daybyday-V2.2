from __future__ import annotations

from app.utils.qt_compat import Signal, Qt, dialog_exec
from app.utils.qt_compat import (
    QDialog,
    QFileDialog,
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

from app.utils.date_utils import parse_date
from app.utils.validators import safe_decimal, safe_int


class LegacyMigrationConfirmDialog(QDialog):
    """旧版迁移预加载确认框。"""

    RECORD_COLUMNS = [
        ("record_date", "日期", "text"),
        ("account_manager_name", "客户经理", "text"),
        ("repayment_amount_daily", "当日回款金额", "amount"),
        ("loan_amount_daily", "当日放款金额", "amount"),
        ("intention_daily", "当日意向", "int"),
        ("wechat_count_daily", "当日微信量", "int"),
        ("visit_count_daily", "当日上门量", "int"),
        ("invalid_visit_count_daily", "当日无效上门", "int"),
        ("signing_count_daily", "当日签约量", "int"),
        ("quality_visit_count_daily", "当日优质上门", "int"),
        ("approval_customer_count_daily", "当日批复客户数", "int"),
        ("repayment_customer_count_daily", "当日回款客户数", "int"),
        ("debt_case_submit_count_daily", "当日债重进件数", "int"),
        ("debt_case_repayment_count_daily", "当日债重回款件数", "int"),
        ("debt_case_repayment_amount_daily", "当日债重回款金额", "amount"),
        ("large_order_repayment_count_daily", "当日大单回款笔数", "int"),
        ("large_order_repayment_amount_daily", "当日大单回款金额", "amount"),
        ("remark", "备注", "text"),
    ]

    MEMBER_COLUMNS = ["客户经理", "结算周期", "目标"]

    def __init__(self, preview_payload: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview_payload = preview_payload
        self.confirmed_payload: dict | None = None
        self.setWindowTitle("旧版 JSON 预加载确认")
        self.resize(1360, 820)
        self._build_ui()
        self._fill_from_preview()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.summary_label)

        team_group = QGroupBox("团队基础设置")
        team_form = QFormLayout(team_group)
        self.region_edit = QLineEdit()
        self.team_name_edit = QLineEdit()
        self.team_manager_edit = QLineEdit()
        team_form.addRow("区域", self.region_edit)
        team_form.addRow("团队名称", self.team_name_edit)
        team_form.addRow("团队经理", self.team_manager_edit)
        root.addWidget(team_group)

        member_group = QGroupBox("团队成员与目标（可编辑）")
        member_layout = QVBoxLayout(member_group)
        member_actions = QHBoxLayout()
        self.add_member_btn = QPushButton("新增成员行")
        self.remove_member_btn = QPushButton("删除成员行")
        member_actions.addWidget(self.add_member_btn)
        member_actions.addWidget(self.remove_member_btn)
        member_actions.addStretch()
        self.member_table = QTableWidget(0, len(self.MEMBER_COLUMNS))
        self.member_table.setHorizontalHeaderLabels(self.MEMBER_COLUMNS)
        member_layout.addLayout(member_actions)
        member_layout.addWidget(self.member_table)
        root.addWidget(member_group)

        record_group = QGroupBox("每日数据 records（可编辑）")
        record_layout = QVBoxLayout(record_group)
        record_actions = QHBoxLayout()
        self.add_record_btn = QPushButton("新增日报行")
        self.remove_record_btn = QPushButton("删除日报行")
        record_actions.addWidget(self.add_record_btn)
        record_actions.addWidget(self.remove_record_btn)
        record_actions.addStretch()
        self.record_table = QTableWidget(0, len(self.RECORD_COLUMNS))
        self.record_table.setHorizontalHeaderLabels([x[1] for x in self.RECORD_COLUMNS])
        record_layout.addLayout(record_actions)
        record_layout.addWidget(self.record_table)
        root.addWidget(record_group, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.confirm_btn = QPushButton("确认迁移")
        self.cancel_btn = QPushButton("取消")
        bottom.addWidget(self.confirm_btn)
        bottom.addWidget(self.cancel_btn)
        root.addLayout(bottom)

        self.add_member_btn.clicked.connect(self.on_add_member)
        self.remove_member_btn.clicked.connect(self.on_remove_member)
        self.add_record_btn.clicked.connect(self.on_add_record)
        self.remove_record_btn.clicked.connect(self.on_remove_record)
        self.confirm_btn.clicked.connect(self.on_confirm)
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def _set_item(table: QTableWidget, row: int, col: int, value) -> None:
        table.setItem(row, col, QTableWidgetItem(str(value if value is not None else "")))

    def _fill_from_preview(self) -> None:
        team = self.preview_payload.get("team", {})
        self.region_edit.setText(str(team.get("region", "")))
        self.team_name_edit.setText(str(team.get("team_name", "")))
        self.team_manager_edit.setText(str(team.get("team_manager_name", "")))

        summary = str(self.preview_payload.get("recognized_summary", ""))
        start_date = str(self.preview_payload.get("recognized_range", {}).get("start_date", ""))
        end_date = str(self.preview_payload.get("recognized_range", {}).get("end_date", ""))
        self.summary_label.setText(
            f"文件：{self.preview_payload.get('file_name', '')}"
            f"\n识别摘要：{summary}"
            f"\n时间范围：{start_date} ~ {end_date}"
            "\n请确认并按需修改后再执行迁移。"
        )

        members = self.preview_payload.get("members") or []
        self.member_table.setRowCount(len(members))
        for i, row in enumerate(members):
            self._set_item(self.member_table, i, 0, row.get("account_manager_name", ""))
            self._set_item(self.member_table, i, 1, row.get("settlement_cycle_code", ""))
            self._set_item(self.member_table, i, 2, row.get("target_amount", 0))

        records = self.preview_payload.get("records") or []
        self.record_table.setRowCount(len(records))
        for r_idx, row in enumerate(records):
            for c_idx, (key, _label, _kind) in enumerate(self.RECORD_COLUMNS):
                self._set_item(self.record_table, r_idx, c_idx, row.get(key, ""))

        self.member_table.resizeColumnsToContents()
        self.record_table.resizeColumnsToContents()

    def on_add_member(self) -> None:
        row = self.member_table.rowCount()
        self.member_table.insertRow(row)

    def on_remove_member(self) -> None:
        row = self.member_table.currentRow()
        if row >= 0:
            self.member_table.removeRow(row)

    def on_add_record(self) -> None:
        row = self.record_table.rowCount()
        self.record_table.insertRow(row)

    def on_remove_record(self) -> None:
        row = self.record_table.currentRow()
        if row >= 0:
            self.record_table.removeRow(row)

    @staticmethod
    def _cell_text(table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item is not None else ""

    def _collect_payload(self) -> dict | None:
        region = self.region_edit.text().strip()
        team_name = self.team_name_edit.text().strip()
        team_manager = self.team_manager_edit.text().strip()

        if not region or not team_name or not team_manager:
            QMessageBox.warning(self, "提示", "区域、团队名称、团队经理不能为空")
            return None

        members: list[dict] = []
        for row in range(self.member_table.rowCount()):
            manager_name = self._cell_text(self.member_table, row, 0)
            cycle_code = self._cell_text(self.member_table, row, 1)
            target_amount = safe_decimal(self._cell_text(self.member_table, row, 2))
            if not manager_name:
                continue
            members.append(
                {
                    "account_manager_name": manager_name,
                    "settlement_cycle_code": cycle_code,
                    "target_amount": target_amount,
                }
            )

        records: list[dict] = []
        for row in range(self.record_table.rowCount()):
            record_row: dict = {}
            for col, (key, _label, kind) in enumerate(self.RECORD_COLUMNS):
                raw = self._cell_text(self.record_table, row, col)
                if kind == "int":
                    record_row[key] = safe_int(raw)
                elif kind == "amount":
                    record_row[key] = safe_decimal(raw)
                else:
                    record_row[key] = raw

            record_date = str(record_row.get("record_date", "")).strip()
            account_manager_name = str(record_row.get("account_manager_name", "")).strip()
            if not record_date and not account_manager_name:
                continue
            if not record_date or not account_manager_name:
                QMessageBox.warning(self, "提示", f"第 {row + 1} 行日报缺少日期或客户经理")
                return None
            try:
                parse_date(record_date)
            except Exception:  # noqa: BLE001
                QMessageBox.warning(self, "提示", f"第 {row + 1} 行日期格式非法：{record_date}")
                return None
            records.append(record_row)

        if not records:
            QMessageBox.warning(self, "提示", "至少保留一行日报数据")
            return None

        member_names = {str(x.get("account_manager_name", "")).strip().casefold() for x in members}
        for row in records:
            manager_name = str(row.get("account_manager_name", "")).strip()
            if manager_name.casefold() in member_names:
                continue
            members.append(
                {
                    "account_manager_name": manager_name,
                    "settlement_cycle_code": "",
                    "target_amount": 0.0,
                }
            )
            member_names.add(manager_name.casefold())

        return {
            "file_name": self.preview_payload.get("file_name", ""),
            "file_path": self.preview_payload.get("file_path", ""),
            "source_export_id": self.preview_payload.get("source_export_id", ""),
            "recognized_summary": self.preview_payload.get("recognized_summary", ""),
            "recognized_identity": self.preview_payload.get("recognized_identity", {}),
            "team": {
                "region": region,
                "team_name": team_name,
                "team_manager_name": team_manager,
            },
            "members": members,
            "records": records,
        }

    def on_confirm(self) -> None:
        payload = self._collect_payload()
        if payload is None:
            return
        self.confirmed_payload = payload
        self.accept()


class LegacyMigrationTab(QWidget):
    migration_finished = Signal()

    def __init__(self, legacy_migration_service, operator_getter=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.legacy_migration_service = legacy_migration_service
        self.operator_getter = operator_getter or (lambda: "admin")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        actions = QHBoxLayout()
        self.select_btn = QPushButton("选择旧版JSON并预加载")
        self.clear_btn = QPushButton("清空")
        actions.addWidget(self.select_btn)
        actions.addWidget(self.clear_btn)
        actions.addStretch()

        self.file_label = QLabel("未选择文件")
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.file_label.setWordWrap(True)

        self.result_label = QLabel("等待操作")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        root.addLayout(actions)
        root.addWidget(self.file_label)
        root.addWidget(self.result_label)
        root.addStretch()

        self.select_btn.clicked.connect(self.on_select_file)
        self.clear_btn.clicked.connect(self.on_clear)

    def on_clear(self) -> None:
        self.file_label.setText("未选择文件")
        self.result_label.setText("等待操作")

    def on_select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择旧版 JSON 文件", "", "JSON Files (*.json)")
        if not file_path:
            return

        self.file_label.setText(f"文件：{file_path}")
        preview = self.legacy_migration_service.preview_legacy_file(file_path)
        if not preview.get("ok"):
            self.result_label.setText(str(preview.get("message", "识别失败")))
            QMessageBox.warning(self, "旧版迁移", str(preview.get("message", "识别失败")))
            return

        dialog = LegacyMigrationConfirmDialog(preview, self)
        if dialog_exec(dialog) != QDialog.Accepted:
            self.result_label.setText("已取消迁移，未写入数据库")
            return

        confirmed_payload = dialog.confirmed_payload or {}
        ok, message, stats = self.legacy_migration_service.apply_migration(
            confirmed_payload,
            operator=str(self.operator_getter() or "admin"),
        )
        if not ok:
            self.result_label.setText(message)
            QMessageBox.warning(self, "旧版迁移", message)
            return

        detail = (
            f"迁移成功：团队={stats.get('team_name', '')}，"
            f"范围={stats.get('range_start', '')}~{stats.get('range_end', '')}，"
            f"成员={stats.get('member_count', 0)}，"
            f"替换旧记录={stats.get('deleted_count', 0)}，写入新记录={stats.get('inserted_count', 0)}"
        )
        self.result_label.setText(detail)
        QMessageBox.information(self, "旧版迁移", detail)
        self.migration_finished.emit()
