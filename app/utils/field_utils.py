from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config.field_groups import get_group_field_keys
from app.config.field_profiles import get_profile_field_keys
from app.config.field_registry import (
    FORMAT_AMOUNT,
    FORMAT_DATE,
    FORMAT_INT,
    FORMAT_PERCENT,
    FieldSpec,
    daily_metric_field_specs,
    get_field_spec,
    has_field,
    iter_field_specs,
)
from app.config.field_rules import get_aggregation_strategy, get_default_value, get_format_type
from app.utils.format_utils import format_int, format_money, format_percent


def require_field(field_key: str) -> FieldSpec:
    return get_field_spec(field_key)


def get_field(field_key: str) -> Optional[FieldSpec]:
    if not has_field(field_key):
        return None
    return get_field_spec(field_key)


def list_fields(*, include_future: bool = True, include_display: bool = True) -> Tuple[FieldSpec, ...]:
    return iter_field_specs(include_future=include_future, include_display=include_display)


def list_daily_metric_fields(*, include_future: bool = True) -> Tuple[FieldSpec, ...]:
    return daily_metric_field_specs(include_future=include_future)


def list_fields_for_group(group_key: str, *, include_future: bool = True) -> Tuple[FieldSpec, ...]:
    fields = []
    for key in get_group_field_keys(group_key):
        spec = get_field(key)
        if spec is None:
            continue
        if spec.is_future_field and not include_future:
            continue
        fields.append(spec)
    return tuple(fields)


def list_fields_for_profile(profile_key: str, *, include_future: bool = True) -> Tuple[FieldSpec, ...]:
    fields = []
    for key in get_profile_field_keys(profile_key):
        spec = get_field(key)
        if spec is None:
            continue
        if spec.is_future_field and not include_future:
            continue
        fields.append(spec)
    return tuple(fields)


def get_field_label(field_key: str, fallback: str = "") -> str:
    spec = get_field(field_key)
    if spec is None:
        return fallback or field_key
    return spec.label


def default_value_for(field_key: str, fallback: Any = None) -> Any:
    spec = get_field(field_key)
    if spec is None:
        return fallback
    return get_default_value(field_key)


def format_type_for(field_key: str, fallback: str = "text") -> str:
    spec = get_field(field_key)
    if spec is None:
        return fallback
    return get_format_type(field_key)


def aggregation_for(field_key: str, fallback: str = "none") -> str:
    spec = get_field(field_key)
    if spec is None:
        return fallback
    return get_aggregation_strategy(field_key)


def format_field_value(field_key: str, value: Any) -> str:
    fmt = format_type_for(field_key)
    if fmt == FORMAT_AMOUNT:
        return format_money(value)
    if fmt == FORMAT_INT:
        return format_int(value)
    if fmt == FORMAT_PERCENT:
        return format_percent(value)
    if fmt == FORMAT_DATE:
        return str(value or "")
    return str(value if value is not None else "")


def build_default_daily_metrics(*, include_future: bool = True) -> Dict[str, Any]:
    return {
        spec.key: spec.default
        for spec in list_daily_metric_fields(include_future=include_future)
    }


def labels_for_keys(field_keys: Sequence[str]) -> List[str]:
    return [get_field_label(key) for key in field_keys]
