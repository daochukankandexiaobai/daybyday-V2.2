from __future__ import annotations

import uuid
from datetime import datetime

from app.config.field_rules import CONFIGURED_JSON_EXPORT_FIELD_KEYS
from app.utils.date_utils import cycle_week_for_date, parse_date, settlement_cycle_display_code, settlement_cycle_for_date
from app.utils.file_utils import ensure_dir, sanitize_component
from app.utils.json_utils import save_json_file
from app.utils.log_utils import get_logger


class ExportService:
    """JSON 导出服务。"""

    def __init__(
        self,
        record_service,
        team_service,
        settings_service,
        template_service,
        target_alert_service=None,
        star_customer_alert_service=None,
    ) -> None:
        self.logger = get_logger("export_service")
        self.record_service = record_service
        self.team_service = team_service
        self.settings_service = settings_service
        self.template_service = template_service
        self.target_alert_service = target_alert_service
        self.star_customer_alert_service = star_customer_alert_service

    def export_json(
        self,
        mode: str,
        team_id: int,
        base_date: str,
        custom_start: str,
        custom_end: str,
        output_dir: str,
    ) -> tuple[bool, str, str | None]:
        team = self.team_service.get_team(team_id)
        if team is None:
            return False, "团队不存在", None

        dataset = self.record_service.build_report(
            mode=mode,
            base_date=base_date,
            team_id=team_id,
            custom_start=custom_start,
            custom_end=custom_end,
        )
        rows = dataset["rows"]
        if not rows:
            return False, "没有可导出的记录", None

        export_id = str(uuid.uuid4())
        template_version = self.template_service.get_active_template_version()
        app_version = self.settings_service.get("app_version", "1.0.0")

        start_date = dataset["start_date"]
        end_date = dataset["end_date"]
        cycle = settlement_cycle_for_date(parse_date(base_date))
        cycle_code = settlement_cycle_display_code(record_date=base_date)
        cycle_tag = self._build_filename_cycle_tag(dataset.get("cycle_codes", []), cycle_code)
        alert_payload = self._build_alert_payload(
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
            cross_cycle=bool(dataset["cross_cycle"]),
        )

        payload = {
            "metadata": {
                "app_name": "TeamReportApp",
                "app_version": app_version,
                "template_version": template_version,
            },
            "export_info": {
                "export_id": export_id,
                "export_mode": mode,
                "team_id": int(team["id"]),
                "region": team["region"],
                "team_name": team["team_name"],
                "team_manager_name": team["team_manager_name"],
                "start_date": start_date,
                "end_date": end_date,
                "export_time": datetime.now().isoformat(timespec="seconds"),
            },
            "settlement_cycle_info": {
                "cycle_code": cycle_code,
                "cycle_start": cycle.start.isoformat(),
                "cycle_end": cycle.end_inclusive.isoformat(),
                "cross_cycle": bool(dataset["cross_cycle"]),
                "cycle_codes_in_range": dataset["cycle_codes"],
            },
            "records": [self._record_for_export(item) for item in rows],
            "summary": dataset["summary"],
            "alert_summary": alert_payload.get("alert_summary", {}),
            "alert_extensions": alert_payload.get("alert_extensions", []),
        }

        save_dir = output_dir.strip() or self.settings_service.get("default_export_dir", "") or "exports"
        try:
            target_dir = ensure_dir(save_dir)
            file_name = self._build_filename(
                mode=mode,
                team=team,
                base_date=base_date,
                cycle_code=cycle_tag,
                start_date=start_date,
                end_date=end_date,
            )
            file_path = target_dir / file_name
            save_json_file(file_path, payload)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception(
                "JSON导出失败 team_id=%s mode=%s base_date=%s start=%s end=%s output_dir=%s",
                team_id,
                mode,
                base_date,
                start_date,
                end_date,
                save_dir,
            )
            return False, f"导出失败: {exc}", None

        self.logger.info(
            "JSON导出成功 team_id=%s mode=%s range=%s~%s file=%s",
            team_id,
            mode,
            start_date,
            end_date,
            file_path,
        )
        return True, "导出成功", str(file_path)
    @staticmethod
    def _build_filename_cycle_tag(cycle_codes: list[str], fallback_cycle_code: str) -> str:
        normalized = [sanitize_component(str(code or "")) for code in cycle_codes if str(code or "").strip()]
        if not normalized:
            return sanitize_component(fallback_cycle_code)
        if len(normalized) == 1:
            return normalized[0]
        return f"{normalized[0]}_to_{normalized[-1]}"

    def _build_filename(
        self,
        mode: str,
        team: dict,
        base_date: str,
        cycle_code: str,
        start_date: str,
        end_date: str,
    ) -> str:
        region = sanitize_component(team.get("region", ""))
        team_name = sanitize_component(team.get("team_name", ""))
        manager = sanitize_component(team.get("team_manager_name", ""))
        cycle_part = sanitize_component(cycle_code)

        normalized_mode = (mode or "").strip()
        is_week = normalized_mode in {"周报", "某周", "week", "weekly"}
        is_month = normalized_mode in {"月报", "某月", "month", "monthly"}
        is_day = normalized_mode in {"某日", "某天", "日报", "day", "daily"}

        if is_week:
            week_info = cycle_week_for_date(parse_date(base_date))
            week_name = sanitize_component(f"第{week_info['week_index']}周")
            return f"周报_{region}_{team_name}_{manager}_{cycle_part}_{week_name}_{start_date}_{end_date}.json"
        if is_month:
            return f"月报_{region}_{team_name}_{manager}_{cycle_part}_{start_date}_{end_date}.json"
        if is_day:
            return f"日报_{region}_{team_name}_{manager}_{cycle_part}_{start_date}.json"
        return f"区间报_{region}_{team_name}_{manager}_{cycle_part}_{start_date}_{end_date}.json"

    def _build_alert_payload(
        self,
        *,
        mode: str,
        start_date: str,
        end_date: str,
        rows: list[dict],
        cross_cycle: bool,
    ) -> dict:
        if self.target_alert_service is None or self.star_customer_alert_service is None:
            return {"alert_summary": {}, "alert_extensions": []}

        grouped_rows = self._group_rows_for_alert_export(rows)
        if not grouped_rows:
            return {"alert_summary": {}, "alert_extensions": []}

        period_type = self._alert_period_type(mode, start_date, end_date, cross_cycle)
        target_alerts = {}
        if period_type:
            target_alerts = self.target_alert_service.get_query_alerts(
                period_type=period_type,
                start_date=start_date,
                end_date=end_date,
                rows=grouped_rows,
            )

        star_alerts = self._star_alerts_for_rows(grouped_rows, start_date, end_date)
        return {
            "alert_summary": self.target_alert_service.summarize_alerts(target_alerts, star_alerts),
            "alert_extensions": self.target_alert_service.build_alert_extension_rows(
                grouped_rows,
                target_alerts,
                star_alerts,
            ),
        }

    @staticmethod
    def _group_rows_for_alert_export(rows: list[dict]) -> list[dict]:
        grouped: dict[tuple[int, int], dict] = {}
        for row in rows:
            team_id = int(row.get("team_id", 0) or 0)
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if team_id <= 0 or manager_id <= 0:
                continue
            key = (team_id, manager_id)
            item = grouped.setdefault(
                key,
                {
                    "team_id": team_id,
                    "team_name": row.get("team_name_snapshot", ""),
                    "account_manager_id": manager_id,
                    "account_manager_name": row.get("account_manager_name_snapshot", ""),
                    "visit_count": 0,
                    "quality_visit_count": 0,
                    "repayment_amount": 0.0,
                },
            )
            item["visit_count"] += int(row.get("visit_count_daily", 0) or 0)
            item["quality_visit_count"] += int(row.get("quality_visit_count_daily", 0) or 0)
            item["repayment_amount"] += float(row.get("repayment_amount_daily", 0) or 0)
        return sorted(grouped.values(), key=lambda item: (str(item.get("team_name", "")), str(item.get("account_manager_name", ""))))

    @staticmethod
    def _alert_period_type(mode: str, start_date: str, end_date: str, cross_cycle: bool) -> str:
        if cross_cycle:
            return ""

        normalized = str(mode or "").strip()
        if normalized in {"某日", "某天", "日报", "day", "daily"}:
            return "day"
        if normalized in {"周报", "某周", "week", "weekly"}:
            return "week"
        if normalized in {"月报", "某月", "month", "monthly"}:
            return "cycle"
        if start_date == end_date:
            return "day"

        start_obj = parse_date(start_date)
        week = cycle_week_for_date(start_obj)
        if str(week.get("week_start", "")) == start_date and str(week.get("week_end", "")) == end_date:
            return "week"

        cycle = settlement_cycle_for_date(start_obj)
        if cycle.start.isoformat() == start_date and cycle.end_inclusive.isoformat() == end_date:
            return "cycle"
        return ""

    def _star_alerts_for_rows(self, rows: list[dict], start_date: str, end_date: str) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for row in rows:
            team_id = int(row.get("team_id", 0) or 0)
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if team_id <= 0 or manager_id <= 0:
                continue
            row_key = self.target_alert_service.row_key(team_id, manager_id)
            result[row_key] = self.star_customer_alert_service.get_star_alert_status_for_range(
                team_id=team_id,
                account_manager_id=manager_id,
                start_date=start_date,
                end_date=end_date,
            )
        return result

    @staticmethod
    def _record_for_export(record: dict) -> dict:
        payload = {key: record.get(key) for key in CONFIGURED_JSON_EXPORT_FIELD_KEYS}
        record_date = str(payload.get("record_date", "") or "").strip()
        if record_date:
            payload["settlement_cycle_code"] = settlement_cycle_display_code(record_date=record_date)
        else:
            payload["settlement_cycle_code"] = settlement_cycle_display_code(
                cycle_code=str(payload.get("settlement_cycle_code", "")),
            )
        return payload
