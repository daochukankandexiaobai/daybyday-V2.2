from __future__ import annotations

from typing import Any

from app.utils.date_utils import now_iso


class AdminTeamService:
    def __init__(
        self,
        team_service,
        team_repo,
        settings_service,
        admin_action_log_service,
    ) -> None:
        self.team_service = team_service
        self.team_repo = team_repo
        self.settings_service = settings_service
        self.admin_action_log_service = admin_action_log_service

    def list_teams(self, status: str = "all") -> list[dict[str, Any]]:
        if status == "active":
            return self.team_service.list_teams(include_inactive=False)
        if status == "inactive":
            return self.team_service.list_teams(include_inactive=True, only_inactive=True)
        return self.team_service.list_teams(include_inactive=True)

    def get_team(self, team_id: int) -> dict[str, Any] | None:
        return self.team_repo.get_by_id(team_id, include_inactive=True)

    def save_team_config(
        self,
        team_id: int | None,
        region: str,
        team_name: str,
        team_manager_name: str,
        settlement_cycle_code: str,
        members: list[dict[str, Any]],
        operator: str,
    ) -> tuple[bool, str, int | None]:
        before = None
        if team_id:
            before = self.team_repo.get_by_id(int(team_id), include_inactive=True)
        else:
            before = self.team_repo.find_by_identity(
                region=region.strip(),
                team_name=team_name.strip(),
                team_manager_name=team_manager_name.strip(),
                include_inactive=True,
            )
        exists_before = before is not None

        ok, message, saved_team_id = self.team_service.save_team_config(
            team_id=team_id,
            region=region,
            team_name=team_name,
            team_manager_name=team_manager_name,
            settlement_cycle_code=settlement_cycle_code,
            members=members,
        )
        if not ok or not saved_team_id:
            return ok, message, saved_team_id

        after = self.team_repo.get_by_id(int(saved_team_id), include_inactive=True) or {}
        if not exists_before:
            self.admin_action_log_service.log_action(
                action_type="create_team",
                target_type="team",
                target_id=str(saved_team_id),
                operator=operator,
                before_snapshot=before,
                after_snapshot=after,
                note="Admin created team config",
            )
        return ok, message, saved_team_id

    def inspect_delete_team(self, team_id: int) -> dict[str, Any]:
        team = self.team_repo.get_by_id(team_id, include_inactive=True)
        if team is None:
            return {
                "ok": False,
                "message": "团队不存在",
                "team": None,
                "counts": {},
                "has_history_data": False,
                "recommend": "none",
            }

        counts = self.team_repo.count_related_data(team_id)
        has_history_data = (
            int(counts.get("daily_records", 0)) > 0
            or int(counts.get("import_logs", 0)) > 0
            or int(counts.get("migration_logs", 0)) > 0
        )
        return {
            "ok": True,
            "message": "ok",
            "team": team,
            "counts": counts,
            "has_history_data": has_history_data,
            "recommend": "archive",
        }

    def archive_team(self, team_id: int, operator: str, note: str = "") -> tuple[bool, str]:
        before = self.team_repo.get_by_id(team_id, include_inactive=True)
        if before is None:
            return False, "团队不存在"
        if int(before.get("is_active", 1)) == 0:
            return True, "团队已处于归档状态"

        ok = self.team_repo.set_active(team_id=team_id, active=False, now=now_iso(), cascade_members=True)
        if not ok:
            return False, "团队归档失败"

        raw_current = self.settings_service.get("current_team_id", "0")
        try:
            current_team_id = int(raw_current)
        except ValueError:
            current_team_id = 0
        if current_team_id == team_id:
            self.settings_service.set("current_team_id", "0")

        after = self.team_repo.get_by_id(team_id, include_inactive=True) or {}
        self.admin_action_log_service.log_action(
            action_type="archive_team",
            target_type="team",
            target_id=str(team_id),
            operator=operator,
            before_snapshot=before,
            after_snapshot=after,
            note=note or "管理员归档团队",
        )
        return True, "团队已归档（历史数据已保留）"

    def restore_team(self, team_id: int, operator: str, note: str = "") -> tuple[bool, str]:
        before = self.team_repo.get_by_id(team_id, include_inactive=True)
        if before is None:
            return False, "团队不存在"
        if int(before.get("is_active", 1)) == 1:
            return True, "团队已处于启用状态"

        ok = self.team_repo.set_active(team_id=team_id, active=True, now=now_iso(), cascade_members=True)
        if not ok:
            return False, "团队恢复失败"

        after = self.team_repo.get_by_id(team_id, include_inactive=True) or {}
        self.admin_action_log_service.log_action(
            action_type="restore_team",
            target_type="team",
            target_id=str(team_id),
            operator=operator,
            before_snapshot=before,
            after_snapshot=after,
            note=note or "管理员恢复团队",
        )
        return True, "团队已恢复启用"

    def hard_delete_team(self, team_id: int, operator: str, note: str = "") -> tuple[bool, str]:
        return False, "当前版本不支持物理删除团队，请使用归档停用"

    def delete_team_safely(self, team_id: int, operator: str) -> tuple[bool, str, str]:
        inspect = self.inspect_delete_team(team_id)
        if not inspect.get("ok"):
            return False, str(inspect.get("message", "团队不存在")), "none"

        ok, msg = self.archive_team(team_id, operator, note="删除团队入口统一执行归档停用")
        return ok, msg, "archived"
