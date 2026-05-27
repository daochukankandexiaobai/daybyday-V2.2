from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable


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
    end = start + timedelta(days=6)
    return start, end


def month_range(target: date) -> tuple[date, date]:
    start = target.replace(day=1)
    next_year, next_month = _shift_month(start.year, start.month, 1)
    end = date(next_year, next_month, 1) - timedelta(days=1)
    return start, end


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _parse_year_month(text: str) -> tuple[int, int] | None:
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
    return f"{year:04d}-{month:02d}期"


def normalize_cycle_code_text(code: str) -> str:
    """格式化周期编码文本，不做旧新规则推断。"""
    parsed = _parse_year_month(code)
    if parsed is None:
        return str(code or "").strip()
    year, month = parsed
    return _fmt_cycle_code(year, month)


def settlement_cycle_start_for_date(target: date) -> date:
    if target.day >= 29:
        return target.replace(day=29)
    year, month = _shift_month(target.year, target.month, -1)
    return date(year, month, 29)


def settlement_cycle_code_from_start(cycle_start: date) -> str:
    # V1.1：展示/编码统一按结束月命名
    # 例如 2026-03-29 ~ 2026-04-28 => 2026-04期
    end_year, end_month = _shift_month(cycle_start.year, cycle_start.month, 1)
    return _fmt_cycle_code(end_year, end_month)


def settlement_cycle_for_date(target: date) -> SettlementCycleInfo:
    start = settlement_cycle_start_for_date(target)
    next_year, next_month = _shift_month(start.year, start.month, 1)
    end_exclusive = date(next_year, next_month, 29)
    end_inclusive = end_exclusive - timedelta(days=1)
    return SettlementCycleInfo(
        code=settlement_cycle_code_from_start(start),
        start=start,
        end_inclusive=end_inclusive,
        end_exclusive=end_exclusive,
    )


def settlement_cycle_from_code(code: str) -> SettlementCycleInfo:
    parsed = _parse_year_month(code)
    if parsed is None:
        raise ValueError(f"无效结算周期编码: {code}")
    # code 按结束月命名，起始月 = 结束月 - 1
    end_year, end_month = parsed
    start_year, start_month = _shift_month(end_year, end_month, -1)
    start = date(start_year, start_month, 29)
    return settlement_cycle_for_date(start)


def settlement_cycle_display_code(
    *,
    record_date: date | str | None = None,
    cycle_start: date | str | None = None,
    cycle_end: date | str | None = None,
    cycle_code: str = "",
) -> str:
    """统一结算周期展示编码（结束月命名）。

    优先级：
    1. record_date（最可靠）
    2. cycle_end
    3. cycle_start
    4. cycle_code（仅做格式化）
    """
    if record_date is not None:
        d = parse_date(record_date) if isinstance(record_date, str) else record_date
        return settlement_cycle_for_date(d).code

    if cycle_end is not None:
        d = parse_date(cycle_end) if isinstance(cycle_end, str) else cycle_end
        return _fmt_cycle_code(d.year, d.month)

    if cycle_start is not None:
        d = parse_date(cycle_start) if isinstance(cycle_start, str) else cycle_start
        year, month = _shift_month(d.year, d.month, 1)
        return _fmt_cycle_code(year, month)

    return normalize_cycle_code_text(cycle_code)


def canonical_cycle_codes_from_dates(dates: Iterable[str]) -> list[str]:
    codes = {
        settlement_cycle_for_date(parse_date(item)).code
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
                "label": f"第{index}周（{start.isoformat()}~{end.isoformat()}）",
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
        )
        current = end + timedelta(days=1)
        index += 1
    return segments


def cycle_week_for_date(target: date) -> dict[str, str]:
    cycle = settlement_cycle_for_date(target)
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
    custom_start: date | None = None,
    custom_end: date | None = None,
) -> tuple[date, date]:
    if mode == "某日":
        return base_date, base_date

    if mode == "周报":
        week = cycle_week_for_date(base_date)
        return parse_date(week["week_start"]), parse_date(week["week_end"])

    if mode == "月报":
        cycle = settlement_cycle_for_date(base_date)
        return cycle.start, cycle.end_inclusive

    if mode == "自定义":
        if custom_start is None or custom_end is None:
            raise ValueError("自定义范围缺少起止日期")
        if custom_start > custom_end:
            raise ValueError("开始日期不能晚于结束日期")
        return custom_start, custom_end

    raise ValueError(f"未知范围模式: {mode}")


def resolve_date_range(
    mode: str,
    base_date: date,
    custom_start: date | None = None,
    custom_end: date | None = None,
) -> tuple[date, date]:
    """兼容旧接口：某天/某周/某月/自定义。"""
    mapping = {
        "某天": "某日",
        "某周": "周报",
        "某月": "月报",
        "自定义": "自定义",
    }
    return resolve_report_range(mapping.get(mode, mode), base_date, custom_start, custom_end)


def range_crosses_cycles(start_date: date, end_date: date) -> bool:
    return settlement_cycle_for_date(start_date).code != settlement_cycle_for_date(end_date).code


def day_start_iso(target: date) -> str:
    return f"{target.isoformat()}T00:00:00"


def day_end_iso(target: date) -> str:
    return f"{target.isoformat()}T23:59:59"
