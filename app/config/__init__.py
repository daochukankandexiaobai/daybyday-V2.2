from __future__ import annotations

"""Central configuration package for field-driven metadata."""

from app.config.field_registry import (
    FieldDefinition,
    FieldSpec,
    get_all_fields,
    get_analysis_fields,
    get_entry_fields,
    get_field,
    get_field_spec,
    get_fields_by_group,
    get_fields_for_page,
    get_png_export_fields,
    get_query_summary_fields,
    get_today_display_fields,
    has_field,
    is_field_known,
)

__all__ = [
    "FieldDefinition",
    "FieldSpec",
    "get_all_fields",
    "get_analysis_fields",
    "get_entry_fields",
    "get_field",
    "get_field_spec",
    "get_fields_by_group",
    "get_fields_for_page",
    "get_png_export_fields",
    "get_query_summary_fields",
    "get_today_display_fields",
    "has_field",
    "is_field_known",
]
