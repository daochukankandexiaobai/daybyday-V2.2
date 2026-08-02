from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping, Optional, Union


CYCLE_MODE_CALENDAR_MONTH = "calendar_month"
CYCLE_MODE_FIXED_START_DAY = "fixed_start_day"
CYCLE_MODE_LEGACY_29 = "legacy_29"


@dataclass(frozen=True)
class SettlementCycleRule:
    """A monthly settlement boundary rule independent from database storage."""

    mode: str = CYCLE_MODE_CALENDAR_MONTH
    start_day: int = 1
    rule_key: str = "default"
    is_locked: bool = False


DEFAULT_SETTLEMENT_CYCLE_RULE = SettlementCycleRule()
LEGACY_SETTLEMENT_CYCLE_RULE = SettlementCycleRule(
    mode=CYCLE_MODE_LEGACY_29,
    start_day=29,
    rule_key="legacy_29",
    is_locked=True,
)


@dataclass
class SettlementCycleInfo:
    code: str
    start: date
    end_inclusive: date
    end_exclusive: date


def today_str() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min


def week_range(target: date) -> tuple[date, date]:
    start = target - timedelta(days=target.weekday())
    return start, start + timedelta(days=6)


def month_range(target: date) -> tuple[date, date]:
    start = target.replace(day=1)
    next_year, next_month = _shift_month(start.year, start.month, 1)
    return start, date(next_year, next_month, 1) - timedelta(days=1)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _parse_year_month(text: str) -> Optional[tuple[int, int]]:
    clean = str(text or "").replace("期", "").strip()
    if len(clean) != 7 or clean[4] != "-":
        return None
    try:
        year = int(clean[:4])
        month = int(clean[5:7])
    except (TypeError, ValueError):
        return None
    if month < 1 or month > 12:
        return None
    return year, month


def _fmt_cycle_code(year: int, month: int) -> str:
    return "{:04d}-{:02d}期".format(year, month)


def normalize_cycle_code_text(code: str) -> str:
    parsed = _parse_year_month(code)
    if parsed is None:
        return str(code or "").strip()
    return _fmt_cycle_code(parsed[0], parsed[1])


