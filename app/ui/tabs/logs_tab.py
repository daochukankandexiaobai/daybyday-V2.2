from __future__ import annotations

from app.utils.qt_compat import QDate
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import settlement_cycle_display_code


class LogsTab(QWidget):
    def __init__(self, import_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.import_service = import_service
        self._build_ui()
        self.on_query()

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
        filters.addWidget(QLabel("结果"))
        self.result_combo = QComboBox()
        self.result_combo.addItems(["全部", "success", "skipped", "failed", "conflict", "updated"])
        filters.addWidget(self.result_combo)

        filters.addWidget(QLabel("类型"))
        self.log_type_combo = QComboBox()
        self.log_type_combo.addItems(["全部", "import", "legacy_migration"])
        filters.addWidget(self.log_type_combo)

        filters.addWidget(QLabel("团队"))
        self.team_filter = QLineEdit()
        self.team_filter.setPlaceholderText("包含匹配")
        filters.addWidget(self.team_filter)

        filters.addWidget(QLabel("结算周期"))
        self.cycle_filter = QLineEdit()
        self.cycle_filter.setPlaceholderText("如 2026-04期")
        filters.addWidget(self.cycle_filter)

        self.query_btn = QPushButton("查询")
        self.reset_btn = QPushButton("重置")
        filters.addWidget(self.query_btn)
        filters.addWidget(self.reset_btn)
        filters.addStretch()

        self.table = QTableWidget(0, 19)
        self.table.setHorizontalHeaderLabels(
            [
                "log_id",
                "import_time",
                "log_type",
                "operator",
                "file_name",
                "team_name",
                "final_team",
                "settlement_cycle_code",
                "range_start",
                "range_end",
                "file_path",
                "export_id",
                "template_version",
                "result",
                "affected_record_count",
                "replaced_member_count",
                "replaced_record_count",
                "message",
                "recognized_summary",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        root.addLayout(filters)
        root.addWidget(self.table)

        self.query_btn.clicked.connect(self.on_query)
        self.reset_btn.clicked.connect(self.on_reset)

    def on_query(self) -> None:
        rows = self.import_service.list_logs(
            start_date=self.start_date.date().toString("yyyy-MM-dd"),
            end_date=self.end_date.date().toString("yyyy-MM-dd"),
            result=self.result_combo.currentText(),
        )

        team_kw = self.team_filter.text().strip()
        cycle_kw = self.cycle_filter.text().strip()
        selected_log_type = self.log_type_combo.currentText().strip()
        if team_kw:
            rows = [x for x in rows if team_kw in str(x.get("team_name", ""))]
        if cycle_kw:
            rows = [x for x in rows if cycle_kw in str(x.get("settlement_cycle_code", ""))]
        if selected_log_type and selected_log_type != "全部":
            rows = [x for x in rows if str(x.get("log_type", "import")) == selected_log_type]

        self.table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            values = [
                str(row.get("id", "")),
                row.get("import_time", ""),
                row.get("log_type", "import"),
                row.get("operator", ""),
                row.get("file_name", ""),
                row.get("team_name", ""),
                row.get("final_team", ""),
                settlement_cycle_display_code(cycle_code=str(row.get("settlement_cycle_code", ""))),
                row.get("range_start", ""),
                row.get("range_end", ""),
                row.get("file_path", ""),
                row.get("export_id", ""),
                row.get("template_version", ""),
                row.get("result", ""),
                str(row.get("affected_record_count", 0)),
                str(row.get("replaced_member_count", 0)),
                str(row.get("replaced_record_count", 0)),
                row.get("message", ""),
                row.get("recognized_summary", ""),
            ]
            for col_idx, value in enumerate(values):
                text = "" if value is None else str(value)
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(text))

        self.table.resizeColumnsToContents()

    def on_reset(self) -> None:
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        self.end_date.setDate(QDate.currentDate())
        self.result_combo.setCurrentText("全部")
        self.log_type_combo.setCurrentText("全部")
        self.team_filter.clear()
        self.cycle_filter.clear()
        self.on_query()
