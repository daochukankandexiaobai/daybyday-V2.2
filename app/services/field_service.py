from __future__ import annotations

from typing import Any

from app.config.field_registry import FieldSpec
from app.utils import field_utils


class FieldService:
    """Thin service facade over the field center.

    This is intentionally small for the first migration batch. Existing pages
    can keep their current hard-coded definitions and switch to this facade one
    surface at a time in later batches.
    """

    def get_field(self, field_key: str) -> FieldSpec | None:
        return field_utils.get_field(field_key)

    def require_field(self, field_key: str) -> FieldSpec:
        return field_utils.require_field(field_key)

    def list_fields(self, *, include_future: bool = True, include_display: bool = True) -> tuple[FieldSpec, ...]:
        return field_utils.list_fields(include_future=include_future, include_display=include_display)

    def list_daily_metric_fields(self, *, include_future: bool = True) -> tuple[FieldSpec, ...]:
        return field_utils.list_daily_metric_fields(include_future=include_future)

    def list_group_fields(self, group_key: str, *, include_future: bool = True) -> tuple[FieldSpec, ...]:
        return field_utils.list_fields_for_group(group_key, include_future=include_future)

    def list_profile_fields(self, profile_key: str, *, include_future: bool = True) -> tuple[FieldSpec, ...]:
        return field_utils.list_fields_for_profile(profile_key, include_future=include_future)

    def label_for(self, field_key: str, fallback: str = "") -> str:
        return field_utils.get_field_label(field_key, fallback=fallback)

    def default_for(self, field_key: str, fallback: Any = None) -> Any:
        return field_utils.default_value_for(field_key, fallback=fallback)

    def format_type_for(self, field_key: str, fallback: str = "text") -> str:
        return field_utils.format_type_for(field_key, fallback=fallback)

    def aggregation_for(self, field_key: str, fallback: str = "none") -> str:
        return field_utils.aggregation_for(field_key, fallback=fallback)

    def format_value(self, field_key: str, value: Any) -> str:
        return field_utils.format_field_value(field_key, value)

    def build_default_daily_metrics(self, *, include_future: bool = True) -> dict[str, Any]:
        return field_utils.build_default_daily_metrics(include_future=include_future)

