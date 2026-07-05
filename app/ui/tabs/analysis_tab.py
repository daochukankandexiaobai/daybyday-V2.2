from __future__ import annotations

from app.fields.analysis_config_service import ANALYSIS_TYPE_RANKING, ANALYSIS_TYPE_TREND
from app.services.analytics_service import AnalyticsService
from app.ui.layout_profile import LayoutProfile
from app.ui.widgets.chart_widget import ChartWidget
from app.utils.format_utils import format_int, format_money, format_percent
from app.utils.qt_compat import QDate, Qt
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QFormLayout,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class AnalysisTab(QWidget):
    MODE_DAY = "某日"
    MODE_WEEK = "周报"
    MODE_MONTH = "月报"
    MODE_CUSTOM = "自定义"
    TREND_CHART_KEY = "trend"

    def __init__(
        self,
        record_service,
        team_service,
        analytics_service: AnalyticsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record_service = record_service
        self.team_service = team_service
        self.analytics_service = analytics_service or AnalyticsService(record_service)

        self.week_options: list[dict[str, str]] = []
        self._updating_team_list = False
        self._current_query_rows: list[dict] = []
        self._current_trend_points: list[dict] = []
        self._kpi_value_labels: dict[str, QLabel] = {}
        self._funnel_rate_labels: dict[str, QLabel] = {}
        self._kpi_cards: list[QWidget] = []
        self._charts_available = True
        self._layout_profile: LayoutProfile | None = None

        self._filter_collapsed = False
        self._kpi_collapsed = False
        self._filter_max_height = 220
        self._kpi_max_height = 180
        self._kpi_columns = 5

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
        self.page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setContentsMargins(6, 6, 6, 6)
        self.page_layout.setSpacing(6)

        self.top_action_row = QWidget()
        top_actions = QHBoxLayout(self.top_action_row)
        top_actions.setContentsMargins(0, 0, 0, 0)
        top_actions.setSpacing(6)
        self.toggle_filter_btn = QPushButton("隐藏筛选条件")
        self.toggle_filter_btn.setProperty("buttonRole", "ghost")
        self.toggle_filter_btn.setCheckable(True)
        self.toggle_kpi_btn = QPushButton("隐藏概览")
        self.toggle_kpi_btn.setProperty("buttonRole", "ghost")
        self.toggle_kpi_btn.setCheckable(True)
        self.compact_scope_label = QLabel("")
        self.compact_scope_label.setObjectName("hintText")
        self.compact_scope_label.setVisible(False)
        self.compact_scope_label.setWordWrap(True)
        self.compact_scope_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top_actions.addWidget(self.toggle_filter_btn)
        top_actions.addWidget(self.toggle_kpi_btn)
        top_actions.addWidget(self.compact_scope_label, 1)

        self.filter_group = QGroupBox("分析条件")
        self.filter_grid = QGridLayout(self.filter_group)
        self.filter_grid.setContentsMargins(8, 8, 8, 8)
        self.filter_grid.setHorizontalSpacing(8)
        self.filter_grid.setVerticalSpacing(6)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems([self.MODE_DAY, self.MODE_WEEK, self.MODE_MONTH, self.MODE_CUSTOM])

        self.team_list = QListWidget()
        self.team_list.setAlternatingRowColors(True)
        self.team_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.team_list.setMaximumHeight(108)

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
        self.filter_grid.addWidget(self.team_label, 0, 4)
        self.filter_grid.addWidget(self.team_list, 0, 5, 3, 1)

        self.filter_grid.addWidget(self.custom_start_label, 1, 0)
        self.filter_grid.addWidget(self.custom_start, 1, 1)
        self.filter_grid.addWidget(self.custom_end_label, 1, 2)
        self.filter_grid.addWidget(self.custom_end, 1, 3)

        self.filter_grid.addWidget(self.week_prev_btn, 2, 0)
        self.filter_grid.addWidget(self.week_combo, 2, 1)
        self.filter_grid.addWidget(self.week_next_btn, 2, 2)
        self.filter_grid.addWidget(self.query_btn, 2, 3)
        self.filter_grid.addWidget(self.reset_btn, 2, 4)

        self.info_panel = QWidget()
        info_layout = QVBoxLayout(self.info_panel)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        self.range_info = QLabel("")
        self.range_info.setObjectName("hintText")
        self.range_info.setWordWrap(True)
        self.rule_info = QLabel("")
        self.rule_info.setObjectName("hintText")
        self.rule_info.setWordWrap(True)
        info_layout.addWidget(self.range_info)
        info_layout.addWidget(self.rule_info)

        self.kpi_group = QGroupBox("概览")
        self.kpi_grid = QGridLayout(self.kpi_group)
        self.kpi_grid.setContentsMargins(8, 8, 8, 8)
        self.kpi_grid.setHorizontalSpacing(6)
        self.kpi_grid.setVerticalSpacing(6)
        self._build_kpi_cards()
        self._reflow_kpi_cards(columns=self._kpi_columns)

        self.chart_tabs = QTabWidget()
        self.chart_tabs.setObjectName("chartTabs")
        self.chart_tabs.setDocumentMode(True)
        self.chart_tabs.setUsesScrollButtons(True)
        self._build_chart_tabs()

        self.page_layout.addWidget(self.top_action_row)
        self.page_layout.addWidget(self.filter_group)
        self.page_layout.addWidget(self.info_panel)
        self.page_layout.addWidget(self.kpi_group)
        self.page_layout.addWidget(self.chart_tabs, 1)

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
        self.toggle_filter_btn.clicked.connect(self.on_toggle_filter_panel)
        self.toggle_kpi_btn.clicked.connect(self.on_toggle_kpi_panel)
        self.trend_metric_combo.currentIndexChanged.connect(self._render_trend_chart)
        self.ranking_metric_combo.currentIndexChanged.connect(self._render_ranking_chart)
        self.ranking_top_n_combo.currentIndexChanged.connect(self._render_ranking_chart)

    def _build_kpi_cards(self) -> None:
        self._kpi_defs = [
            ("repayment_amount_total", "回款金额总计"),
            ("loan_amount_total", "放款金额总计"),
            ("visit_total", "上门量总计"),
            ("signing_total", "签约量总计"),
            ("repayment_customer_total", "回款客户数总计"),
            ("signing_rate", "签约率"),
            ("quality_visit_rate", "优质上门率"),
            ("sales_conversion_rate", "销售转化率"),
            ("warrant_conversion_rate", "权证转化率"),
            ("target_progress", "目标完成进度"),
        ]
        for key, title in self._kpi_defs:
            card = QWidget()
            card.setObjectName("analysisKpiCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 5, 8, 5)
            card_layout.setSpacing(2)

            title_label = QLabel(title)
            title_label.setObjectName("kpiTitle")
            title_label.setWordWrap(True)
            value_label = QLabel("-")
            value_label.setObjectName("kpiValue")
            value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            self._kpi_value_labels[key] = value_label
            self._kpi_cards.append(card)

    def _reflow_kpi_cards(self, columns: int) -> None:
        cols = max(1, int(columns))
        while self.kpi_grid.count() > 0:
            item = self.kpi_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.kpi_group)

        for idx, card in enumerate(self._kpi_cards):
            row = idx // cols
            col = idx % cols
            self.kpi_grid.addWidget(card, row, col)
        for col in range(cols):
            self.kpi_grid.setColumnStretch(col, 1)

    def _build_chart_tabs(self) -> None:
        self._build_trend_tab()
        self._build_ranking_tab()
        self._build_funnel_tab()
        self._charts_available = (
            bool(getattr(self.trend_chart, "is_available", True))
            and bool(getattr(self.ranking_chart, "is_available", True))
            and bool(getattr(self.funnel_chart, "is_available", True))
        )

    def _build_trend_tab(self) -> None:
        trend_tab = QWidget()
        layout = QVBoxLayout(trend_tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        bar.addWidget(QLabel("趋势指标"))
        self.trend_metric_combo = QComboBox()
        for text, key in self._trend_metric_options():
            self.trend_metric_combo.addItem(text, key)
        bar.addWidget(self.trend_metric_combo)
        bar.addStretch()

        self.trend_chart = ChartWidget()
        layout.addLayout(bar)
        layout.addWidget(self.trend_chart, 1)
        self.chart_tabs.addTab(trend_tab, "趋势")

    def _trend_metric_options(self) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        for label, field_key in self.analytics_service.get_analysis_metric_options(ANALYSIS_TYPE_TREND):
            label = self._normalize_analysis_metric_label(label)
            options.append((f"{label}趋势", field_key))

        if not options:
            options.append(("回款金额趋势", "repayment_amount_daily"))
        return options

    @staticmethod
    def _normalize_analysis_metric_label(label: str) -> str:
        if label.startswith("当日"):
            label = label[2:]
        return label

    def _analysis_metric_label(self, field_key: str) -> str:
        return self._normalize_analysis_metric_label(self.analytics_service.get_metric_label(field_key))

    def _build_ranking_tab(self) -> None:
        ranking_tab = QWidget()
        layout = QVBoxLayout(ranking_tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        bar.addWidget(QLabel("排行指标"))
        self.ranking_metric_combo = QComboBox()
        for text, key in self._ranking_metric_options():
            self.ranking_metric_combo.addItem(text, key)
        bar.addWidget(self.ranking_metric_combo)

        bar.addWidget(QLabel("Top"))
        self.ranking_top_n_combo = QComboBox()
        for value in [5, 10, 20]:
            self.ranking_top_n_combo.addItem(str(value), value)
        self.ranking_top_n_combo.setCurrentIndex(1)
        bar.addWidget(self.ranking_top_n_combo)
        bar.addStretch()

        self.ranking_chart = ChartWidget()
        layout.addLayout(bar)
        layout.addWidget(self.ranking_chart, 1)
        self.chart_tabs.addTab(ranking_tab, "排行")

    def _ranking_metric_options(self) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        for label, field_key in self.analytics_service.get_analysis_metric_options(ANALYSIS_TYPE_RANKING):
            label = self._normalize_analysis_metric_label(label)
            options.append((f"{label} Top N", field_key))
        if not options:
            options.append(("回款金额 Top N", "repayment_amount"))
        return options

    def reload_field_config(self) -> None:
        trend_current = str(self.trend_metric_combo.currentData() or "")
        ranking_current = str(self.ranking_metric_combo.currentData() or "")

        self.trend_metric_combo.blockSignals(True)
        self.trend_metric_combo.clear()
        trend_index = 0
        for idx, (text, key) in enumerate(self._trend_metric_options()):
            self.trend_metric_combo.addItem(text, key)
            if key == trend_current:
                trend_index = idx
        self.trend_metric_combo.setCurrentIndex(trend_index)
        self.trend_metric_combo.blockSignals(False)

        self.ranking_metric_combo.blockSignals(True)
        self.ranking_metric_combo.clear()
        ranking_index = 0
        for idx, (text, key) in enumerate(self._ranking_metric_options()):
            self.ranking_metric_combo.addItem(text, key)
            if key == ranking_current:
                ranking_index = idx
        self.ranking_metric_combo.setCurrentIndex(ranking_index)
        self.ranking_metric_combo.blockSignals(False)

        self.on_query()

    def _build_funnel_tab(self) -> None:
        funnel_tab = QWidget()
        layout = QHBoxLayout(funnel_tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.funnel_chart = ChartWidget()
        self.funnel_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.funnel_rate_group = QGroupBox("关键转化率")
        self.funnel_rate_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.funnel_rate_group.setMinimumWidth(180)
        rate_form = QFormLayout(self.funnel_rate_group)
        rate_form.setContentsMargins(8, 8, 8, 8)
        for key, text in [
            ("signing_rate", "签约率"),
            ("sales_conversion_rate", "销售转化率"),
            ("warrant_conversion_rate", "权证转化率"),
        ]:
            label = QLabel("")
            self._funnel_rate_labels[key] = label
            rate_form.addRow(text, label)

        layout.addWidget(self.funnel_chart, 1)
        layout.addWidget(self.funnel_rate_group)
        self.chart_tabs.addTab(funnel_tab, "转化")

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

    def _apply_kpi_cards(self, kpis: dict) -> None:
        money_keys = {"repayment_amount_total", "loan_amount_total"}
        int_keys = {"visit_total", "signing_total", "repayment_customer_total"}
        pct_keys = {"signing_rate", "quality_visit_rate", "sales_conversion_rate", "warrant_conversion_rate", "target_progress"}

        for key, label in self._kpi_value_labels.items():
            value = kpis.get(key)
            if key in money_keys:
                label.setText(format_money(value))
                continue
            if key in int_keys:
                label.setText(format_int(value))
                continue
            if key in pct_keys:
                if key == "target_progress" and kpis.get("cross_cycle"):
                    label.setText("")
                else:
                    label.setText(format_percent(value))
                continue
            label.setText(str(value or "-"))

    def _render_trend_chart(self, *_args) -> None:
        if not self._charts_available:
            self.trend_chart.clear_chart("未安装或未正确加载 matplotlib，图表不可用")
            return
        metric_key = str(self.trend_metric_combo.currentData() or "repayment_amount")
        y_label = self._analysis_metric_label(metric_key) if metric_key else "回款金额"
        title = f"{y_label}趋势（按天）"
        if not self._current_trend_points:
            self.trend_chart.clear_chart("当前条件下暂无趋势数据")
            return

        dates = [str(item.get("date", ""))[5:] for item in self._current_trend_points]
        values = [float(item.get(metric_key, 0) or 0) for item in self._current_trend_points]
        try:
            self.trend_chart.plot_line(
                dates=dates,
                series=[{"label": y_label, "values": values}],
                title=title,
                y_label=y_label,
            )
        except Exception as exc:  # noqa: BLE001
            self.trend_chart.clear_chart("趋势图渲染失败")
            self.rule_info.setText(f"趋势图渲染失败：{exc}")

    def _render_ranking_chart(self, *_args) -> None:
        if not self._charts_available:
            self.ranking_chart.clear_chart("未安装或未正确加载 matplotlib，图表不可用")
            return
        metric_key = str(self.ranking_metric_combo.currentData() or "repayment_amount")
        top_n = int(self.ranking_top_n_combo.currentData() or 10)
        ranking = self.analytics_service.get_ranking_by_account_manager(
            query_rows=self._current_query_rows,
            metric_key=metric_key,
            top_n=top_n,
        )
        if not ranking:
            self.ranking_chart.clear_chart("当前条件下暂无排行数据")
            return

        labels = [str(item.get("account_manager_name", "")) for item in ranking]
        values = [float(item.get("value", 0) or 0) for item in ranking]
        as_percent = self.analytics_service.is_percent_metric(metric_key)
        title = f"{self.ranking_metric_combo.currentText()}（Top {len(ranking)}）"
        try:
            self.ranking_chart.plot_horizontal_bar(
                labels=labels,
                values=values,
                title=title,
                x_label="占比" if as_percent else "数值",
                as_percent=as_percent,
            )
        except Exception as exc:  # noqa: BLE001
            self.ranking_chart.clear_chart("排行图渲染失败")
            self.rule_info.setText(f"排行图渲染失败：{exc}")

    def _render_funnel_chart(self, *_args) -> None:
        if not self._charts_available:
            self.funnel_chart.clear_chart("未安装或未正确加载 matplotlib，图表不可用")
            for label in self._funnel_rate_labels.values():
                label.setText("")
            return
        funnel = self.analytics_service.get_funnel_metrics(self._current_query_rows)
        labels = ["上门量", "有效上门量", "签约量", "回款客户数"]
        values = [
            float(funnel.get("visit_count", 0) or 0),
            float(funnel.get("valid_visit_count", 0) or 0),
            float(funnel.get("signing_count", 0) or 0),
            float(funnel.get("repayment_customer_count", 0) or 0),
        ]
        if sum(values) <= 0:
            self.funnel_chart.clear_chart("当前条件下暂无转化数据")
            for label in self._funnel_rate_labels.values():
                label.setText("")
            return

        try:
            self.funnel_chart.plot_funnel(labels=labels, values=values, title="转化分析")
            self._funnel_rate_labels["signing_rate"].setText(format_percent(funnel.get("signing_rate")))
            self._funnel_rate_labels["sales_conversion_rate"].setText(format_percent(funnel.get("sales_conversion_rate")))
            self._funnel_rate_labels["warrant_conversion_rate"].setText(format_percent(funnel.get("warrant_conversion_rate")))
        except Exception as exc:  # noqa: BLE001
            self.funnel_chart.clear_chart("转化图渲染失败")
            self.rule_info.setText(f"转化图渲染失败：{exc}")
            for label in self._funnel_rate_labels.values():
                label.setText("")

    def _refresh_compact_scope(self) -> None:
        if not self._filter_collapsed:
            self.compact_scope_label.clear()
            self.compact_scope_label.setVisible(False)
            return

        mode = self.mode_combo.currentText()
        selected_count = len(self._checked_team_ids())
        range_text = self.range_info.text().replace("分析范围：", "").strip()
        parts = [f"模式：{mode}", f"团队：{selected_count}个"]
        if range_text:
            parts.append(f"范围：{range_text}")
        self.compact_scope_label.setText(" | ".join(parts))
        self.compact_scope_label.setVisible(True)

    def _sync_section_visibility(self) -> None:
        if self._filter_collapsed:
            self.filter_group.setVisible(False)
            self.filter_group.setMinimumHeight(0)
            self.filter_group.setMaximumHeight(0)
            self.toggle_filter_btn.setText("▼ 展开筛选条件")
        else:
            self.filter_group.setVisible(True)
            self.filter_group.setMinimumHeight(0)
            self.filter_group.setMaximumHeight(self._filter_max_height)
            self.toggle_filter_btn.setText("▲ 隐藏筛选条件")

        if self._kpi_collapsed:
            self.kpi_group.setVisible(False)
            self.kpi_group.setMinimumHeight(0)
            self.kpi_group.setMaximumHeight(0)
            self.toggle_kpi_btn.setText("▼ 展开概览")
        else:
            self.kpi_group.setVisible(True)
            self.kpi_group.setMinimumHeight(0)
            self.kpi_group.setMaximumHeight(self._kpi_max_height)
            self.toggle_kpi_btn.setText("▲ 隐藏概览")

        self._refresh_compact_scope()
        self.page_layout.invalidate()
        self.page.adjustSize()
        self.page.updateGeometry()
        self.page_scroll.updateGeometry()

    def on_toggle_filter_panel(self, checked: bool) -> None:
        self._filter_collapsed = bool(checked)
        self._sync_section_visibility()

    def on_toggle_kpi_panel(self, checked: bool) -> None:
        self._kpi_collapsed = bool(checked)
        self._sync_section_visibility()

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
            query_result = self.record_service.get_query_summary_grouped_by_account_manager(
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

        cross_cycle = bool(query_result.get("cross_cycle"))
        self.range_info.setText(f"分析范围：{query_result.get('start_date', '')} ~ {query_result.get('end_date', '')}")
        if not self._charts_available:
            self.rule_info.setText("未安装或未正确加载 matplotlib，图表不可用")
        elif not selected_team_ids:
            self.rule_info.setText("当前未勾选团队，分析结果为空")
        else:
            self.rule_info.setText("跨结算周期区间：目标完成进度已置空" if cross_cycle else "")

        bundle = self.analytics_service.build_analysis_bundle(
            mode=mode,
            base_date=self.base_date.date().toString("yyyy-MM-dd"),
            team_ids=selected_team_ids,
            custom_start=custom_start,
            custom_end=custom_end,
            ranking_metric=str(self.ranking_metric_combo.currentData() or "repayment_amount"),
            top_n=int(self.ranking_top_n_combo.currentData() or 10),
            query_result=query_result,
        )
        self._current_query_rows = list(query_result.get("rows", []))
        self._current_trend_points = list(bundle.get("trend", []))
        self._apply_kpi_cards(bundle.get("kpis", {}))
        self._render_trend_chart()
        self._render_ranking_chart()
        self._render_funnel_chart()
        self._refresh_compact_scope()

    def on_reset(self) -> None:
        self.mode_combo.setCurrentText(self.MODE_DAY)
        self.base_date.setDate(QDate.currentDate())
        self.custom_start.setDate(QDate.currentDate())
        self.custom_end.setDate(QDate.currentDate())
        self._set_all_team_checked(True)
        self.range_info.setText("")
        self.rule_info.setText("")
        for label in self._kpi_value_labels.values():
            label.setText("-")
        for label in self._funnel_rate_labels.values():
            label.setText("")
        self._current_query_rows = []
        self._current_trend_points = []
        self.trend_chart.clear_chart("暂无数据")
        self.ranking_chart.clear_chart("暂无数据")
        self.funnel_chart.clear_chart("暂无数据")
        self._refresh_compact_scope()
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
        control_h = self._scale(metrics.control_height, 22)
        button_h = self._scale(metrics.button_height, 24)

        self.page_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.page_layout.setSpacing(page_spacing)

        top_actions = self.top_action_row.layout()
        if top_actions is not None:
            top_actions.setSpacing(max(4, section_spacing))

        self.filter_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.filter_grid.setHorizontalSpacing(section_spacing)
        self.filter_grid.setVerticalSpacing(max(2, section_spacing - 1))
        self.kpi_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.kpi_grid.setHorizontalSpacing(section_spacing)
        self.kpi_grid.setVerticalSpacing(max(3, section_spacing))

        for widget in [self.mode_combo, self.base_date, self.custom_start, self.custom_end, self.week_combo]:
            widget.setMinimumHeight(control_h)
        for btn in [self.week_prev_btn, self.week_next_btn, self.query_btn, self.reset_btn, self.toggle_filter_btn, self.toggle_kpi_btn]:
            btn.setMinimumHeight(button_h)

        self.team_list.setMaximumHeight(self._scale(metrics.team_list_max_height, 68))

        self._kpi_columns = max(3, int(metrics.kpi_columns))
        self._reflow_kpi_cards(columns=self._kpi_columns)

        card_height = self._scale(metrics.kpi_card_height, 50)
        for card in self._kpi_cards:
            card.setMinimumHeight(card_height)
            card.setMaximumHeight(card_height + self._scale(16, 10))

        kpi_rows = (len(self._kpi_cards) + self._kpi_columns - 1) // self._kpi_columns
        kpi_total = kpi_rows * (card_height + max(3, section_spacing)) + self._scale(28, 20)
        self._kpi_max_height = max(self._scale(84, 72), kpi_total)
        self._filter_max_height = self._scale(max(120, int(metrics.analysis_top_height * 0.56)), 100)

        self.chart_tabs.setMinimumHeight(self._scale(metrics.chart_min_height, 260))
        self.funnel_rate_group.setMinimumWidth(self._scale(180, 140))
        self._sync_section_visibility()

    def apply_view_scale(self, factor: float) -> None:
        for chart in [self.trend_chart, self.ranking_chart, self.funnel_chart]:
            chart.apply_view_scale(factor)
        if self._layout_profile is not None:
            self.apply_layout_profile(self._layout_profile)
            return
        self.team_list.setMaximumHeight(max(72, int(round(105 * factor))))
        for card in self._kpi_cards:
            card.setMinimumHeight(max(48, int(round(70 * factor))))
