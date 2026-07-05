from __future__ import annotations

import json
from typing import Any, Dict, List

from app.fields.registry import (
    PAGE_ANALYSIS,
    PAGE_DATA_ENTRY,
    PAGE_EXCEL_EXPORT,
    PAGE_JSON_EXPORT,
    PAGE_PNG_TODAY,
    PAGE_QUERY_SUMMARY,
    PAGE_TODAY_DISPLAY,
)
from app.services.field_admin_config_service import (
    AGGREGATIONS,
    CATEGORIES,
    DATA_TYPES,
)
from app.utils.qt_compat import Qt, Signal
from app.utils.qt_compat import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QApplication,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


PAGE_LABELS = [
    ("数据录入", PAGE_DATA_ENTRY),
    ("今日展示", PAGE_TODAY_DISPLAY),
    ("查询汇总", PAGE_QUERY_SUMMARY),
    ("数据分析", PAGE_ANALYSIS),
    ("PNG 导出", PAGE_PNG_TODAY),
    ("Excel 导出", PAGE_EXCEL_EXPORT),
    ("JSON 导出", PAGE_JSON_EXPORT),
]


class FieldReportConfigTab(QWidget):
    config_changed = Signal()

    def __init__(self, field_admin_config_service, operator_getter=None, parent=None) -> None:
        super().__init__(parent)
        self.field_admin_config_service = field_admin_config_service
        self.operator_getter = operator_getter
        self._field_rows: List[Dict[str, Any]] = []
        self._page_rows: List[Dict[str, Any]] = []
        self._current_field_key = ""
        self.overview_value_labels: Dict[str, QLabel] = {}
        self._last_health_items: List[Dict[str, Any]] = []

        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        hint = QLabel("字段与报表配置仅管理员可用。系统字段不会被物理删除，新增日报字段默认使用动态指标存储。")
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        root.addWidget(hint)

        backup_bar = QHBoxLayout()
        self.config_export_btn = QPushButton("导出配置")
        self.config_import_btn = QPushButton("导入配置")
        self.config_reset_btn = QPushButton("恢复全部默认")
        self.config_export_btn.setProperty("buttonRole", "secondary")
        self.config_import_btn.setProperty("buttonRole", "secondary")
        self.config_reset_btn.setProperty("buttonRole", "danger")
        backup_bar.addWidget(self.config_export_btn)
        backup_bar.addWidget(self.config_import_btn)
        backup_bar.addWidget(self.config_reset_btn)
        backup_bar.addStretch()
        root.addLayout(backup_bar)

        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.overview_tab = self._build_overview_tab()
        self.field_tab = self._build_field_tab()
        self.entry_config_tab = self._build_page_tab(PAGE_DATA_ENTRY)
        self.display_config_tab = self._build_page_tab(PAGE_TODAY_DISPLAY)
        self.png_config_tab = self._build_png_tab()
        self.tabs.addTab(self.overview_tab, "配置总览")
        self.tabs.addTab(self.field_tab, "字段管理")
        self.tabs.addTab(self.entry_config_tab, "数据录入配置")
        self.tabs.addTab(self.display_config_tab, "今日展示 / 查询汇总配置")
        self.tabs.addTab(self.png_config_tab, "PNG 导出配置")
        root.addWidget(self.tabs, 1)
        self.config_export_btn.clicked.connect(self.on_export_config)
        self.config_import_btn.clicked.connect(self.on_import_config)
        self.config_reset_btn.clicked.connect(self.on_reset_all_config)

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        summary_group = QGroupBox("配置状态")
        summary_layout = QGridLayout(summary_group)
        summary_layout.setContentsMargins(8, 8, 8, 8)
        summary_layout.setHorizontalSpacing(14)
        summary_layout.setVerticalSpacing(8)

        items = [
            ("enabled_field_count", "当前启用字段数"),
            ("entry_field_count", "日报录入字段数"),
            ("today_field_count", "今日展示字段数"),
            ("query_field_count", "查询汇总字段数"),
            ("analysis_field_count", "可分析字段数"),
            ("png_template_count", "PNG 模板数量"),
            ("latest_action_time", "最近修改时间"),
            ("latest_operator", "最近修改人"),
            ("health_status", "配置健康状态"),
            ("version_status", "配置版本状态"),
        ]
        for index, (key, label_text) in enumerate(items):
            label = QLabel(label_text)
            label.setObjectName("formLabel")
            value = QLabel("-")
            value.setObjectName("summaryValue")
            value.setWordWrap(True)
            self.overview_value_labels[key] = value
            row = index // 2
            col = (index % 2) * 2
            summary_layout.addWidget(label, row, col)
            summary_layout.addWidget(value, row, col + 1)

        quick_group = QGroupBox("常用操作")
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.setContentsMargins(8, 8, 8, 8)
        quick_layout.setSpacing(6)
        quick_row_top = QHBoxLayout()
        quick_row_bottom = QHBoxLayout()
        quick_row_top.setSpacing(6)
        quick_row_bottom.setSpacing(6)
        self.overview_new_metric_btn = QPushButton("新增日报指标")
        self.overview_entry_btn = QPushButton("调整数据录入顺序")
        self.overview_today_btn = QPushButton("调整今日展示顺序")
        self.overview_png_btn = QPushButton("调整 PNG 导出字段")
        self.overview_health_btn = QPushButton("检查配置")
        self.overview_export_btn = QPushButton("导出配置备份")
        self.overview_reset_btn = QPushButton("恢复默认配置")
        self.overview_new_metric_btn.setProperty("buttonRole", "primary")
        self.overview_health_btn.setProperty("buttonRole", "primary")
        self.overview_reset_btn.setProperty("buttonRole", "danger")
        for btn in (
            self.overview_entry_btn,
            self.overview_today_btn,
            self.overview_png_btn,
            self.overview_export_btn,
        ):
            btn.setProperty("buttonRole", "secondary")
        for btn in (
            self.overview_new_metric_btn,
            self.overview_entry_btn,
            self.overview_today_btn,
            self.overview_png_btn,
        ):
            quick_row_top.addWidget(btn)
        quick_row_top.addStretch()
        for btn in (
            self.overview_health_btn,
            self.overview_export_btn,
            self.overview_reset_btn,
        ):
            quick_row_bottom.addWidget(btn)
        quick_row_bottom.addStretch()
        quick_layout.addLayout(quick_row_top)
        quick_layout.addLayout(quick_row_bottom)

        health_group = QGroupBox("配置健康检查")
        health_layout = QVBoxLayout(health_group)
        health_layout.setContentsMargins(8, 8, 8, 8)
        self.health_summary_label = QLabel("点击“检查配置”查看字段、页面和 PNG 模板配置状态。")
        self.health_summary_label.setObjectName("hintText")
        self.health_summary_label.setWordWrap(True)
        self.health_table = QTableWidget(0, 3)
        self.health_table.setHorizontalHeaderLabels(["级别", "检查项", "说明"])
        self.health_table.setAlternatingRowColors(True)
        self.health_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.health_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._apply_table_resize_policy(self.health_table, stretch_columns=[2], compact_columns=[0, 1])
        health_button_row = QHBoxLayout()
        self.health_copy_btn = QPushButton("复制检查结果")
        self.health_copy_btn.setProperty("buttonRole", "secondary")
        health_button_row.addWidget(self.health_copy_btn)
        health_button_row.addStretch()
        health_layout.addWidget(self.health_summary_label)
        health_layout.addWidget(self.health_table, 1)
        health_layout.addLayout(health_button_row)

        layout.addWidget(summary_group)
        layout.addWidget(quick_group)
        layout.addWidget(health_group, 1)

        self.overview_new_metric_btn.clicked.connect(self.on_overview_new_metric)
        self.overview_entry_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.entry_config_tab))
        self.overview_today_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.display_config_tab))
        self.overview_png_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.png_config_tab))
        self.overview_health_btn.clicked.connect(self.on_check_config)
        self.overview_export_btn.clicked.connect(self.on_export_config)
        self.overview_reset_btn.clicked.connect(self.on_reset_all_config)
        self.health_copy_btn.clicked.connect(self.on_copy_health_results)
        return self._make_scroll_area(page)

    def _build_field_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        button_row = QHBoxLayout()
        self.field_refresh_btn = QPushButton("刷新")
        self.field_new_btn = QPushButton("新增字段")
        self.field_disable_btn = QPushButton("停用字段")
        self.field_refresh_btn.setProperty("buttonRole", "secondary")
        self.field_new_btn.setProperty("buttonRole", "primary")
        self.field_disable_btn.setProperty("buttonRole", "danger")
        button_row.addWidget(self.field_refresh_btn)
        button_row.addWidget(self.field_new_btn)
        button_row.addWidget(self.field_disable_btn)
        button_row.addStretch()

        self.field_table = QTableWidget(0, 9)
        self.field_table.setHorizontalHeaderLabels(
            ["字段编码", "显示名称", "类型", "分类", "分组", "统计", "启用", "可录入", "系统"]
        )
        self.field_table.setAlternatingRowColors(True)
        self.field_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.field_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._apply_table_resize_policy(self.field_table, stretch_columns=[0, 1], compact_columns=[2, 6, 7, 8])

        left_layout.addLayout(button_row)
        left_layout.addWidget(self.field_table, 1)

        editor = QGroupBox("字段编辑")
        form = QFormLayout(editor)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)

        self.field_key_edit = QLineEdit()
        self.field_label_edit = QLineEdit()
        self.data_type_combo = QComboBox()
        self.data_type_combo.addItems(list(DATA_TYPES))
        self.category_combo = QComboBox()
        self.category_combo.addItems(list(CATEGORIES))
        self.group_key_edit = QLineEdit()
        self.default_value_edit = QLineEdit()
        self.aggregation_combo = QComboBox()
        self.aggregation_combo.addItems(list(AGGREGATIONS))
        self.formula_id_combo = QComboBox()
        self.formula_id_combo.addItem("")
        for formula_id in sorted(self.field_admin_config_service.formula_service.get_calculators().keys()):
            self.formula_id_combo.addItem(formula_id)
        self.enabled_check = QCheckBox("启用")
        self.editable_check = QCheckBox("可录入")
        self.required_check = QCheckBox("必填")
        self.system_field_label = QLabel("-")
        self.visibility_checks = {}
        visibility_box = QGroupBox("参与页面 / 导出")
        visibility_layout = QVBoxLayout(visibility_box)
        visibility_layout.setContentsMargins(6, 6, 6, 6)
        for label, page_key in PAGE_LABELS:
            check = QCheckBox(label)
            self.visibility_checks[page_key] = check
            visibility_layout.addWidget(check)

        form.addRow("字段编码", self.field_key_edit)
        form.addRow("显示名称", self.field_label_edit)
        form.addRow("字段类型", self.data_type_combo)
        form.addRow("字段分类", self.category_combo)
        form.addRow("所属分组", self.group_key_edit)
        form.addRow("默认值", self.default_value_edit)
        form.addRow("统计方式", self.aggregation_combo)
        form.addRow("内置公式", self.formula_id_combo)
        form.addRow("", self.enabled_check)
        form.addRow("", self.editable_check)
        form.addRow("", self.required_check)
        form.addRow("系统字段", self.system_field_label)
        form.addRow("", visibility_box)

        self.field_save_btn = QPushButton("保存字段")
        self.field_save_btn.setProperty("buttonRole", "primary")
        form.addRow("", self.field_save_btn)

        splitter.addWidget(left)
        splitter.addWidget(self._make_scroll_area(editor))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self.field_refresh_btn.clicked.connect(self.reload_fields)
        self.field_new_btn.clicked.connect(self.on_new_field)
        self.field_disable_btn.clicked.connect(self.on_disable_field)
        self.field_save_btn.clicked.connect(self.on_save_field)
        self.field_table.itemSelectionChanged.connect(self.on_field_selected)
        return page

    def _build_page_tab(self, initial_page_key: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("配置页面"))
        combo = QComboBox()
        for label, key in PAGE_LABELS:
            if initial_page_key == PAGE_DATA_ENTRY and key != PAGE_DATA_ENTRY:
                continue
            if initial_page_key != PAGE_DATA_ENTRY and key == PAGE_DATA_ENTRY:
                continue
            if initial_page_key != PAGE_DATA_ENTRY and key == PAGE_PNG_TODAY:
                continue
            combo.addItem(label, key)
        toolbar.addWidget(combo)
        load_btn = QPushButton("加载")
        save_btn = QPushButton("保存配置")
        restore_btn = QPushButton("恢复默认")
        load_btn.setProperty("buttonRole", "secondary")
        save_btn.setProperty("buttonRole", "primary")
        restore_btn.setProperty("buttonRole", "secondary")
        toolbar.addWidget(load_btn)
        toolbar.addWidget(save_btn)
        toolbar.addWidget(restore_btn)
        toolbar.addStretch()

        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["显示", "字段编码", "显示名称", "类型", "分组", "顺序"])
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        self._apply_table_resize_policy(table, stretch_columns=[1, 2, 4], compact_columns=[0, 3, 5])

        move_row = QHBoxLayout()
        top_btn = QPushButton("置顶")
        up_btn = QPushButton("上移")
        down_btn = QPushButton("下移")
        bottom_btn = QPushButton("置底")
        for btn in (top_btn, up_btn, down_btn, bottom_btn):
            btn.setProperty("buttonRole", "secondary")
            move_row.addWidget(btn)
        move_row.addStretch()

        layout.addLayout(toolbar)
        layout.addWidget(table, 1)
        layout.addLayout(move_row)

        page._page_combo = combo
        page._page_table = table
        page._load_btn = load_btn
        page._save_btn = save_btn
        page._restore_btn = restore_btn
        load_btn.clicked.connect(lambda: self.load_page_config(combo.currentData(), table))
        combo.currentIndexChanged.connect(lambda *_: self.load_page_config(combo.currentData(), table))
        save_btn.clicked.connect(lambda: self.on_save_page_config(combo.currentData(), table))
        restore_btn.clicked.connect(lambda: self.on_restore_page_config(combo.currentData(), table))
        top_btn.clicked.connect(lambda: self._move_selected_rows(table, "top"))
        up_btn.clicked.connect(lambda: self._move_selected_rows(table, "up"))
        down_btn.clicked.connect(lambda: self._move_selected_rows(table, "down"))
        bottom_btn.clicked.connect(lambda: self._move_selected_rows(table, "bottom"))
        return page

    def _build_png_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("PNG 模板"))
        self.png_template_combo = QComboBox()
        toolbar.addWidget(self.png_template_combo)
        self.png_load_btn = QPushButton("加载")
        self.png_save_btn = QPushButton("保存模板")
        self.png_restore_btn = QPushButton("恢复默认")
        self.png_load_btn.setProperty("buttonRole", "secondary")
        self.png_save_btn.setProperty("buttonRole", "primary")
        self.png_restore_btn.setProperty("buttonRole", "secondary")
        toolbar.addWidget(self.png_load_btn)
        toolbar.addWidget(self.png_save_btn)
        toolbar.addWidget(self.png_restore_btn)
        toolbar.addStretch()

        self.png_template_text = QTextEdit()
        self.png_template_text.setAcceptRichText(False)
        self.png_template_text.setLineWrapMode(QTextEdit.NoWrap)
        self.png_template_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        hint = QLabel("PNG 模板使用 JSON。每张分图 sections[].field_keys 建议不超过 14 个字段；配置异常时导出服务会回退默认模板。")
        hint.setObjectName("hintText")
        hint.setWordWrap(True)

        layout.addLayout(toolbar)
        layout.addWidget(hint)
        layout.addWidget(self.png_template_text, 1)

        self.png_load_btn.clicked.connect(self.load_png_template)
        self.png_template_combo.currentIndexChanged.connect(lambda *_: self.load_png_template())
        self.png_save_btn.clicked.connect(self.on_save_png_template)
        self.png_restore_btn.clicked.connect(self.on_restore_png_template)
        return page

    @staticmethod
    def _make_scroll_area(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return scroll

    @staticmethod
    def _apply_table_resize_policy(
        table: QTableWidget,
        stretch_columns: List[int],
        compact_columns: List[int],
    ) -> None:
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        for col in compact_columns:
            if 0 <= col < table.columnCount():
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for col in stretch_columns:
            if 0 <= col < table.columnCount():
                header.setSectionResizeMode(col, QHeaderView.Stretch)

    def reload(self) -> None:
        self.reload_overview()
        self.reload_fields()
        for i in range(self.tabs.count()):
            page = self.tabs.widget(i)
            combo = getattr(page, "_page_combo", None)
            table = getattr(page, "_page_table", None)
            if combo is not None and table is not None:
                self.load_page_config(combo.currentData(), table)
        self.reload_png_templates()

    def reload_overview(self) -> None:
        overview = self.field_admin_config_service.get_config_overview()
        health = overview.get("health", {})
        mapping = {
            "enabled_field_count": overview.get("enabled_field_count", 0),
            "entry_field_count": overview.get("entry_field_count", 0),
            "today_field_count": overview.get("today_field_count", 0),
            "query_field_count": overview.get("query_field_count", 0),
            "analysis_field_count": overview.get("analysis_field_count", 0),
            "png_template_count": overview.get("png_template_count", 0),
            "latest_action_time": overview.get("latest_action_time") or "暂无记录",
            "latest_operator": overview.get("latest_operator") or "暂无记录",
            "health_status": "{}（错误 {}，警告 {}）".format(
                health.get("status_label", "未知"),
                health.get("error_count", 0),
                health.get("warning_count", 0),
            ),
            "version_status": overview.get("version_status", ""),
        }
        for key, value in mapping.items():
            label = self.overview_value_labels.get(key)
            if label is not None:
                label.setText(str(value))

    def on_overview_new_metric(self) -> None:
        self.tabs.setCurrentWidget(self.field_tab)
        self.on_new_field()

    def on_check_config(self) -> None:
        result = self.field_admin_config_service.run_config_health_check(operator=self._operator())
        summary = result.get("summary", {})
        self.health_summary_label.setText(
            "检查完成：{}，错误 {} 项，警告 {} 项，正常 {} 项。".format(
                summary.get("status_label", "未知"),
                summary.get("error_count", 0),
                summary.get("warning_count", 0),
                summary.get("ok_count", 0),
            )
        )
        self._last_health_items = list(result.get("items", []))
        self._fill_health_table(self._last_health_items)
        self.reload_overview()
        self.config_changed.emit()

    def on_copy_health_results(self) -> None:
        text = self._format_health_items(self._last_health_items)
        if not text:
            text = self.health_summary_label.text()
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "提示", "配置检查结果已复制")

    def _fill_health_table(self, items: List[Dict[str, Any]]) -> None:
        self.health_table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            values = [
                self._health_level_label(str(item.get("level", ""))),
                item.get("title", ""),
                item.get("detail", ""),
            ]
            for col, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                self.health_table.setItem(row_idx, col, table_item)
        self._apply_table_resize_policy(self.health_table, stretch_columns=[2], compact_columns=[0, 1])

    def _format_health_items(self, items: List[Dict[str, Any]]) -> str:
        lines = []
        for item in items:
            lines.append(
                "[{}] {} - {}".format(
                    self._health_level_label(str(item.get("level", ""))),
                    item.get("title", ""),
                    item.get("detail", ""),
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _health_level_label(level: str) -> str:
        if level == "error":
            return "错误"
        if level == "warning":
            return "警告"
        if level == "ok":
            return "正常"
        return level or "-"

    def reload_fields(self) -> None:
        self._field_rows = self.field_admin_config_service.list_fields(include_disabled=True)
        self.field_table.setRowCount(len(self._field_rows))
        for row_idx, row in enumerate(self._field_rows):
            values = [
                row.get("field_key", ""),
                row.get("label", ""),
                row.get("data_type", ""),
                row.get("category", ""),
                row.get("group_key", ""),
                row.get("aggregation", ""),
                "是" if int(row.get("enabled", 0) or 0) else "否",
                "是" if int(row.get("editable", 0) or 0) else "否",
                "是" if int(row.get("system_field", 0) or 0) else "否",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row.get("field_key", ""))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.field_table.setItem(row_idx, col, item)
        self._apply_table_resize_policy(self.field_table, stretch_columns=[0, 1], compact_columns=[2, 6, 7, 8])
        if self._field_rows and not self._current_field_key:
            self.field_table.selectRow(0)

    def on_new_field(self) -> None:
        self._current_field_key = ""
        self.field_key_edit.setEnabled(True)
        self.field_key_edit.setText("")
        self.field_label_edit.setText("")
        self.data_type_combo.setCurrentText("int")
        self.category_combo.setCurrentText("raw_daily")
        self.group_key_edit.setText("process_behavior")
        self.default_value_edit.setText("0")
        self.aggregation_combo.setCurrentText("sum")
        self.formula_id_combo.setCurrentText("")
        self.enabled_check.setChecked(True)
        self.editable_check.setChecked(True)
        self.required_check.setChecked(False)
        self.system_field_label.setText("否")
        for check in self.visibility_checks.values():
            check.setChecked(False)
        self.visibility_checks[PAGE_DATA_ENTRY].setChecked(True)

    def on_field_selected(self) -> None:
        selected = self.field_table.selectedItems()
        if not selected:
            return
        row_idx = selected[0].row()
        if row_idx < 0 or row_idx >= len(self._field_rows):
            return
        row = self._field_rows[row_idx]
        self._current_field_key = str(row.get("field_key", ""))
        self.field_key_edit.setText(self._current_field_key)
        self.field_key_edit.setEnabled(False)
        self.field_label_edit.setText(str(row.get("label", "")))
        self.data_type_combo.setCurrentText(str(row.get("data_type", "int")))
        self.data_type_combo.setEnabled(int(row.get("system_field", 0) or 0) != 1)
        self.category_combo.setCurrentText(str(row.get("category", "raw_daily")))
        self.group_key_edit.setText(str(row.get("group_key", "")))
        self.default_value_edit.setText(str(row.get("default_value", "")))
        self.aggregation_combo.setCurrentText(str(row.get("aggregation", "none")))
        self.formula_id_combo.setCurrentText(str(row.get("formula_id", "")))
        self.enabled_check.setChecked(int(row.get("enabled", 0) or 0) == 1)
        self.editable_check.setChecked(int(row.get("editable", 0) or 0) == 1)
        self.required_check.setChecked(int(row.get("required", 0) or 0) == 1)
        self.system_field_label.setText("是" if int(row.get("system_field", 0) or 0) else "否")
        visibility = self.field_admin_config_service.get_field_visibility_map(self._current_field_key)
        for page_key, check in self.visibility_checks.items():
            check.setChecked(int(visibility.get(page_key, 0) or 0) == 1)

    def on_save_field(self) -> None:
        payload = self._field_payload_from_editor()
        if self._current_field_key:
            ok, message = self.field_admin_config_service.update_field(
                self._current_field_key,
                payload,
                operator=self._operator(),
            )
        else:
            ok, message = self.field_admin_config_service.create_field(payload, operator=self._operator())
        if not ok:
            QMessageBox.warning(self, "保存失败", message)
            return
        field_key = self._current_field_key or payload["field_key"]
        visible_by_page = {
            page_key: 1 if check.isChecked() else 0
            for page_key, check in self.visibility_checks.items()
        }
        ok, message = self.field_admin_config_service.save_field_visibility(
            field_key,
            visible_by_page,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "显示配置保存失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.reload()
        self.config_changed.emit()

    def on_disable_field(self) -> None:
        field_key = self._current_field_key
        if not field_key:
            QMessageBox.information(self, "提示", "请先选择字段")
            return
        if QMessageBox.question(
            self,
            "确认停用",
            "停用字段只会设置 enabled = 0，不会删除历史数据。是否继续？",
        ) != QMessageBox.Yes:
            return
        ok, message = self.field_admin_config_service.disable_field(field_key, operator=self._operator())
        if not ok:
            QMessageBox.warning(self, "停用失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.reload()
        self.config_changed.emit()

    def _field_payload_from_editor(self) -> Dict[str, Any]:
        return {
            "field_key": self.field_key_edit.text().strip(),
            "label": self.field_label_edit.text().strip(),
            "data_type": self.data_type_combo.currentText(),
            "category": self.category_combo.currentText(),
            "group_key": self.group_key_edit.text().strip(),
            "default_value": self.default_value_edit.text().strip(),
            "aggregation": self.aggregation_combo.currentText(),
            "formula_id": self.formula_id_combo.currentText(),
            "enabled": 1 if self.enabled_check.isChecked() else 0,
            "editable": 1 if self.editable_check.isChecked() else 0,
            "required": 1 if self.required_check.isChecked() else 0,
        }

    def load_page_config(self, page_key: str, table: QTableWidget) -> None:
        rows = self.field_admin_config_service.list_page_config(str(page_key or ""))
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            visible_item = QTableWidgetItem("")
            visible_item.setCheckState(Qt.Checked if int(row.get("visible", 0) or 0) else Qt.Unchecked)
            visible_item.setData(Qt.UserRole, row.get("field_key", ""))
            visible_item.setFlags(visible_item.flags() | Qt.ItemIsUserCheckable)
            table.setItem(row_idx, 0, visible_item)

            values = [
                row.get("field_key", ""),
                row.get("label", ""),
                row.get("data_type", ""),
                row.get("group_key", ""),
                row_idx + 1,
            ]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row.get("field_key", ""))
                if col not in {4}:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_idx, col, item)
        self._apply_table_resize_policy(table, stretch_columns=[1, 2, 4], compact_columns=[0, 3, 5])

    def on_save_page_config(self, page_key: str, table: QTableWidget) -> None:
        rows = self._collect_page_table_rows(table)
        ok, message = self.field_admin_config_service.save_page_config(
            str(page_key or ""),
            rows,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "保存失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.load_page_config(page_key, table)
        self.config_changed.emit()

    def on_restore_page_config(self, page_key: str, table: QTableWidget) -> None:
        if QMessageBox.question(self, "确认恢复", "确认恢复该页面的默认字段配置？") != QMessageBox.Yes:
            return
        ok, message = self.field_admin_config_service.restore_default_page_config(
            str(page_key or ""),
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "恢复失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.load_page_config(page_key, table)
        self.config_changed.emit()

    def _collect_page_table_rows(self, table: QTableWidget) -> List[Dict[str, Any]]:
        rows = []
        for row_idx in range(table.rowCount()):
            key_item = table.item(row_idx, 1)
            visible_item = table.item(row_idx, 0)
            group_item = table.item(row_idx, 4)
            if key_item is None:
                continue
            rows.append(
                {
                    "field_key": key_item.text().strip(),
                    "visible": 1 if visible_item is not None and visible_item.checkState() == Qt.Checked else 0,
                    "group_key": group_item.text().strip() if group_item is not None else "",
                }
            )
        return rows

    def _move_selected_rows(self, table: QTableWidget, direction: str) -> None:
        current = table.currentRow()
        if current < 0:
            return
        target = current
        if direction == "up":
            target = max(0, current - 1)
        elif direction == "down":
            target = min(table.rowCount() - 1, current + 1)
        elif direction == "top":
            target = 0
        elif direction == "bottom":
            target = table.rowCount() - 1
        if target == current:
            return
        row_values = self._take_table_row(table, current)
        self._insert_table_row(table, target, row_values)
        table.selectRow(target)
        self._renumber_page_table(table)

    def _take_table_row(self, table: QTableWidget, row: int) -> List[QTableWidgetItem]:
        values = []
        for col in range(table.columnCount()):
            item = table.takeItem(row, col)
            values.append(item if item is not None else QTableWidgetItem(""))
        table.removeRow(row)
        return values

    def _insert_table_row(self, table: QTableWidget, row: int, values: List[QTableWidgetItem]) -> None:
        table.insertRow(row)
        for col, item in enumerate(values):
            table.setItem(row, col, item)

    @staticmethod
    def _renumber_page_table(table: QTableWidget) -> None:
        for row_idx in range(table.rowCount()):
            item = table.item(row_idx, 5)
            if item is not None:
                item.setText(str(row_idx + 1))

    def reload_png_templates(self) -> None:
        templates = self.field_admin_config_service.list_templates(PAGE_PNG_TODAY)
        self.png_template_combo.blockSignals(True)
        self.png_template_combo.clear()
        for template in templates:
            self.png_template_combo.addItem(str(template.get("template_name", template.get("template_key", ""))), template.get("template_key", ""))
        self.png_template_combo.blockSignals(False)
        self.load_png_template()

    def load_png_template(self) -> None:
        template_key = str(self.png_template_combo.currentData() or "")
        if not template_key:
            self.png_template_text.setPlainText("")
            return
        template = self.field_admin_config_service.get_template(template_key)
        if not template:
            self.png_template_text.setPlainText("")
            return
        try:
            payload = json.loads(str(template.get("config_json", "{}") or "{}"))
            text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        except ValueError:
            text = str(template.get("config_json", ""))
        self.png_template_text.setPlainText(text)

    def on_save_png_template(self) -> None:
        template_key = str(self.png_template_combo.currentData() or "")
        ok, message = self.field_admin_config_service.save_template_config(
            template_key,
            self.png_template_text.toPlainText(),
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "保存失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.load_png_template()
        self.config_changed.emit()

    def on_restore_png_template(self) -> None:
        template_key = str(self.png_template_combo.currentData() or "")
        if QMessageBox.question(self, "确认恢复", "确认恢复 PNG 默认模板？") != QMessageBox.Yes:
            return
        ok, message = self.field_admin_config_service.restore_default_template(
            template_key,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "恢复失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.load_png_template()
        self.config_changed.emit()

    def _operator(self) -> str:
        if callable(self.operator_getter):
            return str(self.operator_getter() or "admin")
        return "admin"

    def on_export_config(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出字段配置",
            "field_config_backup.json",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        ok, message = self.field_admin_config_service.export_field_config_to_json(
            file_path,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "导出失败", message)
            return
        QMessageBox.information(self, "提示", "字段配置已导出：\n{}".format(message))

    def on_import_config(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入字段配置",
            "",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        if QMessageBox.question(
            self,
            "确认导入",
            "导入字段配置会覆盖页面显示配置和模板配置，但不会删除历史日报数据。是否继续？",
        ) != QMessageBox.Yes:
            return
        ok, message = self.field_admin_config_service.import_field_config_from_json(
            file_path,
            operator=self._operator(),
        )
        if not ok:
            QMessageBox.warning(self, "导入失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.reload()
        self.config_changed.emit()

    def on_reset_all_config(self) -> None:
        if QMessageBox.question(
            self,
            "确认恢复默认",
            "恢复全部默认会停用自定义字段并重置页面显示配置和模板配置；历史数据不会删除。是否继续？",
        ) != QMessageBox.Yes:
            return
        ok, message = self.field_admin_config_service.reset_field_config_to_default(operator=self._operator())
        if not ok:
            QMessageBox.warning(self, "恢复失败", message)
            return
        QMessageBox.information(self, "提示", message)
        self.reload()
        self.config_changed.emit()
