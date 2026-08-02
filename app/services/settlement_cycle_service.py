from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from app.utils.date_utils import (
    CYCLE_MODE_CALENDAR_MONTH,
    CYCLE_MODE_FIXED_START_DAY,
    SettlementCycleRule,
    canonical_cycle_codes_from_dates,
    cycle_week_for_date,
    cycle_week_segments,
    normalize_settlement_cycle_rule,
    now_iso,
    range_crosses_cycles,
    resolve_report_range,
    settlement_cycle_display_code,
    settlement_cycle_for_date,
    settlement_cycle_from_code,
    settlement_cycle_rule_label,
)


class SettlementCycleService:
    """Expose the organization settlement rule to all report-facing services."""

    def __init__(self, rule_repo, admin_action_log_service=None) -> None:
        self.rule_repo = rule_repo
        self.admin_action_log_service = admin_action_log_service
        self._cached_rule: Optional[SettlementCycleRule] = None

    def clear_cache(self) -> None:
        self._cached_rule = None

    def get_active_rule(self, refresh: bool = False) -> SettlementCycleRule:
        if self._cached_rule is not None and not refresh:
            return self._cached_rule
        row = self.rule_repo.get_active_rule()
        self._cached_rule = normalize_settlement_cycle_rule(row)
        return self._cached_rule

    def get_rule_status(self) -> Dict[str, Any]:
        row = self.rule_repo.get_active_rule() or {}
        rule = self.get_active_rule(refresh=True)
        has_business_data = self.rule_repo.has_business_data()
        return {
            "rule_key": str(row.get("rule_key", rule.rule_key) or rule.rule_key),
            "rule_mode": rule.mode,
            "start_day": int(rule.start_day),
            "is_locked": bool(int(row.get("is_locked", 1 if rule.is_locked else 0) or 0)),
            "has_business_data": has_business_data,
            "is_editable": not bool(int(row.get("is_locked", 1 if rule.is_locked else 0) or 0)) and not has_business_data,
            "effective_from": str(row.get("effective_from", "") or ""),
            "label": settlement_cycle_rule_label(rule),
        }

    def cycle_for_date(self, target: date):
        return settlement_cycle_for_date(target, self.get_active_rule())

    def cycle_from_code(self, cycle_code: str):
        return settlement_cycle_from_code(cycle_code, self.get_active_rule())

    def cycle_display_code(self, **kwargs) -> str:
        kwargs["rule"] = self.get_active_rule()
        return settlement_cycle_display_code(**kwargs)

    def cycle_week_for_date(self, target: date) -> Dict[str, str]:
        return cycle_week_for_date(target, self.get_active_rule())

    def cycle_week_segments(self, cycle) -> List[Dict[str, str]]:
        return cycle_week_segments(cycle)

    def resolve_report_range(self, mode: str, base_date: date, custom_start=None, custom_end=None):
        return resolve_report_range(
            mode,
            base_date,
            custom_start,
            custom_end,
            self.get_active_rule(),
        )

    def range_crosses_cycles(self, start_date: date, end_date: date) -> bool:
        return range_crosses_cycles(start_date, end_date, self.get_active_rule())

    def canonical_cycle_codes_from_dates(self, dates) -> List[str]:
        return canonical_cycle_codes_from_dates(dates, self.get_active_rule())

    def preview_cycles(self, base_date: date, count: int = 3) -> List[Dict[str, str]]:
        preview: List[Dict[str, str]] = []
        current = self.cycle_for_date(base_date)
        for _index in range(max(1, int(count or 1))):
            preview.append(
                {
                    "cycle_code": current.code,
                    "start_date": current.start.isoformat(),
                    "end_date": current.end_inclusive.isoformat(),
                }
            )
            current = self.cycle_for_date(current.end_exclusive)
        return preview

    def update_initial_rule(
        self,
        rule_mode: str,
        start_day: int,
        operator: str = "admin",
    ) -> tuple[bool, str, Dict[str, Any]]:
        before = self.get_rule_status()
        if before["is_locked"]:
            return False, "结算周期规则已锁定，不能直接修改", before
        if self.rule_repo.has_business_data():
            return False, "已有日报或周期目标，不能直接修改结算周期规则", before

        try:
            candidate = normalize_settlement_cycle_rule(
                {"rule_mode": rule_mode, "start_day": start_day, "rule_key": before["rule_key"]}
            )
        except ValueError:
            return False, "自定义周期起始日只能设置为每月1日至28日", before
        if candidate.mode not in {CYCLE_MODE_CALENDAR_MONTH, CYCLE_MODE_FIXED_START_DAY}:
            return False, "不支持的结算周期规则", before

        updated = self.rule_repo.update_active_initial_rule(
            rule_mode=candidate.mode,
            start_day=candidate.start_day,
            operator=str(operator or "admin"),
            now=now_iso(),
        )
        if not updated:
            return False, "规则未保存：当前规则已锁定或已有业务数据", before

        self.clear_cache()
        after = self.get_rule_status()
        self._log("update_settlement_cycle_rule", operator, before, after, "更新初始结算周期规则")
        return True, "结算周期规则已保存，尚未锁定", after

    def lock_active_rule(self, operator: str = "admin") -> tuple[bool, str, Dict[str, Any]]:
        before = self.get_rule_status()
        if before["is_locked"]:
            return True, "结算周期规则已锁定", before
        if not self.rule_repo.lock_active_rule(str(operator or "admin"), now_iso()):
            return False, "结算周期规则锁定失败", before
        self.clear_cache()
        after = self.get_rule_status()
        self._log("lock_settlement_cycle_rule", operator, before, after, "确认并锁定结算周期规则")
        return True, "结算周期规则已确认并锁定", after

    def _log(self, action_type: str, operator: str, before: Dict[str, Any], after: Dict[str, Any], note: str) -> None:
        if self.admin_action_log_service is None:
            return
        self.admin_action_log_service.log_action(
            action_type=action_type,
            target_type="settlement_cycle_rule",
            target_id=str(after.get("rule_key", before.get("rule_key", "initial_rule"))),
            operator=str(operator or "admin"),
            before_snapshot=before,
            after_snapshot=after,
            note=note,
        )
