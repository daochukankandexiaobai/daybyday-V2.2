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


class AdminActionLogsTab(QWidget):
    ACTION_OPTIONS = [
        "全部",
        "create_team",
        "archive_team",
        "delete_team",
        "restore_team",
        "edit_daily_record",
        "delete_daily_record",
    ]
    TARGET_OPTIONS = ["全部", "team", "daily_record", "account_manager", "cycle_target"]

    def __init__(self, admin_action_log_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.admin_action_log_service = admin_action_log_service
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

        filters.addWidget(QLabel("动作类型"))
        self.action_combo = QComboBox()
        self.action_combo.addItems(self.ACTION_OPTIONS)
        filters.addWidget(self.action_combo)

        filters.addWidget(QLabel("目标类型"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(self.TARGET_OPTIONS)
        filters.addWidget(self.target_combo)

        filters.addWidget(QLabel("操作人"))
        self.operator_edit = QLineEdit()
        self.operator_edit.setPlaceholderText("如：admin")
        filters.addWidget(self.operator_edit)

        self.query_btn = QPushButton("查询")
        self.reset_btn = QPushButton("重置")
        filters.addWidget(self.query_btn)
        filters.addWidget(self.reset_btn)
        filters.addStretch()

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "编号",
                "操作时间",
                "操作人",
                "动作类型",
                "目标类型",
                "目标ID",
                "备注",
                "操作前快照",
                "操作后快照",
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
        rows = self.admin_action_log_service.list_logs(
            start_date=self.start_date.date().toString("yyyy-MM-dd"),
            end_date=self.end_date.date().toString("yyyy-MM-dd"),
            action_type=self.action_combo.currentText(),
            target_type=self.target_combo.currentText(),
            operator=self.operator_edit.text().strip(),
        )
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                str(row.get("id", "")),
                str(row.get("action_time", "")),
                str(row.get("operator", "")),
                str(row.get("action_type", "")),
                str(row.get("target_type", "")),
                str(row.get("target_id", "")),
                str(row.get("note", "")),
                str(row.get("before_snapshot", "")),
                str(row.get("after_snapshot", "")),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def on_reset(self) -> None:
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        self.end_date.setDate(QDate.currentDate())
        self.action_combo.setCurrentText("全部")
        self.target_combo.setCurrentText("全部")
        self.operator_edit.clear()
        self.on_query()
