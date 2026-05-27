from __future__ import annotations

from app.utils.qt_compat import QDate
from app.utils.qt_compat import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import settlement_cycle_display_code


class ConflictTab(QWidget):
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
        self.query_btn = QPushButton("查询冲突")
        self.reset_btn = QPushButton("重置")
        filters.addWidget(self.query_btn)
        filters.addWidget(self.reset_btn)
        filters.addStretch()

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "import_time",
                "file_name",
                "team_name",
                "settlement_cycle_code",
                "file_path",
                "export_id",
                "template_version",
                "result",
                "message",
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
        rows = self.import_service.list_conflict_logs(
            start_date=self.start_date.date().toString("yyyy-MM-dd"),
            end_date=self.end_date.date().toString("yyyy-MM-dd"),
        )
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                row.get("import_time", ""),
                row.get("file_name", ""),
                row.get("team_name", ""),
                settlement_cycle_display_code(cycle_code=str(row.get("settlement_cycle_code", ""))),
                row.get("file_path", ""),
                row.get("export_id", ""),
                row.get("template_version", ""),
                row.get("result", ""),
                row.get("message", ""),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def on_reset(self) -> None:
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        self.end_date.setDate(QDate.currentDate())
        self.on_query()
