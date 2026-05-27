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
from app.utils.metrics_utils import ratio_or_none


class PreviewTab(QWidget):
    FIELD_KEYS = list(get_profile_field_keys(PROFILE_PREVIEW_TABLE))
    HEADERS: list[str] = [get_field_spec(key).label for key in FIELD_KEYS]
    SUMMARY_LABEL = "团队汇总"

    def __init__(
        self,
        record_service,
        team_service,
        settings_service,
        report_image_service,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record_service = record_service
        self.team_service = team_service
        self.settings_service = settings_service
        self.report_image_service = report_image_service

        self.logger = get_logger("preview_tab")

        self._current_cycle_code = ""
        self._current_render_rows: list[list[str]] = []

        self._build_ui()
        self.reload_teams()

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

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
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

    @staticmethod
    def _format_field_value(field_key: str, row: dict) -> str:
        spec = get_field_spec(field_key)
        value = row.get(field_key)
        if spec.data_type == DATA_TYPE_AMOUNT:
            return format_money(value)
        if spec.data_type == DATA_TYPE_INT:
            return format_int(value)
        if spec.data_type == DATA_TYPE_PERCENT:
            return format_percent(value)
        return str(value or "")

    def _build_row_values(self, row: dict) -> list[str]:
        return [self._format_field_value(field_key, row) for field_key in self.FIELD_KEYS]

    def _build_summary_row(self, rows: list[dict], record_date: str) -> dict:
        cycle_target = sum(float(row.get("cycle_target", 0) or 0) for row in rows)
        repayment_amount_cumulative = sum(float(row.get("repayment_amount_cumulative", 0) or 0) for row in rows)
        loan_amount_cumulative = sum(float(row.get("loan_amount_cumulative", 0) or 0) for row in rows)
        repayment_amount_daily = sum(float(row.get("repayment_amount_daily", 0) or 0) for row in rows)
        loan_amount_daily = sum(float(row.get("loan_amount_daily", 0) or 0) for row in rows)
        intention_daily = sum(int(row.get("intention_daily", 0) or 0) for row in rows)
        wechat_count_daily = sum(int(row.get("wechat_count_daily", 0) or 0) for row in rows)
        visit_count_daily = sum(int(row.get("visit_count_daily", 0) or 0) for row in rows)
        invitation_cumulative = sum(int(row.get("invitation_cumulative", 0) or 0) for row in rows)
        invalid_visit_count_daily = sum(int(row.get("invalid_visit_count_daily", 0) or 0) for row in rows)
        four_star_customer_count_daily = sum(int(row.get("four_star_customer_count_daily", 0) or 0) for row in rows)
        five_star_customer_count_daily = sum(int(row.get("five_star_customer_count_daily", 0) or 0) for row in rows)
        signing_count_daily = sum(int(row.get("signing_count_daily", 0) or 0) for row in rows)
        signing_count_cumulative = sum(int(row.get("signing_count_cumulative", 0) or 0) for row in rows)
        quality_visit_count_daily = sum(int(row.get("quality_visit_count_daily", 0) or 0) for row in rows)
        quality_visit_count_cumulative = sum(int(row.get("quality_visit_count_cumulative", 0) or 0) for row in rows)
        approval_customer_count_daily = sum(int(row.get("approval_customer_count_daily", 0) or 0) for row in rows)
        repayment_customer_count_daily = sum(int(row.get("repayment_customer_count_daily", 0) or 0) for row in rows)
        debt_case_submit_count_daily = sum(int(row.get("debt_case_submit_count_daily", 0) or 0) for row in rows)
        debt_case_repayment_count_daily = sum(int(row.get("debt_case_repayment_count_daily", 0) or 0) for row in rows)
        debt_case_repayment_amount_daily = sum(float(row.get("debt_case_repayment_amount_daily", 0) or 0) for row in rows)
        large_order_repayment_count_daily = sum(int(row.get("large_order_repayment_count_daily", 0) or 0) for row in rows)
        large_order_repayment_amount_daily = sum(float(row.get("large_order_repayment_amount_daily", 0) or 0) for row in rows)

        return {
            "record_date": self.SUMMARY_LABEL,
            "account_manager_name": "",
            "cycle_target": cycle_target,
            "repayment_amount_cumulative": repayment_amount_cumulative,
            "loan_amount_cumulative": loan_amount_cumulative,
            "repayment_amount_daily": repayment_amount_daily,
            "target_progress": ratio_or_none(repayment_amount_cumulative, cycle_target),
            "loan_amount_daily": loan_amount_daily,
            "intention_daily": intention_daily,
            "wechat_count_daily": wechat_count_daily,
            "visit_count_daily": visit_count_daily,
            "invitation_cumulative": invitation_cumulative,
            "invalid_visit_count_daily": invalid_visit_count_daily,
            "four_star_customer_count_daily": four_star_customer_count_daily,
            "five_star_customer_count_daily": five_star_customer_count_daily,
            "signing_count_daily": signing_count_daily,
            "signing_count_cumulative": signing_count_cumulative,
            "daily_signing_rate": ratio_or_none(signing_count_daily, visit_count_daily - invalid_visit_count_daily),
            "quality_visit_count_daily": quality_visit_count_daily,
            "daily_quality_visit_rate": ratio_or_none(quality_visit_count_daily, visit_count_daily),
            "quality_visit_count_cumulative": quality_visit_count_cumulative,
            "approval_customer_count_daily": approval_customer_count_daily,
            "daily_approval_rate": ratio_or_none(approval_customer_count_daily, signing_count_daily),
            "repayment_customer_count_daily": repayment_customer_count_daily,
            "daily_sales_conversion_rate": ratio_or_none(signing_count_daily, visit_count_daily),
            "warrant_conversion_rate": ratio_or_none(repayment_customer_count_daily, signing_count_daily),
            "debt_case_submit_count_daily": debt_case_submit_count_daily,
            "debt_case_repayment_count_daily": debt_case_repayment_count_daily,
            "debt_case_repayment_amount_daily": debt_case_repayment_amount_daily,
            "large_order_repayment_count_daily": large_order_repayment_count_daily,
            "large_order_repayment_amount_daily": large_order_repayment_amount_daily,
            "is_summary_row": True,
        }

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

    def refresh(self) -> None:
        team_id = self._current_team_id()
        if team_id <= 0:
            self.table.setRowCount(0)
            self._current_cycle_code = ""
            self._current_render_rows = []
            self.cycle_label.setText("结算周期：")
            return

        self.team_service.set_current_team_id(team_id)
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        rows = self.record_service.get_preview_rows(team_id, record_date)
        render_rows = list(rows)
        render_rows.append(self._build_summary_row(rows, record_date))

        self.table.setRowCount(len(render_rows))
        self._current_render_rows = []

        cycle_code = rows[0].get("settlement_cycle_code", "") if rows else settlement_cycle_display_code(record_date=record_date)
        self._current_cycle_code = str(cycle_code or "")
        self.cycle_label.setText(f"结算周期：{self._current_cycle_code or '-'}")

        summary_row_idx = len(render_rows) - 1
        for row_idx, row in enumerate(render_rows):
            values = self._build_row_values(row)
            self._current_render_rows.append(values)
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                field_key = self.FIELD_KEYS[col_idx]
                if field_key == "account_manager_name":
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                elif field_key == "record_date":
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)
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
                headers=self.HEADERS,
                rows=self._current_render_rows,
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
