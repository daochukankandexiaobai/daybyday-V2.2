from __future__ import annotations

from app.config.field_profiles import PROFILE_QUERY_SUMMARY_TABLE, get_profile_field_keys
from app.config.field_registry import DATA_TYPE_AMOUNT, DATA_TYPE_INT, DATA_TYPE_PERCENT, get_field_spec
from app.ui.layout_profile import LayoutProfile
from app.utils.format_utils import format_int, format_money, format_percent
from app.utils.qt_compat import QDate, Qt
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class QueryTab(QWidget):
    MODE_DAY = "某日"
    MODE_WEEK = "周报"
    MODE_MONTH = "月报"
    MODE_CUSTOM = "自定义"

    FIELD_KEYS = list(get_profile_field_keys(PROFILE_QUERY_SUMMARY_TABLE))
    TABLE_HEADERS = [get_field_spec(key).label for key in FIELD_KEYS]

    def __init__(
        self,
        record_service,
        team_service,
        analytics_service=None,  # 兼容旧注入，当前页不再承载分析模块
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record_service = record_service
        self.team_service = team_service
        self.week_options: list[dict[str, str]] = []
        self._updating_team_list = False
        self._layout_profile: LayoutProfile | None = None

        self._build_ui()
        self.reload_teams()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.page = QWidget()
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setContentsMargins(6, 6, 6, 6)
        self.page_layout.setSpacing(6)

        self.filter_group = QGroupBox("查询条件")
        self.filter_grid = QGridLayout(self.filter_group)
        self.filter_grid.setContentsMargins(8, 8, 8, 8)
        self.filter_grid.setHorizontalSpacing(8)
        self.filter_grid.setVerticalSpacing(5)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([self.MODE_DAY, self.MODE_WEEK, self.MODE_MONTH, self.MODE_CUSTOM])

        self.team_list = QListWidget()
        self.team_list.setAlternatingRowColors(True)
        self.team_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.base_date = QDateEdit()
        self.base_date.setCalendarPopup(True)
        self.base_date.setDate(QDate.currentDate())

        self.custom_start = QDateEdit()
        self.custom_start.setCalendarPopup(True)
        self.custom_start.setDate(QDate.currentDate())

        self.custom_end = QDateEdit()
        self.custom_end.setCalendarPopup(True)
        self.custom_end.setDate(QDate.currentDate())

        self.week_prev_btn = QPushButton("上一周")
        self.week_prev_btn.setProperty("buttonRole", "secondary")
        self.week_next_btn = QPushButton("下一周")
        self.week_next_btn.setProperty("buttonRole", "secondary")
        self.week_combo = QComboBox()

        self.query_btn = QPushButton("查询")
        self.query_btn.setProperty("buttonRole", "primary")
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setProperty("buttonRole", "secondary")

        self.mode_label = QLabel("模式")
        self.team_label = QLabel("团队（多选）")
        self.base_date_label = QLabel("基准日期")
        self.custom_start_label = QLabel("开始日期")
        self.custom_end_label = QLabel("结束日期")

        self.filter_grid.addWidget(self.mode_label, 0, 0)
        self.filter_grid.addWidget(self.mode_combo, 0, 1)
        self.filter_grid.addWidget(self.base_date_label, 0, 2)
        self.filter_grid.addWidget(self.base_date, 0, 3)
        self.filter_grid.addWidget(self.custom_start_label, 1, 0)
        self.filter_grid.addWidget(self.custom_start, 1, 1)
        self.filter_grid.addWidget(self.custom_end_label, 1, 2)
        self.filter_grid.addWidget(self.custom_end, 1, 3)
        self.filter_grid.addWidget(self.week_prev_btn, 2, 0)
        self.filter_grid.addWidget(self.week_combo, 2, 1)
        self.filter_grid.addWidget(self.week_next_btn, 2, 2)

        self.filter_grid.addWidget(self.team_label, 0, 4)
        self.filter_grid.addWidget(self.team_list, 0, 5, 3, 1)
        self.filter_grid.setColumnStretch(5, 1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.query_btn)
        btns.addWidget(self.reset_btn)
        btns.addStretch()
        self.filter_grid.addLayout(btns, 0, 6, 1, 1)

        self.range_info = QLabel("")
        self.range_info.setObjectName("hintText")
        self.range_info.setWordWrap(True)
        self.rule_info = QLabel("")
        self.rule_info.setObjectName("hintText")
        self.rule_info.setWordWrap(True)

        self.top_panel = QWidget()
        self.top_panel_layout = QVBoxLayout(self.top_panel)
        self.top_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.top_panel_layout.setSpacing(4)
        self.top_panel_layout.addWidget(self.filter_group)
        self.top_panel_layout.addWidget(self.range_info)
        self.top_panel_layout.addWidget(self.rule_info)

        self.table = QTableWidget(0, len(self.TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.summary_group = QGroupBox("汇总统计")
        self.summary_grid = QGridLayout(self.summary_group)
        self.summary_grid.setContentsMargins(8, 8, 8, 8)
        self.summary_grid.setHorizontalSpacing(8)
        self.summary_grid.setVerticalSpacing(6)

        self.summary_labels: dict[str, QLabel] = {}
        self._summary_metric_defs = [
            ("repayment_amount_cumulative", "累计回款金额"),
            ("loan_amount_cumulative", "累计放款金额"),
            ("invitation_cumulative", "累计邀约"),
            ("signing_count_cumulative", "累计签约量"),
            ("quality_visit_count_cumulative", "累计优质上门量"),
            ("signing_rate", "签约率"),
            ("quality_visit_rate", "优质上门率"),
            ("approval_rate", "批复率"),
            ("repayment_conversion_rate", "回款转化率"),
            ("target_progress", "目标完成进度"),
        ]
        for idx, (key, text) in enumerate(self._summary_metric_defs):
            card = QWidget()
            card.setObjectName("kpiCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 5, 8, 5)
            card_layout.setSpacing(2)
            title = QLabel(text)
            title.setObjectName("kpiTitle")
            value = QLabel("-")
            value.setObjectName("kpiValue")
            self.summary_labels[key] = value
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            row = idx // 5
            col = idx % 5
            self.summary_grid.addWidget(card, row, col)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.top_panel)
        self.main_splitter.addWidget(self.table)
        self.main_splitter.addWidget(self.summary_group)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([220, 560, 150])

        self.page_layout.addWidget(self.main_splitter, 1)
        self.page_scroll.setWidget(self.page)
        root.addWidget(self.page_scroll, 1)

        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.base_date.dateChanged.connect(self.on_base_date_changed)
        self.team_list.itemChanged.connect(self.on_team_checked_changed)
        self.week_combo.currentIndexChanged.connect(self.on_week_selected)
        self.week_prev_btn.clicked.connect(self.on_prev_week)
        self.week_next_btn.clicked.connect(self.on_next_week)
        self.query_btn.clicked.connect(self.on_query)
        self.reset_btn.clicked.connect(self.on_reset)

    def _checked_team_ids(self) -> list[int]:
        ids: list[int] = []
        for i in range(self.team_list.count()):
            item = self.team_list.item(i)
            if item is None:
                continue
            if item.checkState() == Qt.Checked:
                ids.append(int(item.data(Qt.UserRole) or 0))
        return [team_id for team_id in ids if team_id > 0]

    def _set_all_team_checked(self, checked: bool) -> None:
        self._updating_team_list = True
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.team_list.count()):
            item = self.team_list.item(i)
            if item is not None:
                item.setCheckState(state)
        self._updating_team_list = False

    def reload_teams(self) -> None:
        teams = self.team_service.list_teams()
        self._updating_team_list = True
        self.team_list.clear()
        for team in teams:
            label = f"{team['region']} - {team['team_name']}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, int(team["id"]))
            item.setData(Qt.UserRole + 1, str(team.get("team_name", "")))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.team_list.addItem(item)
        self._updating_team_list = False

        self.on_mode_changed(self.mode_combo.currentText())
        self.on_query()

    def _set_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(visible)

    def _apply_mode_visibility(self, mode: str) -> None:
        is_custom = mode == self.MODE_CUSTOM
        is_week = mode == self.MODE_WEEK

        self.base_date_label.setText("锚点日期" if mode in {self.MODE_WEEK, self.MODE_MONTH} else "基准日期")
        self._set_visible(self.base_date_label, not is_custom)
        self._set_visible(self.base_date, not is_custom)

        self._set_visible(self.custom_start_label, is_custom)
        self._set_visible(self.custom_start, is_custom)
        self._set_visible(self.custom_end_label, is_custom)
        self._set_visible(self.custom_end, is_custom)

        self._set_visible(self.week_prev_btn, is_week)
        self._set_visible(self.week_combo, is_week)
        self._set_visible(self.week_next_btn, is_week)

    def on_mode_changed(self, mode: str) -> None:
        self._apply_mode_visibility(mode)
        if mode == self.MODE_WEEK:
            self.refresh_week_options()
        self.on_query()

    def on_base_date_changed(self, *_args) -> None:
        if self.mode_combo.currentText() == self.MODE_WEEK:
            self.refresh_week_options()
        self.on_query()

    def on_team_checked_changed(self, _item: QListWidgetItem) -> None:
        if self._updating_team_list:
            return
        self.on_query()

    def refresh_week_options(self) -> None:
        self.week_options = self.record_service.list_week_options(self.base_date.date().toString("yyyy-MM-dd"))
        self.week_combo.blockSignals(True)
        self.week_combo.clear()
        for opt in self.week_options:
            self.week_combo.addItem(opt["label"], opt)
        self.week_combo.blockSignals(False)

    def on_prev_week(self) -> None:
        idx = self.week_combo.currentIndex()
        if idx > 0:
            self.week_combo.setCurrentIndex(idx - 1)

    def on_next_week(self) -> None:
        idx = self.week_combo.currentIndex()
        if idx < self.week_combo.count() - 1:
            self.week_combo.setCurrentIndex(idx + 1)

    def on_week_selected(self, *_args) -> None:
        if self.mode_combo.currentText() != self.MODE_WEEK:
            return
        data = self.week_combo.currentData()
        if isinstance(data, dict) and data.get("start"):
            self.base_date.setDate(QDate.fromString(data["start"], "yyyy-MM-dd"))
        self.on_query()

    def _apply_summary(self, summary: dict, cross_cycle: bool) -> None:
        self.summary_labels["repayment_amount_cumulative"].setText(format_money(summary.get("repayment_amount_cumulative")))
        self.summary_labels["loan_amount_cumulative"].setText(format_money(summary.get("loan_amount_cumulative")))
        self.summary_labels["invitation_cumulative"].setText(format_int(summary.get("invitation_cumulative")))
        self.summary_labels["signing_count_cumulative"].setText(format_int(summary.get("signing_count_cumulative")))
        self.summary_labels["quality_visit_count_cumulative"].setText(format_int(summary.get("quality_visit_count_cumulative")))

        for key in ["signing_rate", "quality_visit_rate", "approval_rate", "repayment_conversion_rate", "target_progress"]:
            value = summary.get(key)
            if key == "target_progress" and cross_cycle:
                self.summary_labels[key].setText("")
                continue
            self.summary_labels[key].setText(format_percent(value))

    @staticmethod
    def _format_field_value(field_key: str, row: dict) -> str:
        value = row.get(field_key)
        if field_key == "cycle_target" and value is None:
            return ""
        spec = get_field_spec(field_key)
        if spec.data_type == DATA_TYPE_AMOUNT:
            return format_money(value)
        if spec.data_type == DATA_TYPE_INT:
            return format_int(value)
        if spec.data_type == DATA_TYPE_PERCENT:
            return format_percent(value)
        return str(value or "")

    def _build_table_values(self, row: dict) -> list[str]:
        return [self._format_field_value(field_key, row) for field_key in self.FIELD_KEYS]

    def on_query(self, *_args) -> None:
        selected_team_ids = self._checked_team_ids()
        if len(selected_team_ids) == 1:
            self.team_service.set_current_team_id(selected_team_ids[0])

        mode = self.mode_combo.currentText()
        custom_start = ""
        custom_end = ""
        if mode == self.MODE_CUSTOM:
            custom_start = self.custom_start.date().toString("yyyy-MM-dd")
            custom_end = self.custom_end.date().toString("yyyy-MM-dd")
            if custom_start > custom_end:
                QMessageBox.warning(self, "提示", "开始日期不能晚于结束日期")
                return

        try:
            result = self.record_service.get_query_summary_grouped_by_account_manager(
                mode=mode,
                base_date=self.base_date.date().toString("yyyy-MM-dd"),
                team_id=None,
                team_ids=selected_team_ids,
                custom_start=custom_start,
                custom_end=custom_end,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "查询失败", str(exc))
            return

        rows = result.get("rows", [])
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = self._build_table_values(row)
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                field_key = self.FIELD_KEYS[col_idx]
                if field_key in {"query_range", "account_manager_name"}:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeColumnsToContents()

        cross_cycle = bool(result.get("cross_cycle"))
        self.range_info.setText(f"查询范围：{result.get('start_date', '')} ~ {result.get('end_date', '')}")
        if not selected_team_ids:
            self.rule_info.setText("当前未勾选团队，结果为空")
        else:
            self.rule_info.setText("跨结算周期区间：目标完成进度已置空" if cross_cycle else "")
        self._apply_summary(result.get("summary", {}), cross_cycle)

    def on_reset(self) -> None:
        self.mode_combo.setCurrentText(self.MODE_DAY)
        self.base_date.setDate(QDate.currentDate())
        self.custom_start.setDate(QDate.currentDate())
        self.custom_end.setDate(QDate.currentDate())
        self._set_all_team_checked(True)
        self.table.setRowCount(0)
        self.range_info.setText("")
        self.rule_info.setText("")
        for label in self.summary_labels.values():
            label.setText("-")
        self.on_query()

    def apply_import_context(self, context: dict) -> None:
        team_names = {str(name).strip() for name in (context.get("team_names", []) or []) if str(name).strip()}

        self._updating_team_list = True
        matched = False
        if team_names:
            for i in range(self.team_list.count()):
                item = self.team_list.item(i)
                if item is None:
                    continue
                item_team_name = str(item.data(Qt.UserRole + 1) or "").strip()
                is_checked = item_team_name in team_names
                if is_checked:
                    matched = True
                item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)
            if not matched:
                for i in range(self.team_list.count()):
                    item = self.team_list.item(i)
                    if item is not None:
                        item.setCheckState(Qt.Checked)
        else:
            for i in range(self.team_list.count()):
                item = self.team_list.item(i)
                if item is not None:
                    item.setCheckState(Qt.Checked)
        self._updating_team_list = False

        start_date = str(context.get("start_date", "")).strip()
        end_date = str(context.get("end_date", "")).strip()
        if start_date and end_date:
            if start_date == end_date:
                self.mode_combo.setCurrentText(self.MODE_DAY)
                self.base_date.setDate(QDate.fromString(start_date, "yyyy-MM-dd"))
            else:
                self.mode_combo.setCurrentText(self.MODE_CUSTOM)
                self.custom_start.setDate(QDate.fromString(start_date, "yyyy-MM-dd"))
                self.custom_end.setDate(QDate.fromString(end_date, "yyyy-MM-dd"))

        self.on_query()

    def _scale(self, value: int, floor: int) -> int:
        factor = float(self.window().property("_view_scale_factor") or 1.0) if self.window() is not None else 1.0
        return max(floor, int(round(float(value) * factor)))

    def apply_layout_profile(self, profile: LayoutProfile) -> None:
        self._layout_profile = profile
        metrics = profile.metrics

        page_margin = self._scale(metrics.page_margin, 4)
        section_margin = self._scale(metrics.section_margin, 4)
        page_spacing = self._scale(metrics.page_spacing, 4)
        section_spacing = self._scale(metrics.section_spacing, 3)

        self.page_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.page_layout.setSpacing(page_spacing)
        self.top_panel_layout.setSpacing(max(2, page_spacing - 1))

        self.filter_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.filter_grid.setHorizontalSpacing(section_spacing)
        self.filter_grid.setVerticalSpacing(max(2, section_spacing - 1))
        self.summary_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.summary_grid.setHorizontalSpacing(section_spacing)
        self.summary_grid.setVerticalSpacing(max(3, section_spacing))
        for idx in range(self.summary_grid.count()):
            item = self.summary_grid.itemAt(idx)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setMinimumHeight(self._scale(metrics.kpi_card_height, 44))

        control_h = self._scale(metrics.control_height, 22)
        for widget in [self.mode_combo, self.base_date, self.custom_start, self.custom_end, self.week_combo]:
            widget.setMinimumHeight(control_h)

        btn_h = self._scale(metrics.button_height, 26)
        for btn in [self.week_prev_btn, self.week_next_btn, self.query_btn, self.reset_btn]:
            btn.setMinimumHeight(btn_h)

        self.team_list.setMaximumHeight(self._scale(metrics.team_list_max_height, 68))

        filter_height = self._scale(metrics.query_filter_height, 145)
        summary_height = self._scale(metrics.query_summary_height, 110)
        self.filter_group.setMaximumHeight(filter_height)
        self.summary_group.setMaximumHeight(summary_height)
        self.main_splitter.setSizes([filter_height + 36, self._scale(620, 420), summary_height])

        self.table.verticalHeader().setDefaultSectionSize(self._scale(metrics.table_row_height, 22))
        self.table.horizontalHeader().setMinimumHeight(self._scale(metrics.table_header_height, 24))

    def apply_view_scale(self, factor: float) -> None:
        if self._layout_profile is not None:
            self.apply_layout_profile(self._layout_profile)
            return
        self.team_list.setMaximumHeight(max(72, int(round(105 * factor))))
        row_height = max(22, int(round(30 * factor)))
        header_height = max(24, int(round(34 * factor)))
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.table.horizontalHeader().setMinimumHeight(header_height)
