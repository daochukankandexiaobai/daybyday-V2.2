from __future__ import annotations

from typing import Tuple

from app.config.field_registry import (
    AGGREGATION_DERIVED,
    AGGREGATION_LATEST,
    AGGREGATION_NONE,
    AGGREGATION_SUM,
    DATA_TYPE_AMOUNT,
    DATA_TYPE_DATE,
    DATA_TYPE_INT,
    DATA_TYPE_PERCENT,
    DATA_TYPE_TEXT,
    DATA_TYPE_TEXTAREA,
    FORMAT_AMOUNT,
    FORMAT_DATE,
    FORMAT_INT,
    FORMAT_PERCENT,
    FORMAT_TEXT,
    FieldSpec,
    daily_amount_field_keys,
    daily_int_field_keys,
    daily_metric_field_keys,
    daily_metric_field_specs,
    export_field_keys,
    get_field_spec,
    template_field_specs,
)


LEGACY_DAILY_INT_FIELD_KEYS: Tuple[str, ...] = daily_int_field_keys(include_future=False)
LEGACY_DAILY_AMOUNT_FIELD_KEYS: Tuple[str, ...] = daily_amount_field_keys(include_future=False)
LEGACY_DAILY_METRIC_FIELD_KEYS: Tuple[str, ...] = daily_metric_field_keys(include_future=False)

CONFIGURED_DAILY_INT_FIELD_KEYS: Tuple[str, ...] = daily_int_field_keys(include_future=True)
CONFIGURED_DAILY_AMOUNT_FIELD_KEYS: Tuple[str, ...] = daily_amount_field_keys(include_future=True)
CONFIGURED_DAILY_METRIC_FIELD_KEYS: Tuple[str, ...] = daily_metric_field_keys(include_future=True)

CONFIGURED_JSON_EXPORT_FIELD_KEYS: Tuple[str, ...] = export_field_keys("json", include_future=True)
CONFIGURED_EXCEL_EXPORT_FIELD_KEYS: Tuple[str, ...] = export_field_keys("excel", include_future=True)
CONFIGURED_PNG_EXPORT_FIELD_KEYS: Tuple[str, ...] = export_field_keys("png", include_future=True)


def get_data_type(field_key: str) -> str:
    return get_field_spec(field_key).data_type


def get_format_type(field_key: str) -> str:
    return get_field_spec(field_key).format_type


def get_default_value(field_key: str):
    return get_field_spec(field_key).default


def get_aggregation_strategy(field_key: str) -> str:
    return get_field_spec(field_key).aggregation


def is_sum_field(field_key: str) -> bool:
    return get_aggregation_strategy(field_key) == AGGREGATION_SUM


def is_editable_field(field_key: str) -> bool:
    return bool(get_field_spec(field_key).editable)


def is_analyzable_field(field_key: str) -> bool:
    return bool(get_field_spec(field_key).analyzable)


def get_chart_supported(field_key: str) -> Tuple[str, ...]:
    return tuple(get_field_spec(field_key).chart_supported)


def supports_chart(field_key: str, chart_key: str) -> bool:
    return chart_key in get_chart_supported(field_key)


def is_future_field(field_key: str) -> bool:
    return bool(get_field_spec(field_key).is_future_field)


def configured_daily_metric_specs(*, include_future: bool = True) -> Tuple[FieldSpec, ...]:
    return daily_metric_field_specs(include_future=include_future)


def configured_template_fields(*, include_future: bool = True) -> Tuple[FieldSpec, ...]:
    return template_field_specs(include_future=include_future)


__all__ = [
    "AGGREGATION_DERIVED",
    "AGGREGATION_LATEST",
    "AGGREGATION_NONE",
    "AGGREGATION_SUM",
    "DATA_TYPE_AMOUNT",
    "DATA_TYPE_DATE",
    "DATA_TYPE_INT",
    "DATA_TYPE_PERCENT",
    "DATA_TYPE_TEXT",
    "DATA_TYPE_TEXTAREA",
    "FORMAT_AMOUNT",
    "FORMAT_DATE",
    "FORMAT_INT",
    "FORMAT_PERCENT",
    "FORMAT_TEXT",
    "LEGACY_DAILY_INT_FIELD_KEYS",
    "LEGACY_DAILY_AMOUNT_FIELD_KEYS",
    "LEGACY_DAILY_METRIC_FIELD_KEYS",
    "CONFIGURED_DAILY_INT_FIELD_KEYS",
    "CONFIGURED_DAILY_AMOUNT_FIELD_KEYS",
    "CONFIGURED_DAILY_METRIC_FIELD_KEYS",
    "CONFIGURED_JSON_EXPORT_FIELD_KEYS",
    "CONFIGURED_EXCEL_EXPORT_FIELD_KEYS",
    "CONFIGURED_PNG_EXPORT_FIELD_KEYS",
    "configured_daily_metric_specs",
    "configured_template_fields",
    "get_aggregation_strategy",
    "get_chart_supported",
    "get_data_type",
    "get_default_value",
    "get_format_type",
    "is_analyzable_field",
    "is_editable_field",
    "is_future_field",
    "is_sum_field",
    "supports_chart",
]
