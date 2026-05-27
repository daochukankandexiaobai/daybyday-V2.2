from __future__ import annotations

from pathlib import Path

from app.utils.format_utils import format_int, format_money, format_percent
from app.utils.qt_compat import QDate
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import resolve_report_range


class SummaryTab(QWidget):
    def __init__(self, summary_service, excel_service, settings_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary_service = summary_service
        self.excel_service = excel_service
        self.settings_service = settings_service
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        group = QGroupBox("公司汇总")
        form = QFormLayout(group)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["周报", "月报", "自定义"])

        self.base_date = QDateEdit()
        self.base_date.setCalendarPopup(True)
        self.base_date.setDate(QDate.currentDate())

        self.custom_start = QDateEdit()
        self.custom_start.setCalendarPopup(True)
        self.custom_start.setDate(QDate.currentDate())

        self.custom_end = QDateEdit()
        self.custom_end.setCalendarPopup(True)
        self.custom_end.setDate(QDate.currentDate())

        self.group_by_combo = QComboBox()
        self.group_by_combo.addItems(["全公司", "区域", "团队", "客户经理"])

        btns = QHBoxLayout()
        self.query_btn = QPushButton("查询")
        self.export_btn = QPushButton("导出Excel")
        self.reset_btn = QPushButton("重置")
        btns.addWidget(self.query_btn)
        btns.addWidget(self.export_btn)
        btns.addWidget(self.reset_btn)
        btns.addStretch()

        self.range_info = QLabel("")
        self.rule_info = QLabel("")

        form.addRow("模式", self.mode_combo)
        form.addRow("基准日期", self.base_date)
        form.addRow("自定义开始", self.custom_start)
        form.addRow("自定义结束", self.custom_end)
        form.addRow("聚合维度", self.group_by_combo)
        form.addRow(btns)

        self.table = QTableWidget(0, 13)
        self.table.setHorizontalHeaderLabels(
            [
                "分组",
                "记录数",
                "累计回款金额",
                "累计放款金额",
                "累计邀约",
                "累计签约量",
                "累计优质上门量",
                "签约率",
                "优质上门率",
                "批复率",
                "回款转化率",
                "目标完成进度",
                "结算周期目标",
            ]
        )
        self.table.setAlternatingRowColors(True)

        root.addWidget(group)
        root.addWidget(self.range_info)
        root.addWidget(self.rule_info)
        root.addWidget(self.table)

        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.query_btn.clicked.connect(self.on_query)
        self.export_btn.clicked.connect(self.on_export)
        self.reset_btn.clicked.connect(self.on_reset)
        self.on_mode_changed(self.mode_combo.currentText())

    def on_mode_changed(self, mode: str) -> None:
        is_custom = mode == "自定义"
        self.custom_start.setEnabled(is_custom)
        self.custom_end.setEnabled(is_custom)

    def _resolve_dates(self) -> tuple[str, str] | None:
        mode = self.mode_combo.currentText()
        try:
            if mode == "自定义":
                start, end = resolve_report_range(
                    mode,
                    self.base_date.date().toPython(),
                    self.custom_start.date().toPython(),
                    self.custom_end.date().toPython(),
                )
            else:
                start, end = resolve_report_range(mode, self.base_date.date().toPython())
            return start.isoformat(), end.isoformat()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "提示", str(exc))
            return None

    def on_query(self) -> None:
        resolved = self._resolve_dates()
        if not resolved:
            return

        start_date, end_date = resolved
        rows = self.summary_service.aggregate_records(start_date, end_date, self.group_by_combo.currentText())

        self.table.setRowCount(len(rows))
        cross_cycle = False
        for row_idx, row in enumerate(rows):
            cross_cycle = bool(row.get("cross_cycle", False))
            values = [
                row.get("group_name", ""),
                format_int(row.get("record_count")),
                format_money(row.get("repayment_amount_cumulative")),
                format_money(row.get("loan_amount_cumulative")),
                format_int(row.get("invitation_cumulative")),
                format_int(row.get("signing_count_cumulative")),
                format_int(row.get("quality_visit_count_cumulative")),
                format_percent(row.get("signing_rate")),
                format_percent(row.get("quality_visit_rate")),
                format_percent(row.get("approval_rate")),
                format_percent(row.get("repayment_conversion_rate")),
                "" if cross_cycle else format_percent(row.get("target_progress")),
                format_money(row.get("team_cycle_target")),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        self.table.resizeColumnsToContents()
        self.range_info.setText(f"范围：{start_date} ~ {end_date}")
        self.rule_info.setText("跨结算周期：目标完成进度不显示" if cross_cycle else "")

    def on_export(self) -> None:
        resolved = self._resolve_dates()
        if not resolved:
            return

        start_date, end_date = resolved
        default_dir = self.settings_service.get("default_export_dir", "") or str(Path.cwd())
        suggested = str(Path(default_dir) / f"公司汇总_{start_date}_{end_date}.xlsx")
        file_path, _ = QFileDialog.getSaveFileName(self, "导出Excel", suggested, "Excel Files (*.xlsx)")
        if not file_path:
            return

        dataset = self.summary_service.build_company_dataset(start_date, end_date)
        company_name = self.settings_service.get("company_name", "示例公司")
        ok, info = self.excel_service.export_company_report(
            file_path=file_path,
            company_name=company_name,
            start_date=start_date,
            end_date=end_date,
            dataset=dataset,
        )
        if ok:
            QMessageBox.information(self, "导出成功", f"已生成：\n{info}")
        else:
            QMessageBox.warning(self, "导出失败", info)

    def on_reset(self) -> None:
        self.mode_combo.setCurrentText("周报")
        self.base_date.setDate(QDate.currentDate())
        self.custom_start.setDate(QDate.currentDate())
        self.custom_end.setDate(QDate.currentDate())
        self.group_by_combo.setCurrentText("全公司")
        self.table.setRowCount(0)
        self.range_info.setText("")
        self.rule_info.setText("")
