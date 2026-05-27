from __future__ import annotations

from typing import Any


def format_money(value: Any) -> str:
    return f"{float(value or 0):.2f}"


def format_int(value: Any) -> str:
    return str(int(value or 0))


def format_percent(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.2f}%"
