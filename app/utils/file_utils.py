from __future__ import annotations

import re
from datetime import date
from pathlib import Path


INVALID_CHARS = r"[\\/:*?\"<>|]"


def ensure_dir(path: str) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def sanitize_component(value: str) -> str:
    text = (value or "全部").strip()
    if not text:
        text = "全部"
    text = re.sub(INVALID_CHARS, "_", text)
    return text


def build_json_filename(export_type: str, region: str, team: str, manager: str, start_date: date, end_date: date) -> str:
    region_part = sanitize_component(region)
    team_part = sanitize_component(team)
    manager_part = sanitize_component(manager)

    normalized = (export_type or "").strip().lower()
    is_week = export_type in {"某周", "周报"} or normalized in {"weekly", "week"}
    is_month = export_type in {"某月", "月报"} or normalized in {"monthly", "month"}
    is_day = export_type in {"某天", "某日"} or normalized in {"daily", "day"}

    if is_week:
        y, week_no, _ = start_date.isocalendar()
        suffix = f"{y}W{week_no:02d}"
        prefix = "周报"
    elif is_month:
        suffix = f"{start_date.year}-{start_date.month:02d}"
        prefix = "月报"
    elif is_day:
        suffix = start_date.isoformat()
        prefix = "日报"
    else:
        suffix = f"{start_date.isoformat()}_{end_date.isoformat()}"
        prefix = "区间报"

    return f"{prefix}_{region_part}_{team_part}_{manager_part}_{suffix}.json"
