from __future__ import annotations

from app.utils.date_utils import now_iso
from app.utils.validators import safe_decimal, validate_non_negative_decimal_input


class TeamService:
    def __init__(self, team_repo, account_manager_repo, cycle_target_repo, settings_service) -> None:
        self.team_repo = team_repo
        self.account_manager_repo = account_manager_repo
        self.cycle_target_repo = cycle_target_repo
        self.settings_service = settings_service

    def list_teams(self, include_inactive: bool = False, only_inactive: bool = False) -> list[dict]:
        return self.team_repo.list_teams(include_inactive=include_inactive, only_inactive=only_inactive)

    def get_current_team_id(self) -> int:
        raw = self.settings_service.get("current_team_id", "0")
        try:
            team_id = int(raw)
        except ValueError:
            team_id = 0

        if team_id <= 0:
            teams = self.list_teams()
            if not teams:
                return 0
            team_id = int(teams[0]["id"])
            self.settings_service.set("current_team_id", str(team_id))
            return team_id

        team = self.team_repo.get_by_id(team_id, include_inactive=False)
        if team is None:
            teams = self.list_teams()
            if not teams:
                self.settings_service.set("current_team_id", "0")
                return 0
            team_id = int(teams[0]["id"])
            self.settings_service.set("current_team_id", str(team_id))
        return team_id

    def set_current_team_id(self, team_id: int) -> None:
        self.settings_service.set("current_team_id", str(team_id))

    def get_team(self, team_id: int) -> dict | None:
        return self.team_repo.get_by_id(team_id, include_inactive=False)

    def list_members_with_targets(self, team_id: int, settlement_cycle_code: str) -> list[dict]:
        members = self.account_manager_repo.list_by_team(team_id)
        target_rows = self.cycle_target_repo.list_targets(team_id, settlement_cycle_code)
        target_map = {int(x["account_manager_id"]): float(x["target_amount"] or 0.0) for x in target_rows}

        result = []
        for member in members:
            manager_id = int(member["id"])
            result.append(
                {
                    "account_manager_id": manager_id,
                    "account_manager_name": member["account_manager_name"],
                    "target_amount": float(target_map.get(manager_id, 0.0)),
                    "is_active": int(member.get("is_active", 1)),
                }
            )
        return result

    def save_team_config(
        self,
        team_id: int | None,
        region: str,
        team_name: str,
        team_manager_name: str,
        settlement_cycle_code: str,
        members: list[dict],
        sync_cycle_targets: bool = True,
    ) -> tuple[bool, str, int | None]:
        region = region.strip()
        team_name = team_name.strip()
        team_manager_name = team_manager_name.strip()

        if not region or not team_name or not team_manager_name:
            return False, "区域/团队/团队经理不能为空", None

        if not members:
            return False, "客户经理名单不能为空", None

        # 先做输入校验，避免半途中写库导致部分成功。
        seen_names: set[str] = set()
        normalized_members: list[dict] = []
        for item in members:
            name = str(item.get("account_manager_name", "")).strip()
            if not name:
                continue

            key = name.casefold()
            if key in seen_names:
                return False, f"客户经理名单存在重复姓名：{name}", None
            seen_names.add(key)

            normalized = {"account_manager_name": name}
            if sync_cycle_targets:
                ok, target_value, err = validate_non_negative_decimal_input(str(item.get("target_amount", "")).strip())
                if not ok:
                    return False, f"客户经理[{name}]结算周期目标无效：{err}", None
                normalized["target_amount"] = safe_decimal(target_value)

            normalized_members.append(normalized)

        if not normalized_members:
            return False, "客户经理名单不能为空", None

        now = now_iso()
        saved_team_id = self.team_repo.save_team(team_id, region, team_name, team_manager_name, now)

        keep_ids: list[int] = []
        for item in normalized_members:
            name = item["account_manager_name"]
            manager_id = self.account_manager_repo.ensure_member(saved_team_id, name, now)
            keep_ids.append(manager_id)
            if sync_cycle_targets:
                self.cycle_target_repo.upsert_target(
                    team_id=saved_team_id,
                    account_manager_id=manager_id,
                    settlement_cycle_code=settlement_cycle_code,
                    target_amount=safe_decimal(item.get("target_amount", 0)),
                    now=now,
                )

        self.account_manager_repo.deactivate_missing(saved_team_id, keep_ids=keep_ids, now=now)
        self.set_current_team_id(saved_team_id)
        return True, "基础设置已保存", saved_team_id

    def ensure_team_and_member(self, region: str, team_name: str, team_manager_name: str, account_manager_name: str) -> tuple[int, int]:
        now = now_iso()
        team_row = self.team_repo.find_by_identity(region, team_name, team_manager_name)
        if team_row is None:
            team_id = self.team_repo.save_team(None, region, team_name, team_manager_name, now)
        else:
            team_id = int(team_row["id"])

        account_manager_id = self.account_manager_repo.ensure_member(team_id, account_manager_name, now)
        return team_id, account_manager_id
