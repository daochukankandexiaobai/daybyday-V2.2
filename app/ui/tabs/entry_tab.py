from __future__ import annotations

from app.ui.layout_profile import LayoutProfile
from app.ui.tabs.entry_navigation_helper import EntryNavigationHelper
from app.ui.tabs.entry_table_config import (
    ENTRY_AMOUNT_COLUMNS,
    ENTRY_DISPLAY_HEADERS,
    ENTRY_EDITABLE_COLUMNS,
    ENTRY_FIELD_KEY_BY_COLUMN,
    ENTRY_FIELD_KEYS,
    ENTRY_HEADERS,
    ENTRY_INT_COLUMNS,
    ENTRY_PRIMARY_COLUMNS,
    ENTRY_SUMMARY_COLUMNS,
    build_entry_columns_from_config,
    build_entry_table_metadata,
)
from app.utils.qt_compat import QApplication, QByteArray, QDate, QColor, QFont, QKeySequence, QShortcut, Qt, QTimer, Signal
from app.utils.qt_compat import (
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
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

from app.utils.validators import (
    validate_non_negative_decimal_input,
    validate_non_negative_int_input,
)

class EntryTab(QWidget):
    record_saved = Signal()

    HEADER_STATE_SETTING_KEY = "ui.data_entry.header_state.v1"
    HEADER_STATE_SIGNATURE_SETTING_KEY = "ui.data_entry.header_state.signature.v1"
    HEADER_STATE_SAVE_DELAY_MS = 800

    HEADERS = ENTRY_HEADERS
    DISPLAY_HEADERS = ENTRY_DISPLAY_HEADERS
    FIELD_KEYS = ENTRY_FIELD_KEYS
    FIELD_KEY_BY_COLUMN = ENTRY_FIELD_KEY_BY_COLUMN
    EDITABLE_COLS = set(ENTRY_EDITABLE_COLUMNS)
    PRIMARY_ENTRY_COLS = list(ENTRY_PRIMARY_COLUMNS)

    INT_COLS = set(ENTRY_INT_COLUMNS)
    AMOUNT_COLS = set(ENTRY_AMOUNT_COLUMNS)
    SUMMARY_COLS = set(ENTRY_SUMMARY_COLUMNS)
    SUMMARY_LABEL = "团队汇总"
    COLUMN_CONFIGS = build_entry_columns_from_config()

    def __init__(self, record_service, team_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record_service = record_service
        self.team_service = team_service
        self.settings_service = getattr(team_service, "settings_service", None)
        self._load_entry_column_configs()
        self._summary_row_index = -1
        self._suppress_item_changed = False
        self._suppress_header_state_save = False
        self._using_saved_header_state = False
        self._header_state_restore_attempted = False
        self._layout_profile: LayoutProfile | None = None
        self._header_state_save_timer = QTimer(self)
        self._header_state_save_timer.setSingleShot(True)
        self._header_state_save_timer.setInterval(self.HEADER_STATE_SAVE_DELAY_MS)
        self._header_state_save_timer.timeout.connect(self.persist_table_view_state)
        self._build_ui()
        self._apply_table_column_layout()
        self._restore_table_view_state_once()
        self._connect_app_shutdown_save()
        self.reload_teams()

    def _load_entry_column_configs(self) -> None:
        getter = getattr(self.record_service, "get_entry_field_definitions", None)
        field_definitions = getter() if callable(getter) else None
        self.COLUMN_CONFIGS = build_entry_columns_from_config(field_definitions)
        metadata = build_entry_table_metadata(self.COLUMN_CONFIGS)
        self.FIELD_KEYS = metadata["field_keys"]
        self.HEADERS = metadata["headers"]
        self.DISPLAY_HEADERS = metadata["display_headers"]
        self.FIELD_KEY_BY_COLUMN = metadata["field_key_by_column"]
        self.EDITABLE_COLS = set(metadata["editable_columns"])
        self.PRIMARY_ENTRY_COLS = list(metadata["primary_columns"])
        self.INT_COLS = set(metadata["int_columns"])
        self.AMOUNT_COLS = set(metadata["amount_columns"])
        self.SUMMARY_COLS = set(metadata["summary_columns"])

    def reload_field_config(self) -> None:
        self.persist_table_view_state()
        self._load_entry_column_configs()
        self._suppress_header_state_save = True
        self.table.clear()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.DISPLAY_HEADERS)
        self._apply_table_column_layout()
        self._suppress_header_state_save = False
        self._header_state_restore_attempted = False
        self._restore_table_view_state_once()
        self.load_sheet()

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

        self.info_group = QGroupBox("日报录入信息")
        self.info_grid = QGridLayout(self.info_group)
        self.info_grid.setContentsMargins(8, 8, 8, 8)
        self.info_grid.setHorizontalSpacing(8)
        self.info_grid.setVerticalSpacing(4)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())

        self.team_combo = QComboBox()
        self.region_label = QLabel("-")
        self.team_manager_label = QLabel("-")
        self.cycle_label = QLabel("-")
        self.week_label = QLabel("-")

        self.info_grid.addWidget(QLabel("日期"), 0, 0)
        self.info_grid.addWidget(self.date_edit, 0, 1)
        self.info_grid.addWidget(QLabel("团队"), 0, 2)
        self.info_grid.addWidget(self.team_combo, 0, 3)

        self.info_grid.addWidget(QLabel("区域"), 1, 0)
        self.info_grid.addWidget(self.region_label, 1, 1)
        self.info_grid.addWidget(QLabel("团队经理"), 1, 2)
        self.info_grid.addWidget(self.team_manager_label, 1, 3)

        self.info_grid.addWidget(QLabel("结算周期"), 2, 0)
        self.info_grid.addWidget(self.cycle_label, 2, 1)
        self.info_grid.addWidget(QLabel("周期周次"), 2, 2)
        self.info_grid.addWidget(self.week_label, 2, 3)

        self.summary_group = QGroupBox("团队汇总（结算周期累计）")
        self.summary_grid = QGridLayout(self.summary_group)
        self.summary_grid.setContentsMargins(8, 8, 8, 8)
        self.summary_grid.setHorizontalSpacing(8)
        self.summary_grid.setVerticalSpacing(4)

        self.summary_labels: dict[str, QLabel] = {}
        self.summary_cards: list[QWidget] = []
        metrics = [
            ("repayment_amount_cumulative", "累计回款金额"),
            ("loan_amount_cumulative", "累计放款金额"),
            ("invitation_cumulative", "累计邀约"),
            ("signing_count_cumulative", "累计签约量"),
            ("quality_visit_count_cumulative", "累计优质上门量"),
            ("signing_rate", "签约率"),
            ("quality_visit_rate", "优质上门率"),
            ("target_progress", "目标完成进度"),
        ]
        for idx, (key, text) in enumerate(metrics):
            row = idx // 3
            col = idx % 3
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
            self.summary_cards.append(card)
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            self.summary_grid.addWidget(card, row, col)

        self.top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.addWidget(self.info_group)
        self.top_splitter.addWidget(self.summary_group)
        self.top_splitter.setStretchFactor(0, 3)
        self.top_splitter.setStretchFactor(1, 2)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.DISPLAY_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setWordWrap(False)
        self.table.setTabKeyNavigation(False)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionsClickable(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setTextElideMode(Qt.ElideNone)
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.horizontalHeader().sectionResized.connect(self._schedule_header_state_save)
        self.table.horizontalHeader().sectionMoved.connect(self._schedule_header_state_save)

        self.navigation_helper = EntryNavigationHelper(
            table=self.table,
            is_editable_cell=self._is_editable_cell,
            data_row_count_getter=self._data_row_count,
            parent=self,
        )
        self.table.setItemDelegate(self.navigation_helper.build_delegate())

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.table)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([180, 720])

        self.button_row = QWidget()
        btns = QHBoxLayout(self.button_row)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(6)

        self.save_btn = QPushButton("保存")
        self.save_btn.setProperty("buttonRole", "primary")
        self.submit_btn = QPushButton("提交")
        self.submit_btn.setProperty("buttonRole", "primary")
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setProperty("buttonRole", "secondary")
        self.clear_zero_btn = QPushButton("全部清零")
        self.clear_zero_btn.setProperty("buttonRole", "danger")
        self.copy_yesterday_btn = QPushButton("复制昨日名单")
        self.copy_yesterday_btn.setProperty("buttonRole", "secondary")
        self.refresh_summary_btn = QPushButton("刷新汇总")
        self.refresh_summary_btn.setProperty("buttonRole", "secondary")

        btns.addWidget(self.save_btn)
        btns.addWidget(self.submit_btn)
        btns.addSpacing(10)
        btns.addWidget(self.reset_btn)
        btns.addWidget(self.clear_zero_btn)
        btns.addSpacing(10)
        btns.addWidget(self.copy_yesterday_btn)
        btns.addWidget(self.refresh_summary_btn)
        btns.addStretch()

        self.page_layout.addWidget(self.main_splitter, 1)
        self.page_layout.addWidget(self.button_row)
        self.page_scroll.setWidget(self.page)
        root.addWidget(self.page_scroll, 1)

        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.save_shortcut.activated.connect(self.on_save_shortcut)

        self.team_combo.currentIndexChanged.connect(self.load_sheet)
        self.date_edit.dateChanged.connect(self.load_sheet)
        self.table.itemChanged.connect(self.on_table_item_changed)
        self.save_btn.clicked.connect(self.on_save)
        self.submit_btn.clicked.connect(self.on_submit)
        self.reset_btn.clicked.connect(self.on_reset)
        self.clear_zero_btn.clicked.connect(self.on_clear_zero)
        self.copy_yesterday_btn.clicked.connect(self.on_copy_yesterday)
        self.refresh_summary_btn.clicked.connect(self.on_refresh_summary)

    def _connect_app_shutdown_save(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.persist_table_view_state)

    def _settings_available(self) -> bool:
        return self.settings_service is not None

    def _header_state_signature(self) -> str:
        return "|".join(self.FIELD_KEYS)

    def _schedule_header_state_save(self, *_args) -> None:
        if self._suppress_header_state_save or not self._settings_available():
            return
        self._using_saved_header_state = True
        self._header_state_save_timer.start()

    def _restore_table_view_state_once(self) -> bool:
        if self._header_state_restore_attempted:
            return self._using_saved_header_state
        self._header_state_restore_attempted = True
        return self._restore_table_view_state()

    def _restore_table_view_state(self) -> bool:
        if not self._settings_available():
            return False

        try:
            raw_state = self.settings_service.get(self.HEADER_STATE_SETTING_KEY, "").strip()
            if not raw_state:
                return False

            saved_signature = self.settings_service.get(self.HEADER_STATE_SIGNATURE_SETTING_KEY, "").strip()
            if saved_signature and saved_signature != self._header_state_signature():
                return False

            state = QByteArray.fromBase64(QByteArray(raw_state.encode("ascii")))
            if state.isEmpty():
                return False

            self._suppress_header_state_save = True
            restored = bool(self.table.horizontalHeader().restoreState(state))
            self._using_saved_header_state = restored
            return restored
        except Exception:  # noqa: BLE001
            return False
        finally:
            self._suppress_header_state_save = False

    def persist_table_view_state(self) -> None:
        if not self._settings_available():
            return

        try:
            if self._header_state_save_timer.isActive():
                self._header_state_save_timer.stop()
            state = self.table.horizontalHeader().saveState()
            encoded = bytes(state.toBase64()).decode("ascii")
            self.settings_service.set(self.HEADER_STATE_SETTING_KEY, encoded)
            self.settings_service.set(self.HEADER_STATE_SIGNATURE_SETTING_KEY, self._header_state_signature())
        except Exception:  # noqa: BLE001
            return

    def _current_team_id(self) -> int:
        return int(self.team_combo.currentData() or 0)

    def _data_row_count(self) -> int:
        if self._summary_row_index < 0:
            return self.table.rowCount()
        return max(0, self.table.rowCount() - 1)

    def _is_summary_row(self, row: int) -> bool:
        return row >= 0 and row == self._summary_row_index

    def _is_editable_cell(self, row: int, col: int) -> bool:
        if row < 0 or col < 0:
            return False
        if row >= self._data_row_count():
            return False
        if col not in self.EDITABLE_COLS:
            return False
        item = self.table.item(row, col)
        if item is None:
            return True
        return bool(item.flags() & Qt.ItemIsEditable)

    def _field_key_for_col(self, col: int) -> str:
        return self.FIELD_KEY_BY_COLUMN.get(col, "")

    def _is_remark_col(self, col: int) -> bool:
        return self._field_key_for_col(col) == "remark"

    def _entry_cell_text_from_row(self, row: dict, col: int) -> str:
        cfg = self.COLUMN_CONFIGS[col]
        value = row.get(cfg.field_key, cfg.default)
        if cfg.field_key == "account_manager_name":
            value = row.get("account_manager_name", value)
        if cfg.field_key == "remark":
            return str(value or "")
        if col in self.AMOUNT_COLS:
            return f"{float(value or 0):.2f}"
        if col in self.INT_COLS:
            return str(int(value or 0))
        return str(value or "")

    def reload_teams(self) -> None:
        teams = self.team_service.list_teams()
        self.team_combo.blockSignals(True)
        self.team_combo.clear()
        for team in teams:
            label = f"{team['region']} / {team['team_name']} / {team['team_manager_name']}"
            self.team_combo.addItem(label, int(team["id"]))
        self.team_combo.blockSignals(False)

        if not teams:
            self.team_combo.setEnabled(False)
            self.table.setRowCount(0)
            self._summary_row_index = -1
            self.region_label.setText("-")
            self.team_manager_label.setText("-")
            self.cycle_label.setText("-")
            self.week_label.setText("-")
            for key in self.summary_labels:
                self._set_summary_value(key, 0 if key != "target_progress" and not key.endswith("_rate") else None)
            for btn in [
                self.save_btn,
                self.submit_btn,
                self.reset_btn,
                self.clear_zero_btn,
                self.copy_yesterday_btn,
                self.refresh_summary_btn,
            ]:
                btn.setEnabled(False)
            return

        self.team_combo.setEnabled(True)
        for btn in [
            self.save_btn,
            self.submit_btn,
            self.reset_btn,
            self.clear_zero_btn,
            self.copy_yesterday_btn,
            self.refresh_summary_btn,
        ]:
            btn.setEnabled(True)
        current_id = self.team_service.get_current_team_id()
        target_idx = 0
        for i in range(self.team_combo.count()):
            if int(self.team_combo.itemData(i) or 0) == current_id:
                target_idx = i
                break
        self.team_combo.setCurrentIndex(target_idx)
        self.load_sheet()

    def _set_summary_value(self, key: str, value) -> None:
        label = self.summary_labels[key]
        if key.endswith("_rate") or key == "target_progress":
            if value is None:
                label.setText("")
            else:
                label.setText(f"{float(value) * 100:.2f}%")
            return

        if key in {"repayment_amount_cumulative", "loan_amount_cumulative"}:
            label.setText(f"{float(value or 0):.2f}")
        else:
            label.setText(str(int(value or 0)))

    def load_sheet(self, *_args) -> None:
        team_id = self._current_team_id()
        if team_id <= 0:
            return

        self.team_service.set_current_team_id(team_id)
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        data = self.record_service.get_team_day_sheet(team_id, record_date)
        if not data.get("ok"):
            QMessageBox.warning(self, "提示", data.get("message", "加载失败"))
            return

        team = data["team"]
        self.region_label.setText(str(team.get("region", "")))
        self.team_manager_label.setText(str(team.get("team_manager_name", "")))
        self.cycle_label.setText(str(data.get("cycle_code", "")))
        self.week_label.setText(str(data.get("week_label", "")))

        rows = data.get("rows", [])
        self._suppress_item_changed = True
        self.table.setRowCount(len(rows) + 1)
        for row_idx, row in enumerate(rows):
            account_manager_id = int(row.get("account_manager_id", 0))
            for col, cfg in enumerate(self.COLUMN_CONFIGS):
                self._set_cell(
                    row_idx,
                    col,
                    self._entry_cell_text_from_row(row, col),
                    editable=cfg.editable,
                    account_manager_id=account_manager_id if cfg.field_key == "account_manager_name" else None,
                )
        self._render_summary_row()
        self._suppress_item_changed = False

        summary = data.get("summary", {})
        for key in self.summary_labels:
            self._set_summary_value(key, summary.get(key))

        self._apply_table_column_layout()
        self._focus_first_empty_cell(start_edit=False)

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        editable: bool = True,
        account_manager_id: int | None = None,
        summary: bool = False,
    ) -> None:
        item = QTableWidgetItem(str(text))
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if col == 0:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if account_manager_id is not None:
                item.setData(Qt.UserRole, account_manager_id)

        if col == 0 or self._is_remark_col(col):
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        elif col in self.AMOUNT_COLS:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignCenter)

        if summary:
            font: QFont = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setData(Qt.BackgroundRole, QColor("#FFF1F2"))
            item.setData(Qt.ForegroundRole, QColor("#7A111A"))
        elif editable and col in self.EDITABLE_COLS:
            item.setData(Qt.BackgroundRole, QColor("#FFFDF7"))
        self.table.setItem(row, col, item)

    def _cell_text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return (item.text() if item else "").strip()

    def _numeric_cell_value(self, row: int, col: int) -> float:
        text = self._cell_text(row, col)
        if col in self.AMOUNT_COLS:
            ok, value, _ = validate_non_negative_decimal_input(text, max_decimals=2)
            return float(value) if ok else 0.0
        ok, value, _ = validate_non_negative_int_input(text)
        return float(value) if ok else 0.0

    def _render_summary_row(self) -> None:
        self._summary_row_index = max(0, self.table.rowCount() - 1)
        self._refresh_summary_row()

    def _refresh_summary_row(self) -> None:
        if self.table.rowCount() <= 0:
            self._summary_row_index = -1
            return

        if self._summary_row_index < 0 or self._summary_row_index >= self.table.rowCount():
            self._summary_row_index = self.table.rowCount() - 1

        data_row_count = self._data_row_count()
        self._suppress_item_changed = True
        self._set_cell(self._summary_row_index, 0, self.SUMMARY_LABEL, editable=False, summary=True)
        for col in range(1, self.table.columnCount()):
            if col in self.SUMMARY_COLS:
                total = sum(self._numeric_cell_value(row, col) for row in range(data_row_count))
                if col in self.AMOUNT_COLS:
                    text = f"{float(total):.2f}"
                else:
                    text = str(int(total))
                self._set_cell(self._summary_row_index, col, text, editable=False, summary=True)
            else:
                self._set_cell(self._summary_row_index, col, "", editable=False, summary=True)
        self._suppress_item_changed = False

    def on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_item_changed:
            return
        if self._is_summary_row(item.row()):
            return
        if item.column() == 0:
            return
        self._refresh_summary_row()

    def collect_row_values_by_field_key(self, row_idx: int) -> dict:
        name_item = self.table.item(row_idx, 0)
        if name_item is None:
            raise ValueError(f"第{row_idx + 1}行缺少客户经理")

        account_manager_id = int(name_item.data(Qt.UserRole) or 0)
        name = name_item.text().strip()
        if account_manager_id <= 0 or not name:
            raise ValueError(f"第{row_idx + 1}行客户经理信息无效")

        values = {
            "account_manager_id": account_manager_id,
            "account_manager_name": name,
        }

        for col, cfg in enumerate(self.COLUMN_CONFIGS):
            if cfg.field_key == "account_manager_name":
                continue

            text = self._cell_text(row_idx, col)
            if cfg.required and text == "":
                raise ValueError(f"第{row_idx + 1}行[{self.HEADERS[col]}] 不能为空")

            if col in self.INT_COLS:
                ok, value, err = validate_non_negative_int_input(text)
                if not ok:
                    raise ValueError(f"第{row_idx + 1}行[{self.HEADERS[col]}] {err}")
                values[cfg.field_key] = int(value)
            elif col in self.AMOUNT_COLS:
                ok, value, err = validate_non_negative_decimal_input(text, max_decimals=2)
                if not ok:
                    raise ValueError(f"第{row_idx + 1}行[{self.HEADERS[col]}] {err}")
                values[cfg.field_key] = float(value)
            else:
                values[cfg.field_key] = text

        return values

    def validate_entry_values(self, row_idx: int, values: dict) -> list[str]:
        soft_warnings: list[str] = []

        visit = int(values.get("visit_count_daily", 0) or 0)
        invalid_visit = int(values.get("invalid_visit_count_daily", 0) or 0)
        quality_visit = int(values.get("quality_visit_count_daily", 0) or 0)
        signing = int(values.get("signing_count_daily", 0) or 0)
        approval = int(values.get("approval_customer_count_daily", 0) or 0)
        repayment_customers = int(values.get("repayment_customer_count_daily", 0) or 0)

        if invalid_visit > visit:
            raise ValueError(f"第{row_idx + 1}行无效上门不能大于总上门")
        if quality_visit > visit:
            raise ValueError(f"第{row_idx + 1}行优质上门不能大于总上门")

        if approval > signing:
            soft_warnings.append(f"第{row_idx + 1}行批复客户数大于签约量（允许保存）")
        if repayment_customers > visit:
            soft_warnings.append(f"第{row_idx + 1}行回款客户数大于上门量（允许保存）")
        return soft_warnings

    def _validate_and_collect_rows(self) -> tuple[list[dict], list[str]]:
        rows: list[dict] = []
        soft_warnings: list[str] = []

        for row_idx in range(self._data_row_count()):
            values = self.collect_row_values_by_field_key(row_idx)
            soft_warnings.extend(self.validate_entry_values(row_idx, values))
            rows.append(values)

        return rows, soft_warnings

    def _show_status_message(self, message: str, timeout_ms: int = 2600) -> None:
        win = self.window()
        status_bar_getter = getattr(win, "statusBar", None)
        if callable(status_bar_getter):
            bar = status_bar_getter()
            if bar is not None:
                bar.showMessage(message, timeout_ms)

    def _save(self, source_type: str, show_success_dialog: bool = True) -> bool:
        team_id = self._current_team_id()
        if team_id <= 0:
            QMessageBox.warning(self, "提示", "请先配置团队")
            return False

        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        if not record_date:
            QMessageBox.warning(self, "提示", "日期不能为空")
            return False

        try:
            rows, soft_warnings = self._validate_and_collect_rows()
        except ValueError as exc:
            QMessageBox.warning(self, "校验失败", str(exc))
            return False

        if self.record_service.has_team_day_data(team_id, record_date):
            answer = QMessageBox.question(
                self,
                "覆盖确认",
                "该团队该日期已有数据，继续保存将执行覆盖更新（命中记录 version +1）。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False

        if soft_warnings:
            answer = QMessageBox.question(
                self,
                "提示",
                "发现以下提醒（不拦截）：\n"
                + "\n".join(soft_warnings[:5])
                + ("\n..." if len(soft_warnings) > 5 else "")
                + "\n\n是否继续保存？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return False

        ok, message, stats = self.record_service.save_team_day_sheet(
            team_id=team_id,
            record_date=record_date,
            rows=rows,
            source_type=source_type,
        )
        if ok:
            detail = f"{message}"
            if int(stats.get("updated", 0)) > 0:
                detail += f"\n覆盖更新 {int(stats.get('updated', 0))} 条，version 已自动+1"

            if show_success_dialog:
                QMessageBox.information(self, "提示", detail)
            else:
                self._show_status_message("已保存（Ctrl+S）")

            self.record_saved.emit()
            self.load_sheet()
            return True

        QMessageBox.warning(self, "保存失败", message)
        return False

    def on_save(self) -> None:
        self._save("local", show_success_dialog=True)

    def on_save_shortcut(self) -> None:
        self._save("local", show_success_dialog=False)

    def on_submit(self) -> None:
        self._save("local_submit", show_success_dialog=True)

    def on_reset(self) -> None:
        self.load_sheet()

    def on_clear_zero(self) -> None:
        for row in range(self._data_row_count()):
            for col in range(self.table.columnCount()):
                if col == 0:
                    continue
                if col in self.AMOUNT_COLS:
                    self._set_cell(row, col, "0.00")
                elif col in self.INT_COLS:
                    self._set_cell(row, col, "0")
                else:
                    self._set_cell(row, col, "")
        self._refresh_summary_row()
        self._focus_first_empty_cell(start_edit=False)

    def on_copy_yesterday(self) -> None:
        team_id = self._current_team_id()
        if team_id <= 0:
            return
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        order = self.record_service.copy_yesterday_member_order(team_id, record_date)
        if not order:
            QMessageBox.information(self, "提示", "昨日无名单可复制")
            return

        row_map: dict[int, list[str]] = {}
        for row in range(self._data_row_count()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            manager_id = int(item.data(Qt.UserRole) or 0)
            row_map[manager_id] = [self._cell_text(row, col) for col in range(self.table.columnCount())]

        reordered_ids: list[int] = []
        for manager_id in order:
            if manager_id in row_map:
                reordered_ids.append(manager_id)
        for manager_id in row_map:
            if manager_id not in reordered_ids:
                reordered_ids.append(manager_id)

        self._suppress_item_changed = True
        self.table.setRowCount(len(reordered_ids) + 1)
        for row_idx, manager_id in enumerate(reordered_ids):
            values = row_map[manager_id]
            for col_idx, value in enumerate(values):
                if col_idx == 0:
                    self._set_cell(row_idx, col_idx, value, editable=False, account_manager_id=manager_id)
                else:
                    self._set_cell(row_idx, col_idx, value)
        self._render_summary_row()
        self._suppress_item_changed = False
        self._apply_table_column_layout()
        self._focus_first_empty_cell(start_edit=False)

        QMessageBox.information(self, "提示", "已按昨日名单顺序重排")

    def on_refresh_summary(self) -> None:
        self._refresh_summary_row()

    def _scale(self, value: int, floor: int) -> int:
        factor = float(self.window().property("_view_scale_factor") or 1.0) if self.window() is not None else 1.0
        return max(floor, int(round(float(value) * factor)))

    def _mode_width_factor(self) -> float:
        if self._layout_profile is None:
            return 1.0
        mode = self._layout_profile.mode
        if mode == "wide":
            return 1.0
        if mode == "standard":
            return 0.94
        return 0.88

    def _apply_table_column_layout(self) -> None:
        header = self.table.horizontalHeader()
        width_factor = self._mode_width_factor()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setStretchLastSection(False)
        header.setTextElideMode(Qt.ElideNone)
        header.setSectionsMovable(True)

        max_lines = 1
        self._suppress_header_state_save = True
        try:
            for col, cfg in enumerate(self.COLUMN_CONFIGS):
                min_width = self._scale(cfg.min_width, 64)
                preferred_width = self._scale(int(round(cfg.preferred_width * width_factor)), min_width)
                final_width = max(min_width, preferred_width)
                if not self._using_saved_header_state:
                    self.table.setColumnWidth(col, final_width)
                elif self.table.columnWidth(col) < min_width:
                    self.table.setColumnWidth(col, min_width)
                max_lines = max(max_lines, int(cfg.display_name.count("\n")) + 1)
        finally:
            self._suppress_header_state_save = False

        line_px = max(12, int(self.table.fontMetrics().lineSpacing()))
        base_header_height = self._scale(28, 24)
        header_height = max(base_header_height, max_lines * line_px + self._scale(12, 8))
        header.setFixedHeight(header_height)

    def _is_empty_for_entry(self, row: int, col: int) -> bool:
        value = self._cell_text(row, col)
        if col in self.AMOUNT_COLS:
            return value in {"", "0", "0.0", "0.00"}
        if col in self.INT_COLS:
            return value in {"", "0"}
        return value == ""

    def _focus_cell(self, row: int, col: int, start_edit: bool = False) -> None:
        if row < 0 or col < 0:
            return
        if row >= self._data_row_count():
            return
        item = self.table.item(row, col)
        if item is None:
            return
        self.table.setCurrentCell(row, col)
        self.table.scrollToItem(item)
        self.table.setFocus()
        if start_edit:
            self.table.editItem(item)

    def _focus_first_empty_cell(self, start_edit: bool = False) -> None:
        data_rows = self._data_row_count()
        if data_rows <= 0:
            return

        scan_cols = list(self.PRIMARY_ENTRY_COLS)
        for col in self.EDITABLE_COLS:
            if col not in scan_cols:
                scan_cols.append(col)

        for row in range(data_rows):
            for col in scan_cols:
                if not self._is_editable_cell(row, col):
                    continue
                if self._is_empty_for_entry(row, col):
                    self._focus_cell(row, col, start_edit=start_edit)
                    return

        fallback_col = next((c for c in scan_cols if self._is_editable_cell(0, c)), 1)
        self._focus_cell(0, fallback_col, start_edit=start_edit)

    def apply_layout_profile(self, profile: LayoutProfile) -> None:
        self._layout_profile = profile
        metrics = profile.metrics

        page_margin = self._scale(metrics.page_margin, 4)
        section_margin = self._scale(metrics.section_margin, 4)
        page_spacing = self._scale(metrics.page_spacing, 4)
        section_spacing = self._scale(metrics.section_spacing, 3)

        self.page_layout.setContentsMargins(page_margin, page_margin, page_margin, page_margin)
        self.page_layout.setSpacing(page_spacing)
        self.info_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.info_grid.setHorizontalSpacing(section_spacing)
        self.info_grid.setVerticalSpacing(max(2, section_spacing - 1))
        self.summary_grid.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
        self.summary_grid.setHorizontalSpacing(section_spacing)
        self.summary_grid.setVerticalSpacing(max(2, section_spacing - 1))
        for card in self.summary_cards:
            card.setMinimumHeight(self._scale(max(42, metrics.kpi_card_height - 10), 40))

        control_h = self._scale(metrics.control_height, 22)
        for widget in [self.date_edit, self.team_combo]:
            widget.setMinimumHeight(control_h)

        btn_h = self._scale(metrics.button_height, 26)
        for btn in [
            self.save_btn,
            self.submit_btn,
            self.reset_btn,
            self.clear_zero_btn,
            self.copy_yesterday_btn,
            self.refresh_summary_btn,
        ]:
            btn.setMinimumHeight(btn_h)

        top_height = self._scale(metrics.entry_top_height, 140)
        self.info_group.setMaximumHeight(top_height)
        self.summary_group.setMaximumHeight(top_height)
        self.main_splitter.setSizes([top_height + 12, self._scale(780, 460)])

        self.table.verticalHeader().setDefaultSectionSize(self._scale(metrics.table_row_height, 22))
        self.table.horizontalHeader().setMinimumHeight(self._scale(metrics.table_header_height, 24))
        self._apply_table_column_layout()

    def apply_view_scale(self, factor: float) -> None:
        # 统一缩放后重新应用当前档位，避免固定高度与缩放冲突
        if self._layout_profile is not None:
            self.apply_layout_profile(self._layout_profile)
            return
        row_height = max(22, int(round(30 * factor)))
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self._apply_table_column_layout()
