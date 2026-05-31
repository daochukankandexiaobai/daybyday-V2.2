from __future__ import annotations

from collections import defaultdict

from app.utils.date_utils import (
    cycle_week_for_date,
    day_end_iso,
    day_start_iso,
    parse_date,
    range_crosses_cycles,
    settlement_cycle_for_date,
)
from app.utils.metrics_utils import aggregate_daily_rows


class SummaryService:
    """V1.0 公司汇总服务。"""

    def __init__(
        self,
        record_repo,
        import_log_repo,
        cycle_target_repo,
        target_alert_service=None,
        star_customer_alert_service=None,
    ) -> None:
        self.record_repo = record_repo
        self.import_log_repo = import_log_repo
        self.cycle_target_repo = cycle_target_repo
        self.target_alert_service = target_alert_service
        self.star_customer_alert_service = star_customer_alert_service

    def _aggregate_rows(self, rows: list[dict], target: float = 0.0, include_progress: bool = True) -> dict:
        return aggregate_daily_rows(rows, team_target=target, include_progress=include_progress)

    def aggregate_records(self, start_date: str, end_date: str, group_by: str) -> list[dict]:
        rows = self.record_repo.list_all_records(start_date, end_date)
        if not rows:
            return []

        crosses = range_crosses_cycles(parse_date(start_date), parse_date(end_date))
        include_progress = not crosses
        cycle_code = settlement_cycle_for_date(parse_date(start_date)).code if not crosses else ""

        key_func_map = {
            "全公司": lambda x: "全公司",
            "区域": lambda x: x.get("region", ""),
            "团队": lambda x: x.get("team_name_snapshot", ""),
            "客户经理": lambda x: x.get("account_manager_name_snapshot", ""),
        }
        key_func = key_func_map.get(group_by, key_func_map["全公司"])

        buckets: dict[str, list[dict]] = defaultdict(list)
        team_id_map: dict[str, int] = {}
        for row in rows:
            key = key_func(row) or "未分组"
            buckets[key].append(row)
            if group_by == "团队":
                team_id_map[key] = int(row.get("team_id", 0) or 0)

        result: list[dict] = []
        for key, bucket in sorted(buckets.items(), key=lambda x: x[0]):
            target = 0.0
            if include_progress and group_by == "团队":
                team_id = team_id_map.get(key, 0)
                if team_id > 0:
                    target = self.cycle_target_repo.team_target_sum(team_id, cycle_code)
            agg = self._aggregate_rows(bucket, target=target, include_progress=include_progress)
            result.append({"group_name": key, "cross_cycle": crosses, **agg})

        return result

    def build_company_dataset(self, start_date: str, end_date: str) -> dict:
        rows = self.record_repo.list_all_records(start_date, end_date)
        by_account_manager = self.aggregate_records(start_date, end_date, "客户经理")
        by_team = self.aggregate_records(start_date, end_date, "团队")
        total = self.aggregate_records(start_date, end_date, "全公司")

        crosses = range_crosses_cycles(parse_date(start_date), parse_date(end_date))
        cycle_targets: list[dict] = []
        if not crosses:
            cycle_code = settlement_cycle_for_date(parse_date(start_date)).code
            team_ids = sorted({int(x.get("team_id", 0) or 0) for x in rows if int(x.get("team_id", 0) or 0) > 0})
            for team_id in team_ids:
                cycle_targets.extend(self.cycle_target_repo.list_targets(team_id, cycle_code))

        start_time = day_start_iso(parse_date(start_date))
        end_time = day_end_iso(parse_date(end_date))
        logs = self.import_log_repo.list_logs(start_time=start_time, end_time=end_time, result="")

        return {
            "raw_records": rows,
            "by_account_manager": by_account_manager,
            "by_team": by_team,
            "total_summary": total,
            "cycle_targets": cycle_targets,
            "alert_rows": self._build_alert_rows(start_date, end_date, rows, crosses),
            "import_logs": logs,
            "cross_cycle": crosses,
        }

    def _build_alert_rows(self, start_date: str, end_date: str, rows: list[dict], crosses: bool) -> list[dict]:
        if self.target_alert_service is None or self.star_customer_alert_service is None:
            return []

        grouped_rows = self._group_rows_for_alert_export(rows)
        if not grouped_rows:
            return []

        period_type = self._alert_period_type(start_date, end_date, crosses)
        target_alerts = {}
        if period_type:
            target_alerts = self.target_alert_service.get_query_alerts(
                period_type=period_type,
                start_date=start_date,
                end_date=end_date,
                rows=grouped_rows,
            )

        star_alerts = self._star_alerts_for_rows(grouped_rows, start_date, end_date)
        return self.target_alert_service.build_alert_extension_rows(grouped_rows, target_alerts, star_alerts)

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
    def _alert_period_type(start_date: str, end_date: str, crosses: bool) -> str:
        if crosses:
            return ""
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
