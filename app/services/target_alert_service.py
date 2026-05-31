from __future__ import annotations

from typing import Any

from app.utils.date_utils import cycle_week_for_date, parse_date, settlement_cycle_for_date


class TargetAlertService:
    STATUS_LABELS = {
        "lagging": "落后",
        "warning": "预警",
        "ok": "达标",
        "excellent": "超常",
        "no_target": "未设置目标",
    }
    SUMMARY_ORDER = ("lagging", "warning", "ok", "excellent")
    WORST_STATUS_ORDER = {"lagging": 0, "warning": 1, "ok": 2, "excellent": 3}

    DAILY_FIELD_MAP = {
        "visit_count_daily": ("visit_target", "visit_count_daily"),
        "quality_visit_count_daily": ("quality_visit_target", "quality_visit_count_daily"),
        "repayment_amount_daily": ("repayment_target", "repayment_amount_daily"),
    }
    SUMMARY_FIELD_MAP = {
        "visit_count": ("visit_target", "visit_count_daily"),
        "quality_visit_count": ("quality_visit_target", "quality_visit_count_daily"),
        "repayment_amount": ("repayment_target", "repayment_amount_daily"),
    }

    def __init__(self, record_repo, weekly_target_service, target_progress_service) -> None:
        self.record_repo = record_repo
        self.weekly_target_service = weekly_target_service
        self.target_progress_service = target_progress_service

    @staticmethod
    def row_key(team_id: int, account_manager_id: int) -> str:
        return f"{int(team_id or 0)}:{int(account_manager_id or 0)}"

    def get_daily_alerts(
        self,
        team_id: int,
        record_date: str,
        account_manager_ids: list[int],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        week = cycle_week_for_date(parse_date(record_date))
        cycle_code = str(week.get("cycle_code", ""))
        week_index = int(week.get("week_index", 0) or 0)
        week_start = str(week.get("week_start", ""))
        week_end = str(week.get("week_end", ""))
        target_map = self._weekly_targets_for_team(team_id, cycle_code)

        result: dict[str, dict[str, dict[str, Any]]] = {}
        for manager_id in account_manager_ids:
            actuals = self._sum_actuals(team_id, manager_id, week_start, record_date)
            week_targets = target_map.get(int(manager_id or 0), {}).get("weeks", {}).get(week_index, {})
            statuses: dict[str, dict[str, Any]] = {}
            for field_key, (target_key, actual_key) in self.DAILY_FIELD_MAP.items():
                statuses[field_key] = self.target_progress_service.calc_daily_target_status(
                    actual_to_date=actuals.get(actual_key, 0),
                    week_target=week_targets.get(target_key, 0),
                    week_start_date=week_start,
                    week_end_date=week_end,
                    current_date=record_date,
                )
            result[self.row_key(team_id, manager_id)] = statuses
        return result

    def get_query_alerts(
        self,
        period_type: str,
        start_date: str,
        end_date: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        period_type = str(period_type or "").strip()
        if period_type not in {"day", "week", "cycle"}:
            return {}
        if period_type == "day":
            return self._get_query_day_alerts(end_date, rows)
        if period_type == "week":
            return self._get_query_week_alerts(start_date, end_date, rows)
        return self._get_query_cycle_alerts(start_date, rows)

    def status_label(self, status_code: str) -> str:
        return self.STATUS_LABELS.get(str(status_code or ""), str(status_code or ""))

    def summarize_alerts(
        self,
        target_alerts: dict[str, dict[str, dict[str, Any]]],
        star_alerts: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        target_counts = {key: 0 for key in self.SUMMARY_ORDER}
        all_row_keys = set(target_alerts.keys()) | set(star_alerts.keys())
        for row_key in all_row_keys:
            status_code = self._worst_target_status(target_alerts.get(row_key, {}))
            if status_code in target_counts:
                target_counts[status_code] += 1

        four_star_count = sum(1 for item in star_alerts.values() if item.get("four_star_alert"))
        five_star_count = sum(1 for item in star_alerts.values() if item.get("five_star_alert"))
        lines = [
            f"目标落后人数：{target_counts['lagging']}",
            f"目标预警人数：{target_counts['warning']}",
            f"目标达标人数：{target_counts['ok']}",
            f"目标超常人数：{target_counts['excellent']}",
            f"四星连续三工作日未达标人数：{four_star_count}人",
            f"五星连续三工作日未达标人数：{five_star_count}人",
        ]
        return {
            "target_lagging_count": target_counts["lagging"],
            "target_warning_count": target_counts["warning"],
            "target_ok_count": target_counts["ok"],
            "target_excellent_count": target_counts["excellent"],
            "four_star_low_streak_count": four_star_count,
            "five_star_low_streak_count": five_star_count,
            "lines": lines,
        }

    def build_alert_extension_rows(
        self,
        rows: list[dict[str, Any]],
        target_alerts: dict[str, dict[str, dict[str, Any]]],
        star_alerts: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            team_id = int(row.get("team_id", 0) or 0)
            account_manager_id = int(row.get("account_manager_id", 0) or 0)
            row_key = self.row_key(team_id, account_manager_id)
            statuses = target_alerts.get(row_key, {})
            star_status = star_alerts.get(row_key, {})
            visit_status = statuses.get("visit_count") or statuses.get("visit_count_daily") or {}
            quality_status = statuses.get("quality_visit_count") or statuses.get("quality_visit_count_daily") or {}
            repayment_status = statuses.get("repayment_amount") or statuses.get("repayment_amount_daily") or {}
            result.append(
                {
                    "team_id": team_id,
                    "team_name": row.get("team_name") or row.get("team_name_snapshot") or "",
                    "account_manager_id": account_manager_id,
                    "account_manager_name": row.get("account_manager_name") or row.get("account_manager_name_snapshot") or "",
                    "visit_target": visit_status.get("target"),
                    "visit_completion_rate": visit_status.get("completion_rate"),
                    "visit_status": self.status_label(str(visit_status.get("status_code", ""))),
                    "quality_visit_target": quality_status.get("target"),
                    "quality_visit_completion_rate": quality_status.get("completion_rate"),
                    "quality_visit_status": self.status_label(str(quality_status.get("status_code", ""))),
                    "repayment_target": repayment_status.get("target"),
                    "repayment_completion_rate": repayment_status.get("completion_rate"),
                    "repayment_status": self.status_label(str(repayment_status.get("status_code", ""))),
                    "four_star_low_streak_alert": bool(star_status.get("four_star_alert", False)),
                    "five_star_low_streak_alert": bool(star_status.get("five_star_alert", False)),
                }
            )
        return result

    def _worst_target_status(self, statuses: dict[str, dict[str, Any]]) -> str:
        ranked: list[tuple[int, str]] = []
        for status in statuses.values():
            status_code = str(status.get("status_code", ""))
            if status_code in self.WORST_STATUS_ORDER:
                ranked.append((self.WORST_STATUS_ORDER[status_code], status_code))
        if not ranked:
            return ""
        ranked.sort(key=lambda item: item[0])
        return ranked[0][1]

    def _get_query_day_alerts(
        self,
        record_date: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        grouped: dict[int, list[int]] = {}
        for row in rows:
            team_id = int(row.get("team_id", 0) or 0)
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if team_id > 0 and manager_id > 0:
                grouped.setdefault(team_id, []).append(manager_id)

        result: dict[str, dict[str, dict[str, Any]]] = {}
        for team_id, manager_ids in grouped.items():
            daily = self.get_daily_alerts(team_id, record_date, sorted(set(manager_ids)))
            for row_key, statuses in daily.items():
                result[row_key] = {
                    "visit_count": statuses.get("visit_count_daily", {}),
                    "quality_visit_count": statuses.get("quality_visit_count_daily", {}),
                    "repayment_amount": statuses.get("repayment_amount_daily", {}),
                }
        return result

    def _get_query_week_alerts(
        self,
        start_date: str,
        end_date: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        week = cycle_week_for_date(parse_date(start_date))
        cycle_code = str(week.get("cycle_code", ""))
        week_index = int(week.get("week_index", 0) or 0)

        target_cache: dict[int, dict[int, dict[str, Any]]] = {}
        result: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            team_id = int(row.get("team_id", 0) or 0)
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if team_id <= 0 or manager_id <= 0:
                continue
            if team_id not in target_cache:
                target_cache[team_id] = self._weekly_targets_for_team(team_id, cycle_code)
            week_targets = target_cache[team_id].get(manager_id, {}).get("weeks", {}).get(week_index, {})
            statuses: dict[str, dict[str, Any]] = {}
            for field_key, (target_key, _actual_key) in self.SUMMARY_FIELD_MAP.items():
                statuses[field_key] = self.target_progress_service.calc_week_target_status(
                    actual=row.get(field_key, 0),
                    week_target=week_targets.get(target_key, 0),
                )
            result[self.row_key(team_id, manager_id)] = statuses
        return result

    def _get_query_cycle_alerts(
        self,
        start_date: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        cycle_code = settlement_cycle_for_date(parse_date(start_date)).code
        target_cache: dict[int, dict[int, dict[str, Any]]] = {}
        result: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            team_id = int(row.get("team_id", 0) or 0)
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if team_id <= 0 or manager_id <= 0:
                continue
            if team_id not in target_cache:
                target_cache[team_id] = self._weekly_targets_for_team(team_id, cycle_code)
            cycle_targets = target_cache[team_id].get(manager_id, {}).get("cycle", {})
            statuses: dict[str, dict[str, Any]] = {}
            for field_key, (target_key, _actual_key) in self.SUMMARY_FIELD_MAP.items():
                statuses[field_key] = self.target_progress_service.calc_cycle_target_status(
                    actual=row.get(field_key, 0),
                    cycle_target=cycle_targets.get(target_key, 0),
                )
            result[self.row_key(team_id, manager_id)] = statuses
        return result

    def _weekly_targets_for_team(self, team_id: int, settlement_cycle_code: str) -> dict[int, dict[str, Any]]:
        matrix = self.weekly_target_service.get_cycle_matrix_for_team(team_id, settlement_cycle_code)
        result: dict[int, dict[str, Any]] = {}
        for row in matrix.get("rows", []):
            manager_id = int(row.get("account_manager_id", 0) or 0)
            weeks: dict[int, dict[str, Any]] = {}
            for week_row in row.get("weeks", []):
                if not isinstance(week_row, dict):
                    continue
                weeks[int(week_row.get("week_index", 0) or 0)] = week_row
            result[manager_id] = {
                "weeks": weeks,
                "cycle": {
                    "visit_target": row.get("cycle_visit_target", 0),
                    "quality_visit_target": row.get("cycle_quality_visit_target", 0),
                    "repayment_target": row.get("cycle_repayment_target", 0),
                },
            }
        return result

    def _sum_actuals(self, team_id: int, account_manager_id: int, start_date: str, end_date: str) -> dict[str, float]:
        rows = self.record_repo.list_records(
            start_date=start_date,
            end_date=end_date,
            team_id=team_id,
            account_manager_id=account_manager_id,
        )
        result = {
            "visit_count_daily": 0.0,
            "quality_visit_count_daily": 0.0,
            "repayment_amount_daily": 0.0,
        }
        for row in rows:
            for key in result:
                result[key] += float(row.get(key, 0) or 0)
        return result
