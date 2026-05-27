from __future__ import annotations

from app.ui.layout_profile import LayoutProfile
from app.utils.qt_compat import QDate, Qt, Signal
from app.utils.qt_compat import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import settlement_cycle_for_date
from app.utils.validators import validate_non_negative_decimal_input


class TeamSetupTab(QWidget):
    config_saved = Signal(int)
    team_archived = Signal()

    def __init__(
        self,
        team_service,
        admin_team_service=None,
        operator_getter=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.team_service = team_service
        self.admin_team_service = admin_team_service
        self.operator_getter = operator_getter or (lambda: "admin")
        self.current_team_id: int | None = None
        self.teams: list[dict] = []
        self._is_new_team_mode = False
        self._layout_profile: LayoutProfile | None = None
        self._build_ui()
        self.reload_teams()

    def _build_ui(self) -> None:
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)
        self.root_layout.setSpacing(6)

        self.main_splitter = QSplitter()
        self.main_splitter.setOrientation(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)

        self._build_nav_panel()
        self._build_detail_panel()

        self.main_splitter.addWidget(self.nav_panel)
        self.main_splitter.addWidget(self.detail_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([280, 1000])

        self.root_layout.addWidget(self.main_splitter, 1)

        self.reload_btn.clicked.connect(self.reload_teams)
        self.new_team_btn.clicked.connect(self.on_new_team)
        self.delete_team_btn.clicked.connect(self.on_delete_team)
        self.team_list.currentRowChanged.connect(self.on_team_changed)
        self.team_search_edit.textChanged.connect(self.on_team_search_changed)

        self.add_member_btn.clicked.connect(self.on_add_member)
        self.remove_member_btn.clicked.connect(self.on_remove_member)
        self.save_btn.clicked.connect(self.on_save)
        self.reset_btn.clicked.connect(self.on_reset)
        self.cycle_base_date.dateChanged.connect(self.refresh_cycle_related)
        self.member_table.itemChanged.connect(self.on_member_table_item_changed)
        self.member_table.itemSelectionChanged.connect(self._refresh_remove_member_button_state)

    def _build_nav_panel(self) -> None:
        self.nav_panel = QWidget()
        self.nav_panel.setObjectName("teamNavPanel")
        self.nav_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self.nav_layout = QVBoxLayout(self.nav_panel)
        self.nav_layout.setContentsMargins(8, 8, 8, 8)
        self.nav_layout.setSpacing(8)

        title = QLabel("团队列表")
        title.setObjectName("teamNavTitle")

        self.team_search_edit = QLineEdit()
        self.team_search_edit.setPlaceholderText("搜索团队/区域/经理")

        self.new_team_btn = QPushButton("新建团队")
        self.new_team_btn.setProperty("buttonRole", "primary")
        self.delete_team_btn = QPushButton("删除团队")
        self.delete_team_btn.setProperty("buttonRole", "danger")
        self.delete_team_btn.setEnabled(False)
        self.delete_team_btn.setToolTip("逻辑删除：归档停用团队并保留历史数据。")

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        action_row.addWidget(self.new_team_btn, 1)
        action_row.addWidget(self.delete_team_btn, 1)

        self.team_list = QListWidget()
        self.team_list.setObjectName("teamList")
        self.team_list.setAlternatingRowColors(True)

        self.empty_hint_label = QLabel("暂无团队，请点击\"新建团队\"")
        self.empty_hint_label.setWordWrap(True)
        self.empty_hint_label.setVisible(False)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)
        self.reload_btn = QPushButton("刷新")
        self.reload_btn.setProperty("buttonRole", "secondary")
        self.mode_label = QLabel("编辑模式")
        self.mode_label.setObjectName("statusText")
        bottom_row.addWidget(self.reload_btn)
        bottom_row.addStretch()
        bottom_row.addWidget(self.mode_label)

        self.nav_layout.addWidget(title)
        self.nav_layout.addWidget(self.team_search_edit)
        self.nav_layout.addLayout(action_row)
        self.nav_layout.addWidget(self.team_list, 1)
        self.nav_layout.addWidget(self.empty_hint_label)
        self.nav_layout.addLayout(bottom_row)

        self.nav_panel.setStyleSheet(
            "\n".join(
                [
                    "QWidget#teamNavPanel { background-color: #F8FAFC; border: 1px solid #E0E4E8; border-radius: 6px; }",
                    "QLabel#teamNavTitle { background: transparent; color: #2C3E50; font-size: 14px; font-weight: 700; }",
                    "QListWidget#teamList { border: 1px solid #E0E4E8; border-radius: 4px; background: #FFFFFF; }",
                    "QListWidget#teamList::item { padding: 10px 10px; border-bottom: 1px solid #F0F2F5; }",
                    "QListWidget#teamList::item:selected { background: #FFF1F2; color: #9A1622; border-left: 4px solid #9A1622; font-weight: 700; }",
                ]
            )
        )

    def _build_detail_panel(self) -> None:
        self.detail_panel = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(8, 8, 8, 8)
        self.detail_layout.setSpacing(8)

        self._build_basic_group()
        self._build_summary_group()
        self._build_member_group()

        self.detail_layout.addWidget(self.basic_group)
        self.detail_layout.addWidget(self.summary_group)
        self.detail_layout.addWidget(self.member_group, 1)

    def _build_basic_group(self) -> None:
        self.basic_group = QGroupBox("团队基础信息")
        self.basic_grid = QGridLayout(self.basic_group)
        self.basic_grid.setContentsMargins(10, 10, 10, 10)
        self.basic_grid.setHorizontalSpacing(12)
        self.basic_grid.setVerticalSpacing(8)

        self.region_edit = QLineEdit()
        self.team_name_edit = QLineEdit()
        self.team_manager_edit = QLineEdit()

        self.cycle_base_date = QDateEdit()
        self.cycle_base_date.setCalendarPopup(True)
        self.cycle_base_date.setDate(QDate.currentDate())

        region_label = self._build_form_label("区域")
        manager_label = self._build_form_label("团队经理姓名")
        team_label = self._build_form_label("团队名称")
        cycle_base_label = self._build_form_label("周期基准日期")

        self.basic_grid.addWidget(region_label, 0, 0)
        self.basic_grid.addWidget(self.region_edit, 0, 1)
        self.basic_grid.addWidget(team_label, 0, 2)
        self.basic_grid.addWidget(self.team_name_edit, 0, 3)

        self.basic_grid.addWidget(manager_label, 1, 0)
        self.basic_grid.addWidget(self.team_manager_edit, 1, 1)
        self.basic_grid.addWidget(cycle_base_label, 1, 2)
        self.basic_grid.addWidget(self.cycle_base_date, 1, 3)

        self.basic_grid.setColumnStretch(1, 1)
        self.basic_grid.setColumnStretch(3, 1)

    def _build_summary_group(self) -> None:
        self.summary_group = QGroupBox("自动摘要（系统计算）")
        summary_layout = QHBoxLayout(self.summary_group)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(8)

        self.cycle_code_label = QLabel("-")
        self.total_members_label = QLabel("0")
        self.team_target_label = QLabel("0.00")

        self.cycle_card = self._build_summary_card("结算周期", self.cycle_code_label)
        self.members_card = self._build_summary_card("总人数", self.total_members_label)
        self.target_card = self._build_summary_card("团队结算周期目标", self.team_target_label)

        summary_layout.addWidget(self.cycle_card, 1)
        summary_layout.addWidget(self.members_card, 1)
        summary_layout.addWidget(self.target_card, 1)

        self.summary_group.setStyleSheet(
            "\n".join(
                [
                    "QFrame#summaryCard { background: #F8FAFC; border: 1px solid #E3E8EF; border-radius: 6px; }",
                    "QLabel#summaryTitle { background: transparent; color: #6C7A89; font-size: 12px; }",
                    "QLabel#summaryValue { background: transparent; color: #1F2937; font-size: 18px; font-weight: 700; }",
                ]
            )
        )

    def _build_member_group(self) -> None:
        self.member_group = QGroupBox("客户经理名单与目标")
        self.member_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        member_layout = QVBoxLayout(self.member_group)
        member_layout.setContentsMargins(8, 8, 8, 8)
        member_layout.setSpacing(8)

        self.member_toolbar = QWidget()
        toolbar_layout = QHBoxLayout(self.member_toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        self.add_member_btn = QPushButton("新增客户经理")
        self.add_member_btn.setProperty("buttonRole", "secondary")
        self.remove_member_btn = QPushButton("删除客户经理")
        self.remove_member_btn.setProperty("buttonRole", "danger")
        self.batch_member_btn = QPushButton("批量粘贴（预留）")
        self.batch_member_btn.setProperty("buttonRole", "secondary")
        self.batch_member_btn.setEnabled(False)

        toolbar_layout.addWidget(self.add_member_btn)
        toolbar_layout.addWidget(self.remove_member_btn)
        toolbar_layout.addWidget(self.batch_member_btn)
        toolbar_layout.addStretch()

        self.member_table = QTableWidget(0, 2)
        self.member_table.setHorizontalHeaderLabels(["客户经理姓名", "结算周期目标"])
        self.member_table.setAlternatingRowColors(True)
        self.member_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.member_table.setSelectionMode(QTableWidget.SingleSelection)
        self.member_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_member_table_columns()

        self.detail_action_row = QWidget()
        action_layout = QHBoxLayout(self.detail_action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setProperty("buttonRole", "secondary")
        self.save_btn = QPushButton("保存")
        self.save_btn.setProperty("buttonRole", "primary")
        action_layout.addStretch()
        action_layout.addWidget(self.reset_btn)
        action_layout.addWidget(self.save_btn)

        member_layout.addWidget(self.member_toolbar)
        member_layout.addWidget(self.member_table, 1)
        member_layout.addWidget(self.detail_action_row)

    @staticmethod
    def _build_form_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setMinimumWidth(92)
        return label

    @staticmethod
    def _build_summary_card(title: str, value_label: QLabel) -> QWidget:
        card = QFrame()
        card.setObjectName("summaryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("summaryTitle")
        value_label.setObjectName("summaryValue")
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()
        return card

    def _apply_member_table_columns(self) -> None:
        header = self.member_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        current_w = header.sectionSize(1)
        if current_w <= 0:
            current_w = 170
        header.resizeSection(1, max(120, int(current_w)))

    def _cycle_code(self) -> str:
        cycle = settlement_cycle_for_date(self.cycle_base_date.date().toPython())
        return cycle.code

    def _set_mode(self, is_new: bool) -> None:
        self._is_new_team_mode = is_new
        self.mode_label.setText("新建模式" if is_new else "编辑模式")
        self._refresh_delete_button_state()

    def _clear_editor(self) -> None:
        self.region_edit.clear()
        self.team_name_edit.clear()
        self.team_manager_edit.clear()
        self.member_table.blockSignals(True)
        self.member_table.setRowCount(0)
        self.member_table.blockSignals(False)
        self.total_members_label.setText("0")
        self.team_target_label.setText("0.00")
        self.cycle_code_label.setText(self._cycle_code())
        self._apply_member_table_columns()
        self._refresh_remove_member_button_state()

    def _set_editor_enabled(self, enabled: bool) -> None:
        self.region_edit.setEnabled(enabled)
        self.team_name_edit.setEnabled(enabled)
        self.team_manager_edit.setEnabled(enabled)
        self.cycle_base_date.setEnabled(enabled)
        self.member_table.setEnabled(enabled)
        self.add_member_btn.setEnabled(enabled)
        self.save_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.batch_member_btn.setEnabled(False)
        self._refresh_delete_button_state()
        self._refresh_remove_member_button_state()

    def _refresh_delete_button_state(self) -> None:
        enabled = bool(
            self.admin_team_service is not None
            and self.current_team_id
            and not self._is_new_team_mode
            and self.team_list.isEnabled()
        )
        self.delete_team_btn.setEnabled(enabled)

    def _refresh_remove_member_button_state(self) -> None:
        enabled = self.member_table.isEnabled() and self.member_table.currentRow() >= 0
        self.remove_member_btn.setEnabled(enabled)

    def _selected_team_id_from_list(self) -> int:
        item = self.team_list.currentItem()
        if item is None:
            return 0
        try:
            return int(item.data(Qt.UserRole) or 0)
        except (TypeError, ValueError):
            return 0

    def _render_team_list(self, selected_team_id: int | None = None) -> bool:
        search_text = self.team_search_edit.text().strip().casefold()

        self.team_list.blockSignals(True)
        self.team_list.clear()

        selected_row = -1
        for team in self.teams:
            team_id = int(team.get("id") or 0)
            region = str(team.get("region", "")).strip()
            team_name = str(team.get("team_name", "")).strip()
            manager = str(team.get("team_manager_name", "")).strip()

            searchable = f"{region} {team_name} {manager}".casefold()
            if search_text and search_text not in searchable:
                continue

            item_text = team_name or f"团队 {team_id}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, team_id)
            item.setToolTip(f"区域：{region}\n团队：{team_name}\n团队经理：{manager}")
            self.team_list.addItem(item)

            if team_id == int(selected_team_id or 0):
                selected_row = self.team_list.count() - 1

        if self.team_list.count() > 0:
            self.team_list.setCurrentRow(selected_row if selected_row >= 0 else 0)

        self.team_list.blockSignals(False)
        return self.team_list.count() > 0

    def reload_teams(self, select_team_id: int | None = None) -> None:
        self.teams = self.team_service.list_teams()

        if not self.teams:
            self.current_team_id = None
            self._set_mode(False)
            self.mode_label.setText("暂无团队")
            self.empty_hint_label.setText("暂无团队，请点击\"新建团队\"")
            self.empty_hint_label.setVisible(True)
            self.team_list.clear()
            self.team_list.setEnabled(False)
            self.team_search_edit.setEnabled(False)
            self._clear_editor()
            self._set_editor_enabled(False)
            self._refresh_delete_button_state()
            return

        if select_team_id is not None and self.team_search_edit.text().strip():
            self.team_search_edit.blockSignals(True)
            self.team_search_edit.clear()
            self.team_search_edit.blockSignals(False)

        self.team_search_edit.setEnabled(True)
        self._set_editor_enabled(True)

        target_id = select_team_id
        if target_id is None:
            target_id = self.team_service.get_current_team_id()
        if int(target_id or 0) <= 0:
            target_id = int(self.teams[0]["id"])

        has_visible_team = self._render_team_list(selected_team_id=int(target_id))
        if not has_visible_team:
            self.team_list.setEnabled(False)
            self.empty_hint_label.setText("未找到匹配团队，请调整搜索关键词")
            self.empty_hint_label.setVisible(True)
            self.load_team(int(target_id))
            self._refresh_delete_button_state()
            return

        self.team_list.setEnabled(True)
        self.empty_hint_label.setVisible(False)

        selected_id = self._selected_team_id_from_list()
        if selected_id > 0:
            self.load_team(selected_id)
        self._refresh_delete_button_state()

    def _team_index(self) -> int:
        row = self.team_list.currentRow()
        return row if row >= 0 else 0

    def on_prev_team(self) -> None:
        count = self.team_list.count()
        if count <= 0:
            return
        idx = self._team_index()
        idx = (idx - 1) % count
        self.team_list.setCurrentRow(idx)

    def on_next_team(self) -> None:
        count = self.team_list.count()
        if count <= 0:
            return
        idx = self._team_index()
        idx = (idx + 1) % count
        self.team_list.setCurrentRow(idx)

    def on_team_search_changed(self, _text: str) -> None:
        if not self.teams:
            return

        has_visible_team = self._render_team_list(selected_team_id=self.current_team_id)
        if not has_visible_team:
            self.team_list.setEnabled(False)
            self.empty_hint_label.setText("未找到匹配团队，请调整搜索关键词")
            self.empty_hint_label.setVisible(True)
            self._refresh_delete_button_state()
            return

        self.team_list.setEnabled(True)
        self.empty_hint_label.setVisible(False)
        selected_id = self._selected_team_id_from_list()
        if selected_id > 0 and selected_id != int(self.current_team_id or 0):
            self.load_team(selected_id)

    def on_team_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self.team_list.item(row)
        if item is None:
            return
        team_id = int(item.data(Qt.UserRole) or 0)
        if team_id > 0:
            self.load_team(team_id)
        self._refresh_delete_button_state()

    def on_new_team(self) -> None:
        self.current_team_id = None
        self._set_mode(True)
        self.empty_hint_label.setVisible(False)
        self._clear_editor()
        self._set_editor_enabled(True)
        self.team_list.blockSignals(True)
        self.team_list.clearSelection()
        self.team_list.setCurrentRow(-1)
        self.team_list.blockSignals(False)
        self._refresh_delete_button_state()

    def on_reset(self) -> None:
        if self._is_new_team_mode or not self.current_team_id:
            self._clear_editor()
            return
        self.load_team(int(self.current_team_id))

    def load_team(self, team_id: int) -> None:
        team = self.team_service.get_team(team_id)
        if team is None:
            return

        self.current_team_id = int(team["id"])
        self._set_mode(False)
        self.empty_hint_label.setVisible(False)
        self._set_editor_enabled(True)
        self.team_service.set_current_team_id(self.current_team_id)

        self.region_edit.setText(str(team.get("region", "")))
        self.team_name_edit.setText(str(team.get("team_name", "")))
        self.team_manager_edit.setText(str(team.get("team_manager_name", "")))
        self.refresh_cycle_related()
        self._refresh_delete_button_state()

    def _operator(self) -> str:
        try:
            return str(self.operator_getter() or "admin")
        except Exception:  # noqa: BLE001
            return "admin"

    def on_delete_team(self) -> None:
        if self.admin_team_service is None:
            QMessageBox.warning(self, "提示", "当前未配置团队归档服务")
            return

        team_id = int(self.current_team_id or 0)
        if team_id <= 0:
            QMessageBox.warning(self, "提示", "请先选择团队")
            return

        team = self.team_service.get_team(team_id)
        if team is None:
            QMessageBox.warning(self, "提示", "当前团队不存在或已归档")
            self.current_team_id = None
            self.reload_teams()
            return

        team_name = str(team.get("team_name", "")).strip()
        confirm_text = (
            "删除团队将执行逻辑删除（归档停用），不会清除历史数据。\n\n"
            f"团队：{team.get('region', '')} / {team_name}\n"
            f"团队经理：{team.get('team_manager_name', '')}\n\n"
            "归档后：\n"
            "1. 该团队不再出现在可用团队列表中。\n"
            "2. 不能继续为该团队录入新日报。\n"
            "3. 历史数据和历史快照仍会保留并可查询。\n"
            "4. 团队下客户经理将一并停用。\n\n"
            "是否继续？"
        )
        answer = QMessageBox.question(
            self,
            "确认删除团队",
            confirm_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        typed, ok = QInputDialog.getText(
            self,
            "输入团队名称确认",
            f"请输入团队名称“{team_name}”以确认归档：",
        )
        if not ok:
            return
        if typed.strip() != team_name:
            QMessageBox.warning(self, "确认失败", "输入的团队名称不匹配，已取消删除。")
            return

        ok, message = self.admin_team_service.archive_team(
            team_id=team_id,
            operator=self._operator(),
            note="基础设置页删除团队（归档停用）",
        )
        if not ok:
            QMessageBox.warning(self, "删除失败", message)
            return

        QMessageBox.information(self, "删除成功", message)
        self.current_team_id = None
        self._set_mode(False)
        self.reload_teams()
        self.team_archived.emit()

    def _refresh_member_stats_from_table(self) -> None:
        total_target = 0.0
        member_count = 0
        for row in range(self.member_table.rowCount()):
            name_item = self.member_table.item(row, 0)
            target_item = self.member_table.item(row, 1)
            name = (name_item.text() if name_item else "").strip()
            if not name:
                continue
            member_count += 1
            ok, target, _ = validate_non_negative_decimal_input((target_item.text() if target_item else "0").strip())
            total_target += target if ok else 0.0

        self.total_members_label.setText(str(member_count))
        self.team_target_label.setText(f"{total_target:.2f}")

    def on_member_table_item_changed(self, _item: QTableWidgetItem) -> None:
        self._refresh_member_stats_from_table()

    def refresh_cycle_related(self, *_args) -> None:
        cycle_code = self._cycle_code()
        self.cycle_code_label.setText(cycle_code)

        if not self.current_team_id:
            self._refresh_member_stats_from_table()
            return

        rows = self.team_service.list_members_with_targets(self.current_team_id, cycle_code)
        self.member_table.blockSignals(True)
        self.member_table.setRowCount(len(rows))
        total_target = 0.0
        for i, row in enumerate(rows):
            self.member_table.setItem(i, 0, QTableWidgetItem(str(row.get("account_manager_name", ""))))
            target = float(row.get("target_amount", 0) or 0)
            total_target += target
            target_item = QTableWidgetItem(f"{target:.2f}")
            target_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.member_table.setItem(i, 1, target_item)
        self.member_table.blockSignals(False)

        self.total_members_label.setText(str(len(rows)))
        self.team_target_label.setText(f"{total_target:.2f}")
        self._apply_member_table_columns()
        self._refresh_remove_member_button_state()

    def on_add_member(self) -> None:
        row = self.member_table.rowCount()
        self.member_table.blockSignals(True)
        self.member_table.insertRow(row)
        self.member_table.setItem(row, 0, QTableWidgetItem(""))
        target_item = QTableWidgetItem("0")
        target_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.member_table.setItem(row, 1, target_item)
        self.member_table.blockSignals(False)
        self.member_table.setCurrentCell(row, 0)
        self._refresh_member_stats_from_table()
        self._apply_member_table_columns()
        self._refresh_remove_member_button_state()

    def on_remove_member(self) -> None:
        row = self.member_table.currentRow()
        if row >= 0:
            self.member_table.blockSignals(True)
            self.member_table.removeRow(row)
            self.member_table.blockSignals(False)
        self._refresh_member_stats_from_table()
        self._apply_member_table_columns()
        self._refresh_remove_member_button_state()

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
            key = name.casefold()
            if key in seen_names:
                raise ValueError(f"第{row + 1}行客户经理姓名重复：{name}")
            seen_names.add(key)

            ok, value, err = validate_non_negative_decimal_input(target)
            if not ok:
                raise ValueError(f"第{row + 1}行目标值无效：{err}")
            members.append({"account_manager_name": name, "target_amount": value})
        return members

    def on_save(self) -> None:
        try:
            members = self._collect_members()
        except ValueError as exc:
            QMessageBox.warning(self, "校验失败", str(exc))
            return

        if not members:
            QMessageBox.warning(self, "提示", "请至少保留一位客户经理")
            return

        ok, message, team_id = self.team_service.save_team_config(
            team_id=self.current_team_id,
            region=self.region_edit.text().strip(),
            team_name=self.team_name_edit.text().strip(),
            team_manager_name=self.team_manager_edit.text().strip(),
            settlement_cycle_code=self._cycle_code(),
            members=members,
        )
        if not ok:
            QMessageBox.warning(self, "保存失败", message)
            return

        self.current_team_id = team_id
        QMessageBox.information(self, "提示", message)
        self.reload_teams(select_team_id=team_id)
        if team_id:
            self.config_saved.emit(team_id)

    def _scale(self, value: int, floor: int) -> int:
        factor = float(self.window().property("_view_scale_factor") or 1.0) if self.window() is not None else 1.0
        return max(floor, int(round(float(value) * factor)))

    def apply_layout_profile(self, profile: LayoutProfile) -> None:
        self._layout_profile = profile
        metrics = profile.metrics

        page_margin = self._scale(metrics.page_margin, 4)
        section_margin = self._scale(metrics.section_margin, 4)
        page_spacing = self._scale(metrics.page_spacing, 3)
        section_spacing = self._scale(metrics.section_spacing, 3)

        self.root_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.root_layout.setSpacing(page_spacing)

        self.nav_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.nav_layout.setSpacing(page_spacing)

        self.detail_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.detail_layout.setSpacing(page_spacing)

        self.basic_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.basic_grid.setHorizontalSpacing(section_spacing + 4)
        self.basic_grid.setVerticalSpacing(section_spacing)

        control_h = self._scale(metrics.control_height, 22)
        for widget in [self.team_search_edit, self.region_edit, self.team_name_edit, self.team_manager_edit, self.cycle_base_date]:
            widget.setMinimumHeight(control_h)

        btn_h = self._scale(metrics.button_height, 26)
        for btn in [
            self.new_team_btn,
            self.delete_team_btn,
            self.reload_btn,
            self.add_member_btn,
            self.remove_member_btn,
            self.batch_member_btn,
            self.save_btn,
            self.reset_btn,
        ]:
            btn.setMinimumHeight(btn_h)

        row_height = self._scale(metrics.table_row_height, 22)
        header_height = self._scale(metrics.table_header_height, 24)
        self.member_table.verticalHeader().setDefaultSectionSize(row_height)
        self.member_table.horizontalHeader().setMinimumHeight(header_height)
        self.member_table.horizontalHeader().resizeSection(1, self._scale(170, 120))

        card_h = self._scale(72, 56)
        for card in [self.cycle_card, self.members_card, self.target_card]:
            card.setMinimumHeight(card_h)

        nav_width = self._scale(280, 220)
        self.nav_panel.setMinimumWidth(nav_width)
        self.nav_panel.setMaximumWidth(nav_width)

        self.main_splitter.setSizes([nav_width, self._scale(1000, 640)])

    def apply_view_scale(self, factor: float) -> None:
        if self._layout_profile is not None:
            self.apply_layout_profile(self._layout_profile)
            return

        row_height = max(22, int(round(30 * factor)))
        header_height = max(24, int(round(34 * factor)))
        self.member_table.verticalHeader().setDefaultSectionSize(row_height)
        self.member_table.horizontalHeader().setMinimumHeight(header_height)
        self.member_table.horizontalHeader().resizeSection(1, max(120, int(round(170 * factor))))
        nav_width = max(220, int(round(280 * factor)))
        self.nav_panel.setMinimumWidth(nav_width)
        self.nav_panel.setMaximumWidth(nav_width)
