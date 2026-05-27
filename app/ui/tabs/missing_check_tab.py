from __future__ import annotations

from app.utils.qt_compat import QDate
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import resolve_report_range


class MissingCheckTab(QWidget):
    def __init__(self, import_service, settings_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.import_service = import_service
        self.settings_service = settings_service
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        group = QGroupBox("导入缺失检查")
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

        self.expected_edit = QLineEdit()
        self.expected_edit.setPlaceholderText("可选：逗号分隔，例如 张三,李四")
        self.expected_edit.setText(self.settings_service.get("expected_managers", ""))

        btns = QHBoxLayout()
        self.query_btn = QPushButton("检查")
        self.save_btn = QPushButton("保存基线经理")
        self.reset_btn = QPushButton("重置")
        btns.addWidget(self.query_btn)
        btns.addWidget(self.save_btn)
        btns.addWidget(self.reset_btn)
        btns.addStretch()

        form.addRow("模式", self.mode_combo)
        form.addRow("基准日期", self.base_date)
        form.addRow("自定义开始", self.custom_start)
        form.addRow("自定义结束", self.custom_end)
        form.addRow("基线经理名单", self.expected_edit)
        form.addRow(btns)

        self.summary_label = QLabel("已收到：0，未收到：0，额外收到：0")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "区域",
            "团队",
            "客户经理",
            "状态",
            "收到记录数",
            "收到起始日期",
            "收到结束日期",
            "备注",
        ])
        self.table.setAlternatingRowColors(True)

        root.addWidget(group)
        root.addWidget(self.summary_label)
        root.addWidget(self.table)

        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.query_btn.clicked.connect(self.on_query)
        self.save_btn.clicked.connect(self.on_save_expected)
        self.reset_btn.clicked.connect(self.on_reset)
        self.on_mode_changed(self.mode_combo.currentText())

    def on_mode_changed(self, mode: str) -> None:
        is_custom = mode == "自定义"
        self.custom_start.setEnabled(is_custom)
        self.custom_end.setEnabled(is_custom)

    def _resolve(self) -> tuple[str, str] | None:
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
        except Exception:
            return None

    def _expected(self) -> list[str]:
        raw = self.expected_edit.text().strip()
        if not raw:
            return []
        return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]

    def on_save_expected(self) -> None:
        self.settings_service.set("expected_managers", self.expected_edit.text().strip())
        self.summary_label.setText("基线经理名单已保存")

    def on_query(self) -> None:
        resolved = self._resolve()
        if not resolved:
            self.summary_label.setText("日期范围无效")
            return

        start_date, end_date = resolved
        rows = self.import_service.check_missing_reports(start_date, end_date, self._expected())
        self.table.setRowCount(len(rows))

        received = 0
        missing = 0
        extra = 0
        for row_idx, row in enumerate(rows):
            status = row.get("status", "")
            if status == "已收到":
                received += 1
            elif status == "未收到":
                missing += 1
            elif status == "额外收到":
                extra += 1

            values = [
                row.get("region", ""),
                row.get("team", ""),
                row.get("account_manager_name", "") or row.get("manager_name", ""),
                status,
                str(row.get("received_record_count", 0)),
                row.get("received_start_date", ""),
                row.get("received_end_date", ""),
                row.get("note", ""),
            ]
            for col_idx, value in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        self.table.resizeColumnsToContents()
        self.summary_label.setText(f"已收到：{received}，未收到：{missing}，额外收到：{extra}")

    def on_reset(self) -> None:
        self.mode_combo.setCurrentText("周报")
        self.base_date.setDate(QDate.currentDate())
        self.custom_start.setDate(QDate.currentDate())
        self.custom_end.setDate(QDate.currentDate())
        self.expected_edit.setText(self.settings_service.get("expected_managers", ""))
        self.table.setRowCount(0)
        self.summary_label.setText("已收到：0，未收到：0，额外收到：0")
