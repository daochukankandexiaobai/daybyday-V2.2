from __future__ import annotations

from pathlib import Path

from app.utils.qt_compat import QDate
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExportTab(QWidget):
    def __init__(self, export_service, settings_service, team_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.export_service = export_service
        self.settings_service = settings_service
        self.team_service = team_service
        self._build_ui()
        self.reload_teams()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        group = QGroupBox("JSON 导出")
        grid = QGridLayout(group)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["某日", "周报", "月报", "自定义"])

        self.team_combo = QComboBox()

        self.base_date = QDateEdit()
        self.base_date.setCalendarPopup(True)
        self.base_date.setDate(QDate.currentDate())

        self.custom_start = QDateEdit()
        self.custom_start.setCalendarPopup(True)
        self.custom_start.setDate(QDate.currentDate())

        self.custom_end = QDateEdit()
        self.custom_end.setCalendarPopup(True)
        self.custom_end.setDate(QDate.currentDate())

        self.output_dir = QLineEdit()
        default_dir = self.settings_service.get("default_export_dir", "") or str((Path.cwd() / "exports").resolve())
        self.output_dir.setText(default_dir)

        browse_row = QHBoxLayout()
        browse_row.setContentsMargins(0, 0, 0, 0)
        browse_row.setSpacing(6)
        self.browse_btn = QPushButton("选择目录")
        self.browse_btn.setProperty("buttonRole", "secondary")
        browse_row.addWidget(self.output_dir)
        browse_row.addWidget(self.browse_btn)

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(6)
        self.export_btn = QPushButton("导出")
        self.export_btn.setProperty("buttonRole", "primary")
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setProperty("buttonRole", "secondary")
        btns.addWidget(self.export_btn)
        btns.addWidget(self.reset_btn)
        btns.addStretch()

        grid.addWidget(QLabel("导出模式"), 0, 0)
        grid.addWidget(self.mode_combo, 0, 1)
        grid.addWidget(QLabel("自定义开始"), 0, 2)
        grid.addWidget(self.custom_start, 0, 3)

        grid.addWidget(QLabel("团队"), 1, 0)
        grid.addWidget(self.team_combo, 1, 1)
        grid.addWidget(QLabel("自定义结束"), 1, 2)
        grid.addWidget(self.custom_end, 1, 3)

        grid.addWidget(QLabel("基准日期"), 2, 0)
        grid.addWidget(self.base_date, 2, 1)
        grid.addWidget(QLabel("导出目录"), 2, 2)
        grid.addLayout(browse_row, 2, 3)

        hint = QLabel("导出为单团队、单时间范围 JSON 数据包，文件名自动包含结算周期与日期范围。")
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        grid.addWidget(hint, 3, 0, 1, 4)
        grid.addLayout(btns, 4, 0, 1, 4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 2)

        root.addWidget(group)
        root.addStretch()

        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.browse_btn.clicked.connect(self.on_browse)
        self.export_btn.clicked.connect(self.on_export)
        self.reset_btn.clicked.connect(self.on_reset)

    def _current_team_id(self) -> int:
        return int(self.team_combo.currentData() or 0)

    def reload_teams(self) -> None:
        teams = self.team_service.list_teams()
        self.team_combo.clear()
        for team in teams:
            label = f"{team['region']} / {team['team_name']} / {team['team_manager_name']}"
            self.team_combo.addItem(label, int(team["id"]))

        if self.team_combo.count() > 0:
            target = self.team_service.get_current_team_id()
            idx = 0
            for i in range(self.team_combo.count()):
                if int(self.team_combo.itemData(i) or 0) == target:
                    idx = i
                    break
            self.team_combo.setCurrentIndex(idx)

        self.on_mode_changed(self.mode_combo.currentText())

    def on_mode_changed(self, mode: str) -> None:
        is_custom = mode == "自定义"
        self.custom_start.setEnabled(is_custom)
        self.custom_end.setEnabled(is_custom)

    def on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择导出目录", self.output_dir.text().strip() or str(Path.cwd()))
        if path:
            self.output_dir.setText(path)

    def on_export(self) -> None:
        team_id = self._current_team_id()
        if team_id <= 0:
            QMessageBox.warning(self, "提示", "请先选择团队")
            return

        mode = self.mode_combo.currentText()
        custom_start = ""
        custom_end = ""
        if mode == "自定义":
            custom_start = self.custom_start.date().toString("yyyy-MM-dd")
            custom_end = self.custom_end.date().toString("yyyy-MM-dd")
            if custom_start > custom_end:
                QMessageBox.warning(self, "提示", "开始日期不能晚于结束日期")
                return

        ok, message, path = self.export_service.export_json(
            mode=mode,
            team_id=team_id,
            base_date=self.base_date.date().toString("yyyy-MM-dd"),
            custom_start=custom_start,
            custom_end=custom_end,
            output_dir=self.output_dir.text().strip(),
        )
        if ok:
            self.settings_service.set("default_export_dir", self.output_dir.text().strip())
            QMessageBox.information(self, "导出成功", f"{message}\n{path}")
        else:
            QMessageBox.warning(self, "导出失败", message)

    def on_reset(self) -> None:
        self.mode_combo.setCurrentText("某日")
        self.base_date.setDate(QDate.currentDate())
        self.custom_start.setDate(QDate.currentDate())
        self.custom_end.setDate(QDate.currentDate())
