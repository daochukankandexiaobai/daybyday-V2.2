from __future__ import annotations

from typing import Any

from app.utils.validators import DAILY_AMOUNT_FIELDS, DAILY_INT_FIELDS, safe_decimal, safe_int


class AdminDataService:
    def __init__(
        self,
        record_repo,
        team_repo,
        account_manager_repo,
        record_service,
        admin_action_log_service,
    ) -> None:
        self.record_repo = record_repo
        self.team_repo = team_repo
        self.account_manager_repo = account_manager_repo
        self.record_service = record_service
        self.admin_action_log_service = admin_action_log_service

    def list_team_options(self) -> list[dict[str, Any]]:
        return self.team_repo.list_teams(include_inactive=True)

    def list_account_manager_options(self, team_ids: list[int] | None = None) -> list[dict[str, Any]]:
        normalized_team_ids = sorted({int(x) for x in (team_ids or []) if int(x) > 0})
        members: list[dict[str, Any]] = []
        if normalized_team_ids:
            for team_id in normalized_team_ids:
                team_members = self.account_manager_repo.list_by_team(team_id, include_inactive=True)
                for item in team_members:
                    members.append(
                        {
                            "id": int(item.get("id", 0) or 0),
                            "team_id": int(item.get("team_id", 0) or 0),
                            "name": str(item.get("account_manager_name", "")),
                            "is_active": int(item.get("is_active", 1)),
                        }
                    )
        else:
            for team in self.team_repo.list_teams(include_inactive=True):
                team_id = int(team.get("id", 0) or 0)
                if team_id <= 0:
                    continue
                team_members = self.account_manager_repo.list_by_team(team_id, include_inactive=True)
                for item in team_members:
                    members.append(
                        {
                            "id": int(item.get("id", 0) or 0),
                            "team_id": team_id,
                            "name": str(item.get("account_manager_name", "")),
                            "is_active": int(item.get("is_active", 1)),
                        }
                    )

        dedup: dict[int, dict[str, Any]] = {}
        for item in members:
            manager_id = int(item.get("id", 0) or 0)
            if manager_id > 0:
                dedup[manager_id] = item
        result = list(dedup.values())
        result.sort(key=lambda x: (str(x.get("name", "")), int(x.get("team_id", 0))))
        return result

    def list_daily_records(
        self,
        start_date: str,
        end_date: str,
        team_ids: list[int] | None = None,
        account_manager_id: int | None = None,
        source_type: str = "",
        source_file_keyword: str = "",
    ) -> list[dict[str, Any]]:
        normalized_team_ids = sorted({int(x) for x in (team_ids or []) if int(x) > 0})
        source_type_filter = ""
        normalized_source = str(source_type or "").strip()
        if normalized_source and normalized_source not in {"All", "全部"}:
            source_type_filter = normalized_source

        rows = self.record_repo.list_records(
            start_date=start_date,
            end_date=end_date,
            team_ids=normalized_team_ids if normalized_team_ids else None,
            account_manager_id=account_manager_id if account_manager_id and account_manager_id > 0 else None,
            source_type=source_type_filter,
        )
        keyword = str(source_file_keyword or "").strip()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("source_file", ""))]
        rows.sort(
            key=lambda x: (
                str(x.get("record_date", "")),
                str(x.get("team_name_snapshot", "")),
                str(x.get("account_manager_name_snapshot", "")),
                int(x.get("id", 0) or 0),
            )
        )
        return rows

    def get_daily_record(self, row_id: int) -> dict[str, Any] | None:
        return self.record_repo.get_by_id(row_id)

    @staticmethod
    def _normalize_edit_payload(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "account_manager_id": int(existing.get("account_manager_id", 0) or 0),
            "remark": str(updates.get("remark", existing.get("remark", ""))),
        }

        for key in DAILY_INT_FIELDS:
            payload[key] = safe_int(updates.get(key, existing.get(key, 0)))
        for key in DAILY_AMOUNT_FIELDS:
            payload[key] = safe_decimal(updates.get(key, existing.get(key, 0.0)))
        return payload

    def update_daily_record(
        self,
        row_id: int,
        updates: dict[str, Any],
        operator: str,
        note: str = "",
    ) -> tuple[bool, str, dict[str, Any] | None]:
        existing = self.record_repo.get_by_id(row_id)
        if existing is None:
            return False, "记录不存在", None

        team_id = int(existing.get("team_id", 0) or 0)
        record_date = str(existing.get("record_date", ""))
        if team_id <= 0 or not record_date:
            return False, "记录关键字段无效", None

        source_type = str(updates.get("source_type", existing.get("source_type", "local")) or "local")
        source_file = str(updates.get("source_file", existing.get("source_file", "")) or "")
        payload = self._normalize_edit_payload(existing, updates)

        ok, msg, stats = self.record_service.save_team_day_sheet(
            team_id=team_id,
            record_date=record_date,
            rows=[payload],
            source_type=source_type,
            source_file=source_file,
        )
        if not ok:
            return False, msg, None

        changed = int(stats.get("inserted", 0) or 0) + int(stats.get("updated", 0) or 0)
        if changed <= 0:
            return True, "未检测到数据变化", existing

        after = self.record_repo.get_by_id(row_id)
        self.admin_action_log_service.log_action(
            action_type="edit_daily_record",
            target_type="daily_record",
            target_id=str(row_id),
            operator=operator,
            before_snapshot=existing,
            after_snapshot=after,
            note=note or "管理员编辑日报记录",
        )
        return True, msg, after

    def delete_daily_record(self, row_id: int, operator: str, note: str = "") -> tuple[bool, str]:
        existing = self.record_repo.get_by_id(row_id)
        if existing is None:
            return False, "记录不存在"

        ok = self.record_repo.delete_by_id(row_id)
        if not ok:
            return False, "删除失败"

        self.admin_action_log_service.log_action(
            action_type="delete_daily_record",
            target_type="daily_record",
            target_id=str(row_id),
            operator=operator,
            before_snapshot=existing,
            after_snapshot=None,
            note=note or "管理员删除日报记录",
        )
        return True, "删除成功"

    def delete_daily_records(self, row_ids: list[int], operator: str) -> tuple[int, int]:
        success = 0
        failed = 0
        for row_id in sorted({int(x) for x in row_ids if int(x) > 0}):
            ok, _ = self.delete_daily_record(
                row_id=row_id,
                operator=operator,
                note="管理员批量删除日报记录",
            )
            if ok:
                success += 1
            else:
                failed += 1
        return success, failed

