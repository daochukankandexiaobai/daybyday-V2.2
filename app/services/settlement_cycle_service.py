from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.utils.date_utils import (
    CYCLE_MODE_CALENDAR_MONTH,
    CYCLE_MODE_FIXED_START_DAY,
    SettlementCycleRule,
    cycle_week_segments,
    normalize_settlement_cycle_rule,
    now_iso,
    parse_date,
    resolve_report_range as resolve_single_rule_report_range,
    settlement_cycle_display_code,
    settlement_cycle_for_date,
    settlement_cycle_from_code,
    settlement_cycle_rule_label,
)


class SettlementCycleService:
    """Resolve settlement cycles from an effective-date rule timeline.

    A saved report row keeps its own rule key snapshot.  This service determines
    which rule applies to *new* calendar dates, so a later rule never rewrites
    the date range used by earlier history.
    """

    def __init__(self, rule_repo, admin_action_log_service=None) -> None:
        self.rule_repo = rule_repo
        self.admin_action_log_service = admin_action_log_service
        self._cached_rule_rows: Optional[List[Dict[str, Any]]] = None

    def clear_cache(self) -> None:
        self._cached_rule_rows = None

    def _rule_rows(self, refresh: bool = False) -> List[Dict[str, Any]]:
        if self._cached_rule_rows is None or refresh:
            self._cached_rule_rows = list(self.rule_repo.list_active_rules())
        return list(self._cached_rule_rows)

    def _row_for_date(self, target: date, refresh: bool = False) -> Dict[str, Any]:
        target_text = target.isoformat()
        candidate: Optional[Dict[str, Any]] = None
        for row in self._rule_rows(refresh=refresh):
            if str(row.get("effective_from", "") or "") <= target_text:
                candidate = row
            else:
                break
        if candidate is None:
            candidate = self.rule_repo.get_rule_for_date(target_text) or {}
        return candidate

    @staticmethod
    def _rule_from_row(row: Dict[str, Any]) -> SettlementCycleRule:
        return normalize_settlement_cycle_rule(row or None)

    def get_active_rule(self, refresh: bool = False) -> SettlementCycleRule:
        """Compatibility accessor for the rule that applies today."""
        return self.get_rule_for_date(date.today(), refresh=refresh)

    def get_rule_for_date(self, target: date, refresh: bool = False) -> SettlementCycleRule:
        return self._rule_from_row(self._row_for_date(target, refresh=refresh))

    def get_rule_by_key(self, rule_key: str) -> SettlementCycleRule:
        row = self.rule_repo.get_rule_by_key(str(rule_key or "").strip())
        if row is None:
            return self.get_active_rule()
        return self._rule_from_row(row)

    def rule_key_for_date(self, target: date) -> str:
        row = self._row_for_date(target)
        return str(row.get("rule_key", "") or self.get_rule_for_date(target).rule_key)

    def get_rule_history_for_export(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_key": str(row.get("rule_key", "") or ""),
                "rule_mode": str(row.get("rule_mode", "") or ""),
                "start_day": int(row.get("start_day", 1) or 1),
                "effective_from": str(row.get("effective_from", "") or ""),
                "is_locked": bool(int(row.get("is_locked", 0) or 0)),
            }
            for row in self._rule_rows()
        ]

    def get_rule_status(self) -> Dict[str, Any]:
        today = date.today()
        current_row = self._row_for_date(today, refresh=True)
        initial_row = self.rule_repo.get_earliest_rule() or current_row
        current_rule = self._rule_from_row(current_row)
        has_business_data = self.rule_repo.has_business_data()
        rule_rows = self._rule_rows()
        initial_locked = bool(int(initial_row.get("is_locked", 0) or 0))
        return {
            "rule_key": str(current_row.get("rule_key", current_rule.rule_key) or current_rule.rule_key),
            "rule_mode": current_rule.mode,
            "start_day": int(current_rule.start_day),
            "is_locked": bool(int(current_row.get("is_locked", 0) or 0)),
            "has_business_data": has_business_data,
            "is_editable": not has_business_data and not initial_locked and len(rule_rows) == 1,
            "effective_from": str(current_row.get("effective_from", "") or ""),
            "label": settlement_cycle_rule_label(current_rule),
            "initial_rule_key": str(initial_row.get("rule_key", "") or ""),
            "initial_rule_locked": initial_locked,
            "has_scheduled_rules": len(rule_rows) > 1,
            "latest_business_date": self.rule_repo.latest_business_date(),
            "rules": self.get_rule_history_for_export(),
        }

    def cycle_for_date(self, target: date):
        rule = self.get_rule_for_date(target)
        cycle = settlement_cycle_for_date(target, rule)
        return self._truncate_cycle_at_successor(cycle, target.isoformat())

    def cycle_from_code(
        self,
        cycle_code: str,
        rule_key: str = "",
        reference_date: Optional[date] = None,
    ):
        if str(rule_key or "").strip():
            rule = self.get_rule_by_key(rule_key)
        elif reference_date is not None:
            rule = self.get_rule_for_date(reference_date)
        else:
            rule = self.get_active_rule()
        cycle = settlement_cycle_from_code(cycle_code, rule)
        if str(rule_key or "").strip():
            source_row = self.rule_repo.get_rule_by_key(str(rule_key).strip()) or {}
            source_effective_from = str(source_row.get("effective_from", "") or cycle.start.isoformat())
        elif reference_date is not None:
            source_effective_from = reference_date.isoformat()
        else:
            source_effective_from = cycle.start.isoformat()
        return self._truncate_cycle_at_successor(cycle, source_effective_from)

    def _truncate_cycle_at_successor(self, cycle, source_reference_date: str):
        """Return the historical slice owned by the applicable rule.

        Two adjacent rules can legitimately produce the same display code.
        In that case, the next rule's effective date is the hard boundary for
        the preceding rule's last cycle and prevents target reads from
        accidentally spanning into the successor timeline.
        """
        source_text = str(source_reference_date or "").strip()
        for row in self._rule_rows():
            effective_text = str(row.get("effective_from", "") or "")
            if not effective_text or effective_text <= source_text:
                continue
            successor_start = parse_date(effective_text)
            if cycle.start < successor_start <= cycle.end_inclusive:
                cycle.end_exclusive = successor_start
                cycle.end_inclusive = successor_start - timedelta(days=1)
            break
        return cycle

    def cycle_display_code(self, **kwargs) -> str:
        record_date = kwargs.get("record_date")
        if record_date is not None:
            target = parse_date(record_date) if isinstance(record_date, str) else record_date
            return self.cycle_for_date(target).code

        reference_date = kwargs.pop("reference_date", None)
        rule_key = kwargs.pop("rule_key", "")
        if reference_date is not None:
            target = parse_date(reference_date) if isinstance(reference_date, str) else reference_date
            kwargs["rule"] = self.get_rule_for_date(target)
        elif str(rule_key or "").strip():
            kwargs["rule"] = self.get_rule_by_key(rule_key)
        return settlement_cycle_display_code(**kwargs)

    def cycle_week_for_date(self, target: date) -> Dict[str, str]:
        cycle = self.cycle_for_date(target)
        segments = cycle_week_segments(cycle)
        selected = segments[0] if segments else {"index": "1", "label": "", "start": "", "end": ""}
        for segment in segments:
            if segment["start"] <= target.isoformat() <= segment["end"]:
                selected = segment
                break
        return {
            "cycle_code": cycle.code,
            "cycle_rule_key": self.rule_key_for_date(target),
            "cycle_start": cycle.start.isoformat(),
            "cycle_end": cycle.end_inclusive.isoformat(),
            "week_index": selected["index"],
            "week_label": selected["label"],
            "week_start": selected["start"],
            "week_end": selected["end"],
        }

    def cycle_week_segments(self, cycle) -> List[Dict[str, str]]:
        return cycle_week_segments(cycle)

    def resolve_report_range(self, mode: str, base_date: date, custom_start=None, custom_end=None):
        if mode == "周报":
            week = self.cycle_week_for_date(base_date)
            return parse_date(week["week_start"]), parse_date(week["week_end"])
        if mode == "月报":
            cycle = self.cycle_for_date(base_date)
            return cycle.start, cycle.end_inclusive
        return resolve_single_rule_report_range(
            mode,
            base_date,
            custom_start,
            custom_end,
            self.get_rule_for_date(base_date),
        )

    def range_crosses_cycles(self, start_date: date, end_date: date) -> bool:
        start_cycle = self.cycle_for_date(start_date)
        end_cycle = self.cycle_for_date(end_date)
        return (
            start_cycle.code != end_cycle.code
            or self.rule_key_for_date(start_date) != self.rule_key_for_date(end_date)
        )

    def canonical_cycle_codes_from_dates(self, dates) -> List[str]:
        codes = {
            self.cycle_for_date(parse_date(item)).code
            for item in dates
            if str(item or "").strip()
        }
        return sorted(codes)

    def preview_cycles(self, base_date: date, count: int = 3) -> List[Dict[str, str]]:
        preview: List[Dict[str, str]] = []
        current = self.cycle_for_date(base_date)
        current_date = base_date
        for _index in range(max(1, int(count or 1))):
            preview.append(
                {
                    "cycle_code": current.code,
                    "start_date": current.start.isoformat(),
                    "end_date": current.end_inclusive.isoformat(),
                    "rule_key": self.rule_key_for_date(current_date),
                }
            )
            current_date = current.end_exclusive
            current = self.cycle_for_date(current_date)
        return preview

    def update_initial_rule(
        self,
        rule_mode: str,
        start_day: int,
        operator: str = "admin",
    ) -> tuple[bool, str, Dict[str, Any]]:
        before = self.get_rule_status()
        if not before["is_editable"]:
            return False, "当前规则已受历史数据或已排期规则保护，不能直接修改", before

        initial_row = self.rule_repo.get_earliest_rule() or {}
        try:
            candidate = normalize_settlement_cycle_rule(
                {"rule_mode": rule_mode, "start_day": start_day, "rule_key": initial_row.get("rule_key", "")}
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

    def schedule_successor_rule(
        self,
        rule_mode: str,
        start_day: int,
        effective_from: str,
        operator: str = "admin",
    ) -> tuple[bool, str, Dict[str, Any]]:
        before = self.get_rule_status()
        try:
            effective_date = parse_date(str(effective_from or "").strip())
            candidate = normalize_settlement_cycle_rule({"rule_mode": rule_mode, "start_day": start_day})
        except ValueError:
            return False, "请填写有效的生效日期和周期起始日", before

        if candidate.mode not in {CYCLE_MODE_CALENDAR_MONTH, CYCLE_MODE_FIXED_START_DAY}:
            return False, "新规则只支持自然月或自定义固定起始日", before
        if effective_date.day != candidate.start_day:
            return False, "生效日期必须正好是新周期的起始日", before

        rules = self._rule_rows(refresh=True)
        if not rules:
            return False, "未找到当前结算周期规则", before
        latest_effective_from = str(rules[-1].get("effective_from", "") or "")
        if effective_date.isoformat() <= latest_effective_from:
            return False, "新规则的生效日期必须晚于现有规则的最后生效日期", before

        latest_business_date = self.rule_repo.latest_business_date()
        if latest_business_date and effective_date.isoformat() <= latest_business_date:
            return False, "新规则的生效日期必须晚于已保存日报或周目标的最后日期", before
        if self.rule_repo.has_cycle_targets() and not latest_business_date:
            return False, "当前仅存在无法定位日期的旧周期目标，请先完成数据迁移或联系维护人员", before

        rule_key = self._make_rule_key(candidate, effective_date)
        inserted = self.rule_repo.insert_successor_rule(
            rule_key=rule_key,
            rule_mode=candidate.mode,
            start_day=candidate.start_day,
            effective_from=effective_date.isoformat(),
            operator=str(operator or "admin"),
            now=now_iso(),
            is_locked=1,
        )
        if not inserted:
            return False, "该生效日期已经存在结算周期规则", before

        self.clear_cache()
        after = self.get_rule_status()
        self._log("schedule_settlement_cycle_rule", operator, before, after, "新增按生效日期切换的结算周期规则")
        return True, "新规则已排期，历史数据将继续按原规则统计", after

    def merge_imported_rule_history(
        self,
        rule_history: Any,
        operator: str = "import",
    ) -> Dict[str, str]:
        """Merge safe rule metadata before importing report rows.

        Existing locked rules win.  A brand-new database may replace its empty
        bootstrap rule with the legacy rule carried by an import package.
        The return value maps incoming rule keys to local rule keys.
        """
        if not isinstance(rule_history, list):
            return {}

        normalized_items: List[Dict[str, Any]] = []
        for item in rule_history:
            if not isinstance(item, dict):
                continue
            try:
                effective_date = parse_date(str(item.get("effective_from", "")).strip())
                candidate = normalize_settlement_cycle_rule(item)
            except (TypeError, ValueError):
                continue
            normalized_items.append(
                {
                    "incoming_key": str(item.get("rule_key", "") or "").strip(),
                    "effective_from": effective_date.isoformat(),
                    "candidate": candidate,
                    "is_locked": bool(item.get("is_locked", True)),
                }
            )

        if not normalized_items:
            return {}

        changed = False
        mapping: Dict[str, str] = {}
        has_local_business_data = self.rule_repo.has_business_data()
        latest_business_date = self.rule_repo.latest_business_date()
        for item in sorted(normalized_items, key=lambda row: str(row["effective_from"])):
            effective_from = str(item["effective_from"])
            candidate = item["candidate"]
            incoming_key = str(item["incoming_key"] or "")
            local_row = self.rule_repo.get_rule_by_effective_from(effective_from)

            if local_row is not None:
                local_rule = self._rule_from_row(local_row)
                local_key = str(local_row.get("rule_key", "") or local_rule.rule_key)
                is_bootstrap = local_key == "initial_calendar_month" and not has_local_business_data
                definitions_match = (
                    local_rule.mode == candidate.mode and local_rule.start_day == candidate.start_day
                )
                if not definitions_match and is_bootstrap:
                    desired_key = incoming_key or self._make_rule_key(candidate, parse_date(effective_from))
                    existing_key_row = self.rule_repo.get_rule_by_key(desired_key)
                    if existing_key_row is not None and int(existing_key_row.get("id", 0) or 0) != int(local_row.get("id", 0) or 0):
                        desired_key = self._make_rule_key(candidate, parse_date(effective_from))
                    self.rule_repo.update_rule_definition(
                        rule_id=int(local_row["id"]),
                        rule_key=desired_key,
                        rule_mode=candidate.mode,
                        start_day=candidate.start_day,
                        is_locked=1 if item["is_locked"] else 0,
                        operator=operator,
                        now=now_iso(),
                    )
                    local_key = desired_key
                    changed = True
                mapping[incoming_key] = local_key
                continue

            if has_local_business_data and latest_business_date and effective_from <= latest_business_date:
                mapping[incoming_key] = self.rule_key_for_date(parse_date(effective_from))
                continue

            desired_key = incoming_key or self._make_rule_key(candidate, parse_date(effective_from))
            existing_key_row = self.rule_repo.get_rule_by_key(desired_key)
            if existing_key_row is not None:
                desired_key = self._make_rule_key(candidate, parse_date(effective_from))
            if self.rule_repo.insert_successor_rule(
                rule_key=desired_key,
                rule_mode=candidate.mode,
                start_day=candidate.start_day,
                effective_from=effective_from,
                operator=operator,
                now=now_iso(),
                is_locked=1 if item["is_locked"] else 0,
            ):
                mapping[incoming_key] = desired_key
                changed = True

        if changed:
            self.clear_cache()
        return mapping

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

    def _make_rule_key(self, rule: SettlementCycleRule, effective_date: date) -> str:
        mode_name = "calendar" if rule.mode == CYCLE_MODE_CALENDAR_MONTH else "fixed"
        base_key = "rule_{}_{}_{}".format(
            effective_date.strftime("%Y%m%d"),
            mode_name,
            int(rule.start_day),
        )
        candidate = base_key
        suffix = 2
        while self.rule_repo.get_rule_by_key(candidate) is not None:
            candidate = "{}_{}".format(base_key, suffix)
            suffix += 1
        return candidate

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
