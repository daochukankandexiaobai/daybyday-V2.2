from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from app.config.field_profiles import (
    PNG_SECTION_PROFILES,
    PROFILE_ANALYSIS_METRICS,
    PROFILE_ENTRY_INPUT,
    PROFILE_EXCEL_RAW_RECORD,
    PROFILE_PREVIEW_TABLE,
    PROFILE_QUERY_SUMMARY_TABLE,
    get_profile_field_keys,
)
from app.config.field_registry import FieldDefinition, export_field_keys, get_all_fields, get_field


PAGE_DATA_ENTRY = "data_entry"
PAGE_TODAY_DISPLAY = "today_display"
PAGE_QUERY_SUMMARY = "query_summary"
PAGE_ANALYSIS = "analysis"
PAGE_JSON_EXPORT = "json_export"
PAGE_EXCEL_EXPORT = "excel_export"
PAGE_PNG_TODAY = "png_today"


def _text_default(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _field_keys(profile_key: str) -> Tuple[str, ...]:
    return tuple(get_profile_field_keys(profile_key))


def get_default_field_definitions() -> Tuple[FieldDefinition, ...]:
    return get_all_fields()


def build_default_field_rows() -> List[Dict[str, Any]]:
    rows = []
    for spec in get_default_field_definitions():
        rows.append(
            {
                "field_key": spec.field_key,
                "label": spec.label,
                "data_type": spec.data_type,
                "category": spec.category,
                "group_key": spec.group_key,
                "editable": 1 if spec.editable else 0,
                "required": 1 if spec.required else 0,
                "default_value": _text_default(spec.default_value),
                "aggregation": spec.aggregation,
                "formula_id": spec.formula_id,
                "enabled": 1 if spec.enabled else 0,
                "system_field": 1,
                "storage_type": spec.storage_type,
                "storage_column": spec.storage_column,
            }
        )
    return rows


def build_default_page_visibility_rows() -> List[Dict[str, Any]]:
    rows = []
    page_profiles = [
        (PAGE_DATA_ENTRY, _field_keys(PROFILE_ENTRY_INPUT)),
        (PAGE_TODAY_DISPLAY, _field_keys(PROFILE_PREVIEW_TABLE)),
        (PAGE_QUERY_SUMMARY, _field_keys(PROFILE_QUERY_SUMMARY_TABLE)),
        (PAGE_ANALYSIS, _field_keys(PROFILE_ANALYSIS_METRICS)),
        (PAGE_JSON_EXPORT, export_field_keys("json", include_future=True)),
        (PAGE_EXCEL_EXPORT, _field_keys(PROFILE_EXCEL_RAW_RECORD)),
    ]

    for page_key, field_keys in page_profiles:
        for index, field_key in enumerate(field_keys, start=1):
            spec = get_field(field_key)
            rows.append(
                {
                    "field_key": field_key,
                    "page_key": page_key,
                    "visible": 1,
                    "group_key": spec.group_key if spec is not None else "",
                    "display_order": index,
                }
            )

    png_order = 1
    for section in sorted(PNG_SECTION_PROFILES, key=lambda item: item.index):
        for field_key in section.field_keys:
            rows.append(
                {
                    "field_key": field_key,
                    "page_key": PAGE_PNG_TODAY,
                    "visible": 1,
                    "group_key": section.key,
                    "display_order": png_order,
                }
            )
            png_order += 1

    return rows


def _template_config(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_default_view_template_rows() -> List[Dict[str, Any]]:
    png_sections = []
    for section in sorted(PNG_SECTION_PROFILES, key=lambda item: item.index):
        png_sections.append(
            {
                "key": section.key,
                "index": section.index,
                "title": section.title,
                "file_suffix": section.file_suffix,
                "field_keys": list(section.field_keys),
            }
        )

    today_groups = []
    for section in sorted(PNG_SECTION_PROFILES, key=lambda item: item.index):
        today_groups.append(
            {
                "group_key": section.key,
                "title": section.title,
                "field_keys": list(section.field_keys),
            }
        )

    templates = [
        {
            "template_key": "entry_default",
            "template_name": "数据录入默认模板",
            "page_key": PAGE_DATA_ENTRY,
            "config_json": _template_config({"field_keys": list(_field_keys(PROFILE_ENTRY_INPUT))}),
            "is_default": 1,
            "enabled": 1,
        },
        {
            "template_key": "today_display_default",
            "template_name": "今日展示默认模板",
            "page_key": PAGE_TODAY_DISPLAY,
            "config_json": _template_config(
                {
                    "field_keys": list(_field_keys(PROFILE_PREVIEW_TABLE)),
                    "groups": today_groups,
                }
            ),
            "is_default": 1,
            "enabled": 1,
        },
        {
            "template_key": "query_summary_default",
            "template_name": "查询汇总默认模板",
            "page_key": PAGE_QUERY_SUMMARY,
            "config_json": _template_config({"field_keys": list(_field_keys(PROFILE_QUERY_SUMMARY_TABLE))}),
            "is_default": 1,
            "enabled": 1,
        },
        {
            "template_key": "png_today_default",
            "template_name": "今日展示 PNG 默认模板",
            "page_key": PAGE_PNG_TODAY,
            "config_json": _template_config({"sections": png_sections}),
            "is_default": 1,
            "enabled": 1,
        },
        {
            "template_key": "analysis_default",
            "template_name": "数据分析默认模板",
            "page_key": PAGE_ANALYSIS,
            "config_json": _template_config({"metric_field_keys": list(_field_keys(PROFILE_ANALYSIS_METRICS))}),
            "is_default": 1,
            "enabled": 1,
        },
    ]
    return templates