def normalize_settlement_cycle_rule(
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> SettlementCycleRule:
    if isinstance(rule, SettlementCycleRule):
        mode = str(rule.mode or CYCLE_MODE_CALENDAR_MONTH).strip()
        start_day = int(rule.start_day or 1)
        rule_key = str(rule.rule_key or "default").strip() or "default"
        is_locked = bool(rule.is_locked)
    elif isinstance(rule, Mapping):
        mode = str(rule.get("rule_mode", rule.get("mode", CYCLE_MODE_CALENDAR_MONTH)) or "").strip()
        try:
            start_day = int(rule.get("start_day", 1) or 1)
        except (TypeError, ValueError):
            start_day = 1
        rule_key = str(rule.get("rule_key", "default") or "default").strip() or "default"
        is_locked = bool(int(rule.get("is_locked", 0) or 0))
    else:
        return DEFAULT_SETTLEMENT_CYCLE_RULE

    if mode == CYCLE_MODE_LEGACY_29:
        return SettlementCycleRule(CYCLE_MODE_LEGACY_29, 29, rule_key, is_locked)
    if mode == CYCLE_MODE_CALENDAR_MONTH:
        return SettlementCycleRule(CYCLE_MODE_CALENDAR_MONTH, 1, rule_key, is_locked)
    if mode != CYCLE_MODE_FIXED_START_DAY or start_day < 1 or start_day > 28:
        raise ValueError("invalid settlement cycle rule")
    return SettlementCycleRule(CYCLE_MODE_FIXED_START_DAY, start_day, rule_key, is_locked)


def settlement_cycle_rule_label(
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> str:
    normalized = normalize_settlement_cycle_rule(rule)
    if normalized.mode == CYCLE_MODE_CALENDAR_MONTH:
        return "自然月：每月1日至月底"
    if normalized.mode == CYCLE_MODE_LEGACY_29:
        return "兼容规则：每月29日至次月28日"
    return "自定义：每月{}日至次月{}日".format(normalized.start_day, normalized.start_day - 1)


def _legacy_start_for_date(target: date) -> date:
    if target.day >= 29:
        return target.replace(day=29)
    previous_year, previous_month = _shift_month(target.year, target.month, -1)
    if previous_month == 2 and not _is_leap_year(target.year):
        return date(target.year, target.month, 1)
    try:
        return date(previous_year, previous_month, 29)
    except ValueError:
        return date(target.year, target.month, 1)


def settlement_cycle_start_for_date(
    target: date,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> date:
    normalized = normalize_settlement_cycle_rule(rule)
    if normalized.mode == CYCLE_MODE_CALENDAR_MONTH:
        return target.replace(day=1)
    if normalized.mode == CYCLE_MODE_LEGACY_29:
        return _legacy_start_for_date(target)
    if target.day >= normalized.start_day:
        return target.replace(day=normalized.start_day)
    year, month = _shift_month(target.year, target.month, -1)
    return date(year, month, normalized.start_day)


def _next_cycle_start(cycle_start: date, rule: SettlementCycleRule) -> date:
    if rule.mode == CYCLE_MODE_CALENDAR_MONTH:
        year, month = _shift_month(cycle_start.year, cycle_start.month, 1)
        return date(year, month, 1)
    if rule.mode == CYCLE_MODE_FIXED_START_DAY:
        year, month = _shift_month(cycle_start.year, cycle_start.month, 1)
        return date(year, month, rule.start_day)

    # In a non-leap year, the legacy 29th rule has a short Mar 1~28 bridge
    # after the Jan 29~Feb 28 cycle. Its next boundary is Mar 29, not Apr 29.
    if cycle_start.day == 1 and cycle_start.month == 3 and not _is_leap_year(cycle_start.year):
        return date(cycle_start.year, 3, 29)

    year, month = _shift_month(cycle_start.year, cycle_start.month, 1)
    try:
        return date(year, month, 29)
    except ValueError:
        next_year, next_month = _shift_month(year, month, 1)
        return date(next_year, next_month, 1)


def settlement_cycle_for_date(
    target: date,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> SettlementCycleInfo:
    normalized = normalize_settlement_cycle_rule(rule)
    start = settlement_cycle_start_for_date(target, normalized)
    end_exclusive = _next_cycle_start(start, normalized)
    end_inclusive = end_exclusive - timedelta(days=1)
    return SettlementCycleInfo(
        code=_fmt_cycle_code(end_inclusive.year, end_inclusive.month),
        start=start,
        end_inclusive=end_inclusive,
        end_exclusive=end_exclusive,
    )


def settlement_cycle_code_from_start(
    cycle_start: date,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> str:
    return settlement_cycle_for_date(cycle_start, rule).code


def settlement_cycle_from_code(
    code: str,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> SettlementCycleInfo:
    parsed = _parse_year_month(code)
    if parsed is None:
        raise ValueError("invalid settlement cycle code: {}".format(code))
    normalized = normalize_settlement_cycle_rule(rule)
    end_year, end_month = parsed
    if normalized.mode == CYCLE_MODE_CALENDAR_MONTH:
        return settlement_cycle_for_date(date(end_year, end_month, 1), normalized)
    start_year, start_month = _shift_month(end_year, end_month, -1)
    if normalized.mode == CYCLE_MODE_FIXED_START_DAY:
        return settlement_cycle_for_date(date(start_year, start_month, normalized.start_day), normalized)
    try:
        start = date(start_year, start_month, 29)
    except ValueError:
        start = date(end_year, end_month, 1)
    return settlement_cycle_for_date(start, normalized)


def settlement_cycle_display_code(
    *,
    record_date: Optional[Union[date, str]] = None,
    cycle_start: Optional[Union[date, str]] = None,
    cycle_end: Optional[Union[date, str]] = None,
    cycle_code: str = "",
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> str:
    if record_date is not None:
        target = parse_date(record_date) if isinstance(record_date, str) else record_date
        return settlement_cycle_for_date(target, rule).code
    if cycle_end is not None:
        target = parse_date(cycle_end) if isinstance(cycle_end, str) else cycle_end
        return _fmt_cycle_code(target.year, target.month)
    if cycle_start is not None:
        target = parse_date(cycle_start) if isinstance(cycle_start, str) else cycle_start
        return settlement_cycle_for_date(target, rule).code
    return normalize_cycle_code_text(cycle_code)


def canonical_cycle_codes_from_dates(
    dates: Iterable[str],
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> list[str]:
    codes = {
        settlement_cycle_for_date(parse_date(item), rule).code
        for item in dates
        if str(item or "").strip()
    }
    return sorted(codes)


def cycle_week_segments(cycle: SettlementCycleInfo) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    current = cycle.start
    index = 1
    while current <= cycle.end_inclusive:
        natural_start, natural_end = week_range(current)
        start = max(natural_start, cycle.start)
        end = min(natural_end, cycle.end_inclusive)
        segments.append(
            {
                "index": str(index),
                "label": "第{}周（{}~{}）".format(index, start.isoformat(), end.isoformat()),
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
        )
        current = end + timedelta(days=1)
        index += 1
    return segments


def cycle_week_for_date(
    target: date,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> dict[str, str]:
    cycle = settlement_cycle_for_date(target, rule)
    for segment in cycle_week_segments(cycle):
        if segment["start"] <= target.isoformat() <= segment["end"]:
            return {
                "cycle_code": cycle.code,
                "cycle_start": cycle.start.isoformat(),
                "cycle_end": cycle.end_inclusive.isoformat(),
                "week_index": segment["index"],
                "week_label": segment["label"],
                "week_start": segment["start"],
                "week_end": segment["end"],
            }
    first = cycle_week_segments(cycle)[0]
    return {
        "cycle_code": cycle.code,
        "cycle_start": cycle.start.isoformat(),
        "cycle_end": cycle.end_inclusive.isoformat(),
        "week_index": first["index"],
        "week_label": first["label"],
        "week_start": first["start"],
        "week_end": first["end"],
    }


def resolve_report_range(
    mode: str,
    base_date: date,
    custom_start: Optional[date] = None,
    custom_end: Optional[date] = None,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> tuple[date, date]:
    if mode == "某日":
        return base_date, base_date
    if mode == "周报":
        week = cycle_week_for_date(base_date, rule)
        return parse_date(week["week_start"]), parse_date(week["week_end"])
    if mode == "月报":
        cycle = settlement_cycle_for_date(base_date, rule)
        return cycle.start, cycle.end_inclusive
    if mode == "自定义":
        if custom_start is None or custom_end is None:
            raise ValueError("custom date range is incomplete")
        if custom_start > custom_end:
            raise ValueError("custom start date cannot be after end date")
        return custom_start, custom_end
    raise ValueError("unknown report mode: {}".format(mode))


def resolve_date_range(
    mode: str,
    base_date: date,
    custom_start: Optional[date] = None,
    custom_end: Optional[date] = None,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> tuple[date, date]:
    mapping = {"某天": "某日", "某周": "周报", "某月": "月报", "自定义": "自定义"}
    return resolve_report_range(mapping.get(mode, mode), base_date, custom_start, custom_end, rule)


def range_crosses_cycles(
    start_date: date,
    end_date: date,
    rule: Optional[Union[SettlementCycleRule, Mapping[str, object]]] = None,
) -> bool:
    return settlement_cycle_for_date(start_date, rule).code != settlement_cycle_for_date(end_date, rule).code


def day_start_iso(target: date) -> str:
    return "{}T00:00:00".format(target.isoformat())


def day_end_iso(target: date) -> str:
    return "{}T23:59:59".format(target.isoformat())
