from __future__ import annotations

from pathlib import Path

from app.config.field_profiles import PROFILE_PREVIEW_TABLE, get_profile_field_keys
from app.config.field_registry import DATA_TYPE_AMOUNT, DATA_TYPE_INT, DATA_TYPE_PERCENT, get_field_spec
from app.utils.qt_compat import QDate, Qt
from app.utils.qt_compat import QColor, QFont
from app.utils.qt_compat import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.date_utils import settlement_cycle_display_code
from app.utils.format_utils import format_int, format_money, format_percent
from app.utils.log_utils import get_logger


class PreviewTab(QWidget):
    DEFAULT_FIELD_KEYS = list(get_profile_field_keys(PROFILE_PREVIEW_TABLE))
    DEFAULT_HEADERS: list[str] = [get_field_spec(key).label for key in DEFAULT_FIELD_KEYS]
    SUMMARY_LABEL = "团队汇总"

    def __init__(
        self,
        record_service,
        team_service,
        settings_service,
        report_image_service,
        target_alert_service=None,
        star_customer_alert_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record_service = record_service
        self.team_service = team_service
        self.settings_service = settings_service
        self.report_image_service = report_image_service
        self.target_alert_service = target_alert_service
        self.star_customer_alert_service = star_customer_alert_service

        self.logger = get_logger("preview_tab")

        self.field_definitions = self._load_field_definitions()
        self.field_keys = [str(row.get("field_key", "")) for row in self.field_definitions]
        self.headers = [str(row.get("label", "")) for row in self.field_definitions]
        self._field_def_map = {str(row.get("field_key", "")): row for row in self.field_definitions}

        self._current_cycle_code = ""
        self._current_render_rows: list[list[str]] = []
        self._current_cell_styles: list[list[dict]] = []
        self._current_alert_summary: list[str] = []

        self._build_ui()
        self.reload_teams()

    def _load_field_definitions(self) -> list[dict]:
        getter = getattr(self.record_service, "get_today_display_field_definitions", None)
        if callable(getter):
            rows = getter()
            if rows:
                return rows
        return [
            {
                "field_key": field_key,
                "label": get_field_spec(field_key).label,
                "data_type": get_field_spec(field_key).data_type,
            }
            for field_key in self.DEFAULT_FIELD_KEYS
        ]

    def reload_field_config(self) -> None:
        self.field_definitions = self._load_field_definitions()
        self.field_keys = [str(row.get("field_key", "")) for row in self.field_definitions]
        self.headers = [str(row.get("label", "")) for row in self.field_definitions]
        self._field_def_map = {str(row.get("field_key", "")): row for row in self.field_definitions}
        self.table.clear()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.toolbar_panel = QWidget()
        self.toolbar_panel.setObjectName("toolbarPanel")
        tools = QHBoxLayout(self.toolbar_panel)
        tools.setContentsMargins(8, 6, 8, 6)
        tools.setSpacing(6)
        self.team_combo = QComboBox()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())

        self.query_btn = QPushButton("查询")
        self.query_btn.setProperty("buttonRole", "primary")
        self.today_btn = QPushButton("今天")
        self.today_btn.setProperty("buttonRole", "secondary")
        self.export_png_btn = QPushButton("导出PNG总图")
        self.export_png_btn.setProperty("buttonRole", "primary")
        self.screenshot_mode = QCheckBox("截图友好模式")
        self.cycle_label = QLabel("结算周期：")
        self.cycle_label.setObjectName("statusText")

        tools.addWidget(QLabel("团队"))
        tools.addWidget(self.team_combo)
        tools.addWidget(QLabel("日期"))
        tools.addWidget(self.date_edit)
        tools.addWidget(self.query_btn)
        tools.addWidget(self.today_btn)
        tools.addWidget(self.export_png_btn)
        tools.addWidget(self.screenshot_mode)
        tools.addWidget(self.cycle_label)
        tools.addStretch()

        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)

        root.addWidget(self.toolbar_panel)
        root.addWidget(self.table)

        self.query_btn.clicked.connect(self.refresh)
        self.today_btn.clicked.connect(self.on_today)
        self.export_png_btn.clicked.connect(self.on_export_png_bundle)
        self.screenshot_mode.toggled.connect(self.apply_screenshot_style)
        self.team_combo.currentIndexChanged.connect(self.refresh)

    def _current_team_id(self) -> int:
        return int(self.team_combo.currentData() or 0)

    def reload_teams(self) -> None:
        teams = self.team_service.list_teams()
        self.team_combo.clear()
        for team in teams:
            label = f"{team['region']} / {team['team_name']}"
            self.team_combo.addItem(label, int(team["id"]))

        if self.team_combo.count() > 0:
            self.team_combo.setEnabled(True)
            team_id = self.team_service.get_current_team_id()
            idx = 0
            for i in range(self.team_combo.count()):
                if int(self.team_combo.itemData(i) or 0) == team_id:
                    idx = i
                    break
            self.team_combo.setCurrentIndex(idx)
        else:
            self.team_combo.setEnabled(False)
        self.refresh()

    def apply_screenshot_style(self, enabled: bool) -> None:
        if enabled:
            self.table.setStyleSheet(
                """
                QTableWidget {
                    font-size: 16px;
                    background: #ffffff;
                    alternate-background-color: #f1f5f9;
                    color: #1a1a1a;
                    gridline-color: #9aa4b2;
                }
                QHeaderView::section {
                    background: #7A111A;
                    color: #ffffff;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 8px;
                    border: 1px solid #aeb8c2;
                }
                """
            )
            self.table.verticalHeader().setDefaultSectionSize(36)
            self.table.horizontalHeader().setMinimumHeight(38)
        else:
            self.table.setStyleSheet("")
            self.table.verticalHeader().setDefaultSectionSize(28)
            self.table.horizontalHeader().setMinimumHeight(32)

    def on_today(self) -> None:
        self.date_edit.setDate(QDate.currentDate())
        self.refresh()

    def _field_data_type(self, field_key: str) -> str:
        field_def = self._field_def_map.get(field_key, {})
        data_type = str(field_def.get("data_type", "") or "")
        if data_type:
            return data_type
        return get_field_spec(field_key).data_type

    def _format_field_value(self, field_key: str, row: dict) -> str:
        data_type = self._field_data_type(field_key)
        value = row.get(field_key)
        if data_type == DATA_TYPE_AMOUNT:
            return format_money(value)
        if data_type == DATA_TYPE_INT:
            return format_int(value)
        if data_type == DATA_TYPE_PERCENT:
            return format_percent(value)
        return str(value or "")

    def _build_row_values(self, row: dict) -> list[str]:
        return [self._format_field_value(field_key, row) for field_key in self.field_keys]

    def _build_summary_row(self, rows: list[dict], record_date: str) -> dict:
        return self.record_service.build_today_display_summary_row(
            rows,
            record_date,
            summary_label=self.SUMMARY_LABEL,
        )

    def _apply_summary_row_style(self, row_index: int) -> None:
        bg = QColor("#7A111A")
        fg = QColor("#FFFFFF")
        for col in range(self.table.columnCount()):
            item = self.table.item(row_index, col)
            if item is None:
                continue
            font = QFont(item.font())
            font.setBold(True)
            item.setFont(font)
            item.setData(Qt.BackgroundRole, bg)
            item.setData(Qt.ForegroundRole, fg)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    @staticmethod
    def _status_color(status_code: str) -> QColor | None:
        colors = {
            "lagging": QColor("#FDE2E2"),
            "warning": QColor("#FFF4CC"),
            "ok": QColor("#DCFCE7"),
            "excellent": QColor("#CCFBF1"),
        }
        return colors.get(str(status_code or ""))

    @staticmethod
    def _status_label(status_code: str) -> str:
        labels = {
            "lagging": "落后",
            "warning": "预警",
            "ok": "达标",
            "excellent": "超常",
            "no_target": "未设置目标",
        }
        return labels.get(str(status_code or ""), str(status_code or ""))

    def _build_star_alert_map(self, team_id: int, rows: list[dict], record_date: str) -> dict[str, dict]:
        if self.star_customer_alert_service is None:
            return {}
        result: dict[str, dict] = {}
        for row in rows:
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if manager_id <= 0:
                continue
            status = self.star_customer_alert_service.get_star_alert_status_for_date(
                team_id=team_id,
                account_manager_id=manager_id,
                record_date=record_date,
            )
            result[f"{team_id}:{manager_id}"] = status
        return result

    def _apply_alert_style(
        self,
        item: QTableWidgetItem,
        field_key: str,
        row: dict,
        target_alerts: dict[str, dict[str, dict]],
        star_alerts: dict[str, dict],
    ) -> None:
        if row.get("is_summary_row"):
            return

        team_id = int(row.get("team_id", self._current_team_id()) or 0)
        manager_id = int(row.get("account_manager_id", 0) or 0)
        row_key = f"{team_id}:{manager_id}"

        status = target_alerts.get(row_key, {}).get(field_key)
        if status:
            status_code = str(status.get("status_code", ""))
            color = self._status_color(status_code)
            if color is not None:
                item.setData(Qt.BackgroundRole, color)
                item.setToolTip(
                    f"目标进度：{self._status_label(status_code)}\n"
                    f"完成率：{format_percent(status.get('completion_rate'))}\n"
                    f"时间进度：{format_percent(status.get('time_progress'))}"
                )
                return

        star_status = star_alerts.get(row_key, {})
        if field_key == "four_star_customer_count_daily" and star_status.get("four_star_alert"):
            item.setData(Qt.BackgroundRole, QColor("#FFE4E6"))
            item.setToolTip("四星客户数连续三工作日未达标，已触发预警")
        elif field_key == "five_star_customer_count_daily" and star_status.get("five_star_alert"):
            item.setData(Qt.BackgroundRole, QColor("#FFE4E6"))
            item.setToolTip("五星客户数连续三工作日未达标，已触发预警")

    def _build_export_cell_style(
        self,
        field_key: str,
        row: dict,
        target_alerts: dict[str, dict[str, dict]],
        star_alerts: dict[str, dict],
    ) -> dict:
        if row.get("is_summary_row"):
            return {}

        team_id = int(row.get("team_id", self._current_team_id()) or 0)
        manager_id = int(row.get("account_manager_id", 0) or 0)
        row_key = f"{team_id}:{manager_id}"

        status = target_alerts.get(row_key, {}).get(field_key)
        if status:
            color = self._status_color(str(status.get("status_code", "")))
            if color is not None:
                return {"background": color.name()}

        star_status = star_alerts.get(row_key, {})
        if field_key == "four_star_customer_count_daily" and star_status.get("four_star_alert"):
            return {"background": "#FFE4E6"}
        if field_key == "five_star_customer_count_daily" and star_status.get("five_star_alert"):
            return {"background": "#FFE4E6"}
        return {}

    def refresh(self) -> None:
        team_id = self._current_team_id()
        if team_id <= 0:
            self.table.setRowCount(0)
            self._current_cycle_code = ""
            self._current_render_rows = []
            self._current_cell_styles = []
            self._current_alert_summary = []
            self.cycle_label.setText("结算周期：")
            return

        self.team_service.set_current_team_id(team_id)
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        rows = self.record_service.get_preview_rows(team_id, record_date)
        render_rows = list(rows)
        render_rows.append(self._build_summary_row(rows, record_date))
        manager_ids = sorted({int(row.get("account_manager_id", 0) or 0) for row in rows if int(row.get("account_manager_id", 0) or 0) > 0})
        target_alerts = {}
        if self.target_alert_service is not None:
            target_alerts = self.target_alert_service.get_daily_alerts(team_id, record_date, manager_ids)
        star_alerts = self._build_star_alert_map(team_id, rows, record_date)
        if self.target_alert_service is not None:
            self._current_alert_summary = list(
                self.target_alert_service.summarize_alerts(target_alerts, star_alerts).get("lines", [])
            )
        else:
            self._current_alert_summary = []

        self.table.setRowCount(len(render_rows))
        self._current_render_rows = []
        self._current_cell_styles = []

        cycle_code = rows[0].get("settlement_cycle_code", "") if rows else settlement_cycle_display_code(record_date=record_date)
        self._current_cycle_code = str(cycle_code or "")
        self.cycle_label.setText(f"结算周期：{self._current_cycle_code or '-'}")

        summary_row_idx = len(render_rows) - 1
        for row_idx, row in enumerate(render_rows):
            values = self._build_row_values(row)
            self._current_render_rows.append(values)
            row_styles: list[dict] = []
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                field_key = self.field_keys[col_idx]
                row_styles.append(self._build_export_cell_style(field_key, row, target_alerts, star_alerts))
                if field_key == "account_manager_name":
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                elif field_key == "record_date":
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._apply_alert_style(item, field_key, row, target_alerts, star_alerts)
                self.table.setItem(row_idx, col_idx, item)
            self._current_cell_styles.append(row_styles)
            if row_idx == summary_row_idx:
                self._apply_summary_row_style(row_idx)

        self.table.resizeColumnsToContents()

    def apply_view_scale(self, factor: float) -> None:
        row_height = max(22, int(round(30 * factor)))
        header_height = max(24, int(round(34 * factor)))
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.table.horizontalHeader().setMinimumHeight(header_height)

    def _resolve_image_output_dir(self) -> Path:
        raw = self.settings_service.get("default_export_dir", "").strip()
        if raw:
            return Path(raw) / "images"
        return Path.cwd() / "exports" / "images"

    def on_export_png_bundle(self) -> None:
        team_id = self._current_team_id()
        if team_id <= 0:
            QMessageBox.warning(self, "提示", "请先选择团队")
            return

        if not self._current_render_rows:
            # 允许空表导出会生成只有表头的图片，这里沿用当前页面体验：无数据直接提示。
            QMessageBox.warning(self, "提示", "当前没有可导出的今日展示数据")
            return

        team = self.team_service.get_team(team_id) or {}
        region = str(team.get("region", ""))
        team_name = str(team.get("team_name", ""))
        team_manager_name = str(team.get("team_manager_name", ""))
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        cycle_code = self._current_cycle_code or settlement_cycle_display_code(record_date=record_date)

        try:
            result = self.report_image_service.export_today_preview_bundle(
                output_dir=self._resolve_image_output_dir(),
                record_date=record_date,
                settlement_cycle_code=cycle_code,
                region=region,
                team_name=team_name,
                team_manager_name=team_manager_name,
                headers=self.headers,
                rows=self._current_render_rows,
                field_keys=self.field_keys,
                cell_styles=self._current_cell_styles,
                alert_summary=self._current_alert_summary,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception(
                "今日展示PNG导出失败 team_id=%s date=%s cycle=%s",
                team_id,
                record_date,
                cycle_code,
            )
            QMessageBox.warning(self, "导出失败", f"导出PNG总图失败：{exc}")
            return

        output_dir = str(result.get("output_dir", ""))
        total_path = Path(str(result.get("total_path", "")))
        part_paths = result.get("part_paths", [])

        QMessageBox.information(
            self,
            "导出成功",
            "\n".join(
                [
                    "已生成 4 张分图 + 1 张总图。",
                    f"保存目录：{output_dir}",
                    f"总图文件：{total_path.name}",
                    f"分图数量：{len(part_paths)}",
                ]
            ),
        )
