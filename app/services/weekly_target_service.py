from __future__ import annotations

from typing import Any

from app.utils.date_utils import (
    cycle_week_segments,
    now_iso,
    parse_date,
    settlement_cycle_for_date,
    settlement_cycle_from_code,
)
from app.utils.validators import safe_decimal, safe_int


class WeeklyTargetService:
    def __init__(
        self,
        weekly_target_repo,
        cycle_target_repo,
        team_repo,
        account_manager_repo,
    ) -> None:
        self.weekly_target_repo = weekly_target_repo
        self.cycle_target_repo = cycle_target_repo
        self.team_repo = team_repo
        self.account_manager_repo = account_manager_repo

    def get_cycle_weeks(self, settlement_cycle_code: str) -> list[dict[str, Any]]:
        cycle = settlement_cycle_from_code(str(settlement_cycle_code or "").strip())
        weeks: list[dict[str, Any]] = []
        for segment in cycle_week_segments(cycle):
            week_index = safe_int(segment.get("index"))
            weeks.append(
                {
                    "week_index": week_index,
                    "week_label": segment.get("label", ""),
                    "week_start_date": segment.get("start", ""),
                    "week_end_date": segment.get("end", ""),
                }
            )
        return weeks

    def get_cycle_weeks_by_date(self, record_date: str) -> dict[str, Any]:
        cycle = settlement_cycle_for_date(parse_date(str(record_date or "").strip()))
        return {
            "settlement_cycle_code": cycle.code,
            "cycle_start_date": cycle.start.isoformat(),
            "cycle_end_date": cycle.end_inclusive.isoformat(),
            "weeks": self.get_cycle_weeks(cycle.code),
        }

    def get_cycle_matrix_for_team(self, team_id: int, settlement_cycle_code: str) -> dict[str, Any]:
        team_id = int(team_id or 0)
        settlement_cycle_code = str(settlement_cycle_code or "").strip()
        team = self.team_repo.get_by_id(team_id, include_inactive=True)
        members = self.account_manager_repo.list_by_team(team_id)
        weeks = self.get_cycle_weeks(settlement_cycle_code)
        week_map = {int(item["week_index"]): item for item in weeks}

        saved_rows = self.weekly_target_repo.list_targets_for_team_cycle(team_id, settlement_cycle_code)
        target_map: dict[tuple[int, int], dict[str, Any]] = {}
        for row in saved_rows:
            key = (int(row.get("account_manager_id", 0) or 0), int(row.get("week_index", 0) or 0))
            target_map[key] = row

        rows: list[dict[str, Any]] = []
        for member in members:
            manager_id = int(member["id"])
            week_targets = []
            cycle_visit_target = 0
            cycle_quality_visit_target = 0
            cycle_repayment_target = 0.0
            for week in weeks:
                week_index = int(week["week_index"])
                saved = target_map.get((manager_id, week_index), {})
                visit_target = safe_int(saved.get("visit_target"))
                quality_visit_target = safe_int(saved.get("quality_visit_target"))
                repayment_target = safe_decimal(saved.get("repayment_target"))
                cycle_visit_target += visit_target
                cycle_quality_visit_target += quality_visit_target
                cycle_repayment_target += repayment_target
                week_targets.append(
                    {
                        "week_index": week_index,
                        "week_label": week.get("week_label", ""),
                        "week_start_date": week_map[week_index].get("week_start_date", ""),
                        "week_end_date": week_map[week_index].get("week_end_date", ""),
                        "visit_target": visit_target,
                        "quality_visit_target": quality_visit_target,
                        "repayment_target": repayment_target,
                    }
                )
            rows.append(
                {
                    "account_manager_id": manager_id,
                    "account_manager_name": member.get("account_manager_name", ""),
                    "is_active": int(member.get("is_active", 1) or 0),
                    "cycle_visit_target": cycle_visit_target,
                    "cycle_quality_visit_target": cycle_quality_visit_target,
                    "cycle_repayment_target": round(cycle_repayment_target, 2),
                    "weeks": week_targets,
                }
            )

        return {
            "team_id": team_id,
            "team": team or {},
            "settlement_cycle_code": settlement_cycle_code,
            "weeks": weeks,
            "rows": rows,
            "team_totals": self.get_team_cycle_targets(team_id, settlement_cycle_code),
        }

    def get_week_targets_for_team(
        self,
        team_id: int,
        settlement_cycle_code: str,
        week_index: int,
    ) -> dict[str, Any]:
        team_id = int(team_id or 0)
        settlement_cycle_code = str(settlement_cycle_code or "").strip()
        week_index = safe_int(week_index)
        team = self.team_repo.get_by_id(team_id, include_inactive=True)
        if team is None:
            raise ValueError("团队不存在")

        weeks = self.get_cycle_weeks(settlement_cycle_code)
        week_map = {int(item["week_index"]): item for item in weeks}
        if week_index not in week_map:
            raise ValueError(f"无效周次: {week_index}")

        members = self.account_manager_repo.list_by_team(team_id)
        saved_rows = self.weekly_target_repo.list_targets_for_team_week(
            team_id=team_id,
            settlement_cycle_code=settlement_cycle_code,
            week_index=week_index,
        )
        target_map = {int(row.get("account_manager_id", 0) or 0): row for row in saved_rows}

        rows: list[dict[str, Any]] = []
        for member in members:
            manager_id = int(member["id"])
            saved = target_map.get(manager_id, {})
            rows.append(
                {
                    "account_manager_id": manager_id,
                    "account_manager_name": member.get("account_manager_name", ""),
                    "is_active": int(member.get("is_active", 1) or 0),
                    "week_index": week_index,
                    "week_start_date": week_map[week_index].get("week_start_date", ""),
                    "week_end_date": week_map[week_index].get("week_end_date", ""),
                    "visit_target": safe_int(saved.get("visit_target")),
                    "quality_visit_target": safe_int(saved.get("quality_visit_target")),
                    "repayment_target": safe_decimal(saved.get("repayment_target")),
                }
            )

        return {
            "team_id": team_id,
            "team": team,
            "settlement_cycle_code": settlement_cycle_code,
            "weeks": weeks,
            "selected_week": week_map[week_index],
            "rows": rows,
        }

    def save_week_targets_for_team(
        self,
        team_id: int,
        settlement_cycle_code: str,
        week_index: int,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        team_id = int(team_id or 0)
        settlement_cycle_code = str(settlement_cycle_code or "").strip()
        week_index = safe_int(week_index)
        if team_id <= 0:
            raise ValueError("team_id 不能为空")
        if not settlement_cycle_code:
            raise ValueError("settlement_cycle_code 不能为空")

        team = self.team_repo.get_by_id(team_id, include_inactive=True)
        if team is None:
            raise ValueError("团队不存在")

        weeks = self.get_cycle_weeks(settlement_cycle_code)
        week_map = {int(item["week_index"]): item for item in weeks}
        if week_index not in week_map:
            raise ValueError(f"无效周次: {week_index}")

        members = self.account_manager_repo.list_by_team(team_id)
        member_ids = {int(item["id"]) for item in members}
        rows_with_week = []
        for row in rows or []:
            item = dict(row)
            item["week_index"] = week_index
            rows_with_week.append(item)

        now = now_iso()
        normalized_rows = self._normalize_save_rows(rows_with_week, member_ids, week_map)
        saved_count = self.weekly_target_repo.replace_targets_for_team_week(
            team_id=team_id,
            settlement_cycle_code=settlement_cycle_code,
            week_index=week_index,
            rows=normalized_rows,
            now=now,
        )
        self._sync_cycle_targets_from_repo(team_id, settlement_cycle_code, member_ids, now)
        return {
            "ok": True,
            "saved_count": saved_count,
            "manager_count": len(member_ids),
            "settlement_cycle_code": settlement_cycle_code,
            "week_index": week_index,
            "account_manager_cycle_targets": self.get_account_manager_cycle_targets(team_id, settlement_cycle_code),
            "team_cycle_targets": self.get_team_cycle_targets(team_id, settlement_cycle_code),
        }

    def save_cycle_matrix_for_team(
        self,
        team_id: int,
        settlement_cycle_code: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        team_id = int(team_id or 0)
        settlement_cycle_code = str(settlement_cycle_code or "").strip()
        if team_id <= 0:
            raise ValueError("team_id 不能为空")
        if not settlement_cycle_code:
            raise ValueError("settlement_cycle_code 不能为空")

        team = self.team_repo.get_by_id(team_id, include_inactive=True)
        if team is None:
            raise ValueError("团队不存在")

        weeks = self.get_cycle_weeks(settlement_cycle_code)
        week_map = {int(item["week_index"]): item for item in weeks}
        members = self.account_manager_repo.list_by_team(team_id)
        member_ids = {int(item["id"]) for item in members}
        now = now_iso()
        normalized_rows = self._normalize_save_rows(rows, member_ids, week_map)

        saved_count = self.weekly_target_repo.replace_targets_for_team_cycle(
            team_id=team_id,
            settlement_cycle_code=settlement_cycle_code,
            rows=normalized_rows,
            now=now,
        )
        self._sync_cycle_targets(team_id, settlement_cycle_code, member_ids, normalized_rows, now)

        return {
            "ok": True,
            "saved_count": saved_count,
            "manager_count": len(member_ids),
            "settlement_cycle_code": settlement_cycle_code,
            "account_manager_cycle_targets": self.get_account_manager_cycle_targets(team_id, settlement_cycle_code),
            "team_cycle_targets": self.get_team_cycle_targets(team_id, settlement_cycle_code),
        }

    def get_account_manager_cycle_targets(self, team_id: int, settlement_cycle_code: str) -> list[dict[str, Any]]:
        team_id = int(team_id or 0)
        settlement_cycle_code = str(settlement_cycle_code or "").strip()
        members = self.account_manager_repo.list_by_team(team_id)
        sums = self.weekly_target_repo.sum_targets_by_manager(team_id, settlement_cycle_code)

        result: list[dict[str, Any]] = []
        for member in members:
            manager_id = int(member["id"])
            row = sums.get(manager_id, {})
            result.append(
                {
                    "team_id": team_id,
                    "account_manager_id": manager_id,
                    "account_manager_name": member.get("account_manager_name", ""),
                    "settlement_cycle_code": settlement_cycle_code,
                    "visit_target": safe_int(row.get("visit_target")),
                    "quality_visit_target": safe_int(row.get("quality_visit_target")),
                    "repayment_target": safe_decimal(row.get("repayment_target")),
                }
            )
        return result

    def get_team_cycle_targets(self, team_id: int, settlement_cycle_code: str) -> dict[str, Any]:
        row = self.weekly_target_repo.sum_targets_for_team(
            int(team_id or 0),
            str(settlement_cycle_code or "").strip(),
        )
        return {
            "team_id": int(team_id or 0),
            "settlement_cycle_code": str(settlement_cycle_code or "").strip(),
            "visit_target": safe_int(row.get("visit_target")),
            "quality_visit_target": safe_int(row.get("quality_visit_target")),
            "repayment_target": safe_decimal(row.get("repayment_target")),
        }

    def _normalize_save_rows(
        self,
        rows: list[dict[str, Any]],
        member_ids: set[int],
        week_map: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for row in rows or []:
            manager_id = safe_int(row.get("account_manager_id"))
            if manager_id not in member_ids:
                raise ValueError(f"客户经理不属于当前团队: {manager_id}")

            raw_weeks = row.get("weeks")
            if isinstance(raw_weeks, dict):
                iterable_weeks = list(raw_weeks.values())
            elif isinstance(raw_weeks, list):
                iterable_weeks = raw_weeks
            else:
                iterable_weeks = [row]

            for week_row in iterable_weeks:
                if not isinstance(week_row, dict):
                    continue
                week_index = safe_int(week_row.get("week_index"))
                if week_index not in week_map:
                    raise ValueError(f"无效周次: {week_index}")
                key = (manager_id, week_index)
                if key in seen:
                    raise ValueError(f"重复周目标: account_manager_id={manager_id}, week_index={week_index}")
                seen.add(key)
                week = week_map[week_index]
                normalized.append(
                    {
                        "account_manager_id": manager_id,
                        "week_index": week_index,
                        "week_start_date": week["week_start_date"],
                        "week_end_date": week["week_end_date"],
                        "visit_target": safe_int(week_row.get("visit_target")),
                        "quality_visit_target": safe_int(week_row.get("quality_visit_target")),
                        "repayment_target": safe_decimal(week_row.get("repayment_target")),
                        "version": max(1, safe_int(week_row.get("version", 1))),
                    }
                )
        return normalized

    def _sync_cycle_targets(
        self,
        team_id: int,
        settlement_cycle_code: str,
        member_ids: set[int],
        rows: list[dict[str, Any]],
        now: str,
    ) -> None:
        repayment_by_manager = {manager_id: 0.0 for manager_id in member_ids}
        for row in rows:
            manager_id = int(row.get("account_manager_id", 0) or 0)
            if manager_id in repayment_by_manager:
                repayment_by_manager[manager_id] += safe_decimal(row.get("repayment_target"))

        for manager_id, target_amount in repayment_by_manager.items():
            self.cycle_target_repo.upsert_target(
                team_id=team_id,
                account_manager_id=manager_id,
                settlement_cycle_code=settlement_cycle_code,
                target_amount=target_amount,
                now=now,
            )

    def _sync_cycle_targets_from_repo(
        self,
        team_id: int,
        settlement_cycle_code: str,
        member_ids: set[int],
        now: str,
    ) -> None:
        sums = self.weekly_target_repo.sum_targets_by_manager(team_id, settlement_cycle_code)
        for manager_id in member_ids:
            target_amount = safe_decimal(sums.get(manager_id, {}).get("repayment_target"))
            self.cycle_target_repo.upsert_target(
                team_id=team_id,
                account_manager_id=manager_id,
                settlement_cycle_code=settlement_cycle_code,
                target_amount=target_amount,
                now=now,
            )
