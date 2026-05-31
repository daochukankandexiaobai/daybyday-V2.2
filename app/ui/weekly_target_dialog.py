from __future__ import annotations

from typing import Any

from app.utils.date_utils import today_str
from app.utils.qt_compat import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)
from app.utils.validators import (
    validate_non_negative_decimal_input,
    validate_non_negative_int_input,
)


class WeeklyTargetDialog(QDialog):
    targets_saved = Signal()

    COL_MANAGER = 0
    COL_VISIT = 1
    COL_QUALITY_VISIT = 2
    COL_REPAYMENT = 3

    def __init__(
        self,
        weekly_target_service,
        team_id: int,
        settlement_cycle_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.weekly_target_service = weekly_target_service
        self.team_id = int(team_id or 0)
        self.settlement_cycle_code = str(settlement_cycle_code or "").strip()
        self.weeks: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.current_week_index = 1
        self.was_saved = False
        self._loading = False
        self._dirty = False

        self._build_ui()
        self.reload_data()

    def _build_ui(self) -> None:
        self.setWindowTitle("周期目标设置")
        self.setModal(True)
        self.resize(760, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.info_group = QGroupBox("周期信息")
        info_layout = QGridLayout(self.info_group)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setHorizontalSpacing(14)
        info_layout.setVerticalSpacing(6)

        self.team_label = QLabel("-")
        self.manager_label = QLabel("-")
        self.cycle_label = QLabel("-")
        self.range_label = QLabel("-")
        self.week_count_label = QLabel("-")
        self.current_week_label = QLabel("-")
        self.current_week_label.setObjectName("currentWeekValue")
        self.current_week_range_label = QLabel("-")
        self.current_week_range_label.setObjectName("currentWeekValue")

        info_layout.addWidget(self._title_label("团队名称"), 0, 0)
        info_layout.addWidget(self.team_label, 0, 1)
        info_layout.addWidget(self._title_label("团队经理"), 0, 2)
        info_layout.addWidget(self.manager_label, 0, 3)
        info_layout.addWidget(self._title_label("当前结算周期"), 1, 0)
        info_layout.addWidget(self.cycle_label, 1, 1)
        info_layout.addWidget(self._title_label("结算周期范围"), 1, 2)
        info_layout.addWidget(self.range_label, 1, 3)
        info_layout.addWidget(self._title_label("周期周数"), 2, 0)
        info_layout.addWidget(self.week_count_label, 2, 1)
        info_layout.addWidget(self._title_label("当前周"), 2, 2)
        info_layout.addWidget(self.current_week_label, 2, 3)
        info_layout.addWidget(self._title_label("当前周范围"), 3, 0)
        info_layout.addWidget(self.current_week_range_label, 3, 1, 1, 3)
        info_layout.setColumnStretch(1, 1)
        info_layout.setColumnStretch(3, 1)

        self.week_switch_panel = QWidget()
        switch_layout = QHBoxLayout(self.week_switch_panel)
        switch_layout.setContentsMargins(0, 0, 0, 0)
        switch_layout.setSpacing(8)
        self.prev_week_btn = QPushButton("上一周")
        self.prev_week_btn.setProperty("buttonRole", "secondary")
        self.week_combo = QComboBox()
        self.next_week_btn = QPushButton("下一周")
        self.next_week_btn.setProperty("buttonRole", "secondary")
        self.week_range_hint = QLabel("-")
        self.week_range_hint.setObjectName("weekRangeHint")
        switch_layout.addWidget(self.prev_week_btn)
        switch_layout.addWidget(self.week_combo)
        switch_layout.addWidget(self.next_week_btn)
        switch_layout.addWidget(self.week_range_hint, 1)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["客户经理姓名", "本周上门目标", "本周优质目标", "本周回款目标"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.itemChanged.connect(self._on_item_changed)

        self.summary_group = QGroupBox("当前周汇总")
        summary_layout = QHBoxLayout(self.summary_group)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(8)
        self.visit_total_label = QLabel("0")
        self.quality_visit_total_label = QLabel("0")
        self.repayment_total_label = QLabel("0.00")
        summary_layout.addWidget(self._summary_card("本周上门目标合计", self.visit_total_label), 1)
        summary_layout.addWidget(self._summary_card("本周优质目标合计", self.quality_visit_total_label), 1)
        summary_layout.addWidget(self._summary_card("本周回款目标合计", self.repayment_total_label), 1)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        self.copy_prev_btn = QPushButton("复制上一周目标到当前周")
        self.copy_prev_btn.setProperty("buttonRole", "secondary")
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setProperty("buttonRole", "secondary")
        self.close_btn = QPushButton("关闭")
        self.close_btn.setProperty("buttonRole", "secondary")
        self.save_btn = QPushButton("保存")
        self.save_btn.setProperty("buttonRole", "primary")

        action_row.addWidget(self.copy_prev_btn)
        action_row.addStretch()
        action_row.addWidget(self.reset_btn)
        action_row.addWidget(self.close_btn)
        action_row.addWidget(self.save_btn)

        root.addWidget(self.info_group)
        root.addWidget(self.week_switch_panel)
        root.addWidget(self.table, 1)
        root.addWidget(self.summary_group)
        root.addLayout(action_row)

        self.prev_week_btn.clicked.connect(self.on_prev_week)
        self.next_week_btn.clicked.connect(self.on_next_week)
        self.week_combo.currentIndexChanged.connect(self.on_week_combo_changed)
        self.copy_prev_btn.clicked.connect(self.on_copy_previous_week)
        self.reset_btn.clicked.connect(self.on_reset)
        self.close_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.on_save)

        self.setStyleSheet(
            "\n".join(
                [
                    "QTableWidget { gridline-color: #E3E8EF; alternate-background-color: #FBFCFE; }",
                    "QHeaderView::section { background: #F1F5F9; color: #243447; font-weight: 700; padding: 6px; border: 1px solid #DCE3EA; }",
                    "QFrame#targetSummaryCard { background: #F8FAFC; border: 1px solid #E3E8EF; border-radius: 6px; }",
                    "QLabel#summaryTitle { color: #6C7A89; font-size: 12px; }",
                    "QLabel#summaryValue { color: #1F2937; font-size: 18px; font-weight: 700; }",
                    "QLabel#currentWeekValue { color: #A60D1A; font-weight: 700; }",
                    "QLabel#weekRangeHint { color: #4B5563; }",
                    "QPushButton[buttonRole='primary'] { background: #A60D1A; color: white; border: 1px solid #A60D1A; border-radius: 4px; padding: 6px 14px; font-weight: 700; }",
                    "QPushButton[buttonRole='secondary'] { background: #FFFFFF; color: #1F2937; border: 1px solid #CBD5E1; border-radius: 4px; padding: 6px 12px; }",
                    "QPushButton:disabled { color: #9CA3AF; background: #F3F4F6; border-color: #E5E7EB; }",
                ]
            )
        )

    @staticmethod
    def _title_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet("color: #6C7A89; font-weight: 700;")
        return label

    @staticmethod
    def _summary_card(title: str, value_label: QLabel) -> QWidget:
        card = QFrame()
        card.setObjectName("targetSummaryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("summaryTitle")
        value_label.setObjectName("summaryValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card

    def reload_data(self) -> None:
        self.weeks = self.weekly_target_service.get_cycle_weeks(self.settlement_cycle_code)
        self.current_week_index = self._default_week_index()
        self._populate_week_combo()
        self._load_current_week()

    def _default_week_index(self) -> int:
        if not self.weeks:
            return 1
        today = today_str()
        for week in self.weeks:
            if str(week.get("week_start_date", "")) <= today <= str(week.get("week_end_date", "")):
                return int(week.get("week_index", 1) or 1)
        return int(self.weeks[0].get("week_index", 1) or 1)

    def _populate_week_combo(self) -> None:
        self.week_combo.blockSignals(True)
        self.week_combo.clear()
        for week in self.weeks:
            week_index = int(week.get("week_index", 0) or 0)
            self.week_combo.addItem(f"第{week_index}周", week_index)
        self.week_combo.blockSignals(False)
        self._sync_week_combo()

    def _sync_week_combo(self) -> None:
        self.week_combo.blockSignals(True)
        for index in range(self.week_combo.count()):
            if int(self.week_combo.itemData(index) or 0) == self.current_week_index:
                self.week_combo.setCurrentIndex(index)
                break
        self.week_combo.blockSignals(False)

    def _current_week(self) -> dict[str, Any]:
        for week in self.weeks:
            if int(week.get("week_index", 0) or 0) == self.current_week_index:
                return week
        return {}

    def _load_current_week(self) -> None:
        if not self.weeks:
            self.table.setRowCount(0)
            self._refresh_info({})
            self._refresh_summary()
            return

        self._loading = True
        data = self.weekly_target_service.get_week_targets_for_team(
            team_id=self.team_id,
            settlement_cycle_code=self.settlement_cycle_code,
            week_index=self.current_week_index,
        )
        self.rows = list(data.get("rows", []))
        selected_week = data.get("selected_week") or self._current_week()
        self._refresh_info(data, selected_week)
        self._render_table()
        self._apply_table_columns()
        self._loading = False
        self._dirty = False
        self._refresh_summary()
        self._refresh_week_buttons()

    def _refresh_info(self, data: dict[str, Any], selected_week: dict[str, Any] | None = None) -> None:
        team = data.get("team") or {}
        selected_week = selected_week or {}
        self.team_label.setText(str(team.get("team_name", "") or "-"))
        self.manager_label.setText(str(team.get("team_manager_name", "") or "-"))
        self.cycle_label.setText(self.settlement_cycle_code or "-")
        if self.weeks:
            self.range_label.setText(
                f"{self.weeks[0].get('week_start_date', '')} ~ {self.weeks[-1].get('week_end_date', '')}"
            )
        else:
            self.range_label.setText("-")
        self.week_count_label.setText(str(len(self.weeks)))
        self.current_week_label.setText(f"第{self.current_week_index}周")
        week_range = f"{selected_week.get('week_start_date', '')} ~ {selected_week.get('week_end_date', '')}"
        self.current_week_range_label.setText(week_range)
        self.week_range_hint.setText(f"当前周范围：{week_range}")

    def _refresh_week_buttons(self) -> None:
        indexes = [int(week.get("week_index", 0) or 0) for week in self.weeks]
        self.prev_week_btn.setEnabled(bool(indexes) and self.current_week_index > min(indexes))
        self.next_week_btn.setEnabled(bool(indexes) and self.current_week_index < max(indexes))
        self.copy_prev_btn.setEnabled(bool(indexes) and self.current_week_index > min(indexes))

    def _render_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for row_idx, row in enumerate(self.rows):
            name_item = QTableWidgetItem(str(row.get("account_manager_name", "")))
            name_item.setData(Qt.UserRole, int(row.get("account_manager_id", 0) or 0))
            name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row_idx, self.COL_MANAGER, name_item)

            values = [
                (self.COL_VISIT, self._format_int(row.get("visit_target"))),
                (self.COL_QUALITY_VISIT, self._format_int(row.get("quality_visit_target"))),
                (self.COL_REPAYMENT, self._format_amount(row.get("repayment_target"))),
            ]
            for col, text in values:
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col, item)
        self.table.blockSignals(False)

    def _apply_table_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        widths = {
            self.COL_MANAGER: 150,
            self.COL_VISIT: 110,
            self.COL_QUALITY_VISIT: 120,
            self.COL_REPAYMENT: 120,
        }
        for col, width in widths.items():
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            header.resizeSection(col, width)
        self.table.verticalHeader().setDefaultSectionSize(30)

    @staticmethod
    def _format_int(value: Any) -> str:
        try:
            return str(int(value or 0))
        except (TypeError, ValueError):
            return "0"

    @staticmethod
    def _format_amount(value: Any) -> str:
        try:
            return f"{float(value or 0):.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def _cell_text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return (item.text() if item is not None else "").strip()

    def _on_item_changed(self, *_args) -> None:
        if not self._loading:
            self._dirty = True
        self._refresh_summary()

    def _refresh_summary(self, *_args) -> None:
        visit_total = 0
        quality_total = 0
        repayment_total = 0.0
        for row in range(self.table.rowCount()):
            ok, value, _ = validate_non_negative_int_input(self._cell_text(row, self.COL_VISIT))
            visit_total += value if ok else 0
            ok, value, _ = validate_non_negative_int_input(self._cell_text(row, self.COL_QUALITY_VISIT))
            quality_total += value if ok else 0
            ok, value, _ = validate_non_negative_decimal_input(self._cell_text(row, self.COL_REPAYMENT))
            repayment_total += value if ok else 0.0

        self.visit_total_label.setText(str(visit_total))
        self.quality_visit_total_label.setText(str(quality_total))
        self.repayment_total_label.setText(f"{repayment_total:.2f}")

    def _has_non_zero_values(self) -> bool:
        for row in range(self.table.rowCount()):
            ok, value, _ = validate_non_negative_int_input(self._cell_text(row, self.COL_VISIT))
            if ok and value != 0:
                return True
            ok, value, _ = validate_non_negative_int_input(self._cell_text(row, self.COL_QUALITY_VISIT))
            if ok and value != 0:
                return True
            ok, value, _ = validate_non_negative_decimal_input(self._cell_text(row, self.COL_REPAYMENT))
            if ok and value != 0:
                return True
        return False

    def _collect_rows(self) -> tuple[bool, str, list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        for row_idx in range(self.table.rowCount()):
            name_item = self.table.item(row_idx, self.COL_MANAGER)
            manager_id = int(name_item.data(Qt.UserRole) or 0) if name_item is not None else 0
            manager_name = name_item.text() if name_item is not None else ""

            ok, visit_target, err = validate_non_negative_int_input(self._cell_text(row_idx, self.COL_VISIT))
            if not ok:
                self.table.setCurrentCell(row_idx, self.COL_VISIT)
                return False, f"{manager_name} 本周上门目标无效：{err}", []

            ok, quality_visit_target, err = validate_non_negative_int_input(self._cell_text(row_idx, self.COL_QUALITY_VISIT))
            if not ok:
                self.table.setCurrentCell(row_idx, self.COL_QUALITY_VISIT)
                return False, f"{manager_name} 本周优质目标无效：{err}", []

            ok, repayment_target, err = validate_non_negative_decimal_input(self._cell_text(row_idx, self.COL_REPAYMENT))
            if not ok:
                self.table.setCurrentCell(row_idx, self.COL_REPAYMENT)
                return False, f"{manager_name} 本周回款目标无效：{err}", []

            rows.append(
                {
                    "account_manager_id": manager_id,
                    "visit_target": visit_target,
                    "quality_visit_target": quality_visit_target,
                    "repayment_target": repayment_target,
                }
            )
        return True, "ok", rows

    def _save_current_week(self, show_message: bool) -> bool:
        ok, message, rows = self._collect_rows()
        if not ok:
            QMessageBox.warning(self, "校验失败", message)
            return False

        try:
            result = self.weekly_target_service.save_week_targets_for_team(
                team_id=self.team_id,
                settlement_cycle_code=self.settlement_cycle_code,
                week_index=self.current_week_index,
                rows=rows,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))
            return False

        self.was_saved = True
        self._dirty = False
        self.targets_saved.emit()
        self._load_current_week()
        if show_message:
            QMessageBox.information(
                self,
                "保存成功",
                f"第{self.current_week_index}周目标已保存。\n\n保存记录数：{result.get('saved_count', 0)}",
            )
        return True

    def on_save(self) -> None:
        self._save_current_week(show_message=True)

    def _confirm_unsaved_switch(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("未保存修改")
        box.setIcon(QMessageBox.Question)
        box.setText("当前周目标已修改但尚未保存，是否保存后再切换？")
        save_btn = box.addButton("保存并切换", QMessageBox.AcceptRole)
        discard_btn = box.addButton("放弃修改并切换", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(save_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == save_btn:
            return "save"
        if clicked == discard_btn:
            return "discard"
        if clicked == cancel_btn:
            return "cancel"
        return "cancel"

    def _request_week_switch(self, target_week_index: int) -> bool:
        target_week_index = int(target_week_index or 0)
        if target_week_index == self.current_week_index:
            return True

        if self._dirty:
            action = self._confirm_unsaved_switch()
            if action == "save":
                if not self._save_current_week(show_message=False):
                    self._sync_week_combo()
                    return False
            elif action == "discard":
                pass
            else:
                self._sync_week_combo()
                return False

        self.current_week_index = target_week_index
        self._sync_week_combo()
        self._load_current_week()
        return True

    def on_prev_week(self) -> None:
        self._request_week_switch(self.current_week_index - 1)

    def on_next_week(self) -> None:
        self._request_week_switch(self.current_week_index + 1)

    def on_week_combo_changed(self, index: int) -> None:
        if self._loading or index < 0:
            return
        target_week_index = int(self.week_combo.itemData(index) or 0)
        if target_week_index <= 0:
            return
        self._request_week_switch(target_week_index)

    def on_copy_previous_week(self) -> None:
        if self.current_week_index <= 1:
            QMessageBox.information(self, "提示", "第1周没有上一周目标可复制")
            return

        if self._has_non_zero_values():
            answer = QMessageBox.question(
                self,
                "确认覆盖",
                "当前周已有非零目标，复制上一周会覆盖当前表格数据。\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        previous_data = self.weekly_target_service.get_week_targets_for_team(
            team_id=self.team_id,
            settlement_cycle_code=self.settlement_cycle_code,
            week_index=self.current_week_index - 1,
        )
        previous_map = {
            int(row.get("account_manager_id", 0) or 0): row
            for row in previous_data.get("rows", [])
        }

        self.table.blockSignals(True)
        for row_idx in range(self.table.rowCount()):
            name_item = self.table.item(row_idx, self.COL_MANAGER)
            manager_id = int(name_item.data(Qt.UserRole) or 0) if name_item is not None else 0
            source = previous_map.get(manager_id, {})
            self.table.item(row_idx, self.COL_VISIT).setText(self._format_int(source.get("visit_target")))
            self.table.item(row_idx, self.COL_QUALITY_VISIT).setText(self._format_int(source.get("quality_visit_target")))
            self.table.item(row_idx, self.COL_REPAYMENT).setText(self._format_amount(source.get("repayment_target")))
        self.table.blockSignals(False)
        self._dirty = True
        self._refresh_summary()

    def on_reset(self) -> None:
        if self._dirty:
            answer = QMessageBox.question(
                self,
                "确认重置",
                "将重新加载数据库中已保存的当前周目标，当前未保存修改会丢失。\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self._load_current_week()

    def _confirm_close(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "未保存修改",
            "当前周目标尚未保存，是否放弃修改？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def reject(self) -> None:
        if self._confirm_close():
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._confirm_close():
            event.accept()
        else:
            event.ignore()
