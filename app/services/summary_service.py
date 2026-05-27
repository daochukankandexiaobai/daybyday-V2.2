from __future__ import annotations

from collections import defaultdict

from app.utils.date_utils import day_end_iso, day_start_iso, parse_date, range_crosses_cycles, settlement_cycle_for_date
from app.utils.metrics_utils import aggregate_daily_rows


class SummaryService:
    """V1.0 公司汇总服务。"""

    def __init__(self, record_repo, import_log_repo, cycle_target_repo) -> None:
        self.record_repo = record_repo
        self.import_log_repo = import_log_repo
        self.cycle_target_repo = cycle_target_repo

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
            "import_logs": logs,
            "cross_cycle": crosses,
        }
