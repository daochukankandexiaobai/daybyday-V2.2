from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.config.field_registry import (
    CATEGORY_FORMULA,
    CATEGORY_RAW_DAILY,
    DATA_TYPE_AMOUNT,
    DATA_TYPE_INT,
    DATA_TYPE_PERCENT,
    DATA_TYPE_TEXT,
    DATA_TYPE_TEXTAREA,
)
from app.fields.registry import PAGE_ANALYSIS, PAGE_DATA_ENTRY, PAGE_PNG_TODAY, PAGE_QUERY_SUMMARY


FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
NUMERIC_TYPES = {DATA_TYPE_INT, DATA_TYPE_AMOUNT, "money", "decimal", DATA_TYPE_PERCENT}
TEXT_TYPES = {DATA_TYPE_TEXT, DATA_TYPE_TEXTAREA}
NUMERIC_AGGREGATIONS = {"sum", "avg", "max", "min"}


class FieldConfigHealthService:
    """Read-only validation for field and report configuration.

    The checker never repairs data automatically. It only reports errors and
    warnings so configuration mistakes do not break normal application startup.
    """

    def __init__(self, db_manager: Any, formula_service: Any) -> None:
        self.db_manager = db_manager
        self.formula_service = formula_service

    def run_checks(self) -> Dict[str, Any]:
        items: List[Dict[str, str]] = []
        with self.db_manager.get_connection() as conn:
            fields = [dict(row) for row in conn.execute("SELECT * FROM field_definitions").fetchall()]
            visibility = [dict(row) for row in conn.execute("SELECT * FROM field_page_visibility").fetchall()]
            templates = [dict(row) for row in conn.execute("SELECT * FROM view_templates").fetchall()]

        field_by_key = {str(row.get("field_key", "")): row for row in fields}
        visible_pages_by_field: Dict[str, List[str]] = {}
        for row in visibility:
            if int(row.get("visible", 0) or 0) != 1:
                continue
            field_key = str(row.get("field_key", ""))
            visible_pages_by_field.setdefault(field_key, []).append(str(row.get("page_key", "")))

        self._check_duplicate_field_keys(fields, items)
        self._check_field_basic_rules(fields, visible_pages_by_field, items)
        self._check_visibility_references(visibility, field_by_key, items)
        self._check_page_semantics(visibility, field_by_key, items)
        self._check_png_templates(templates, field_by_key, items)

        if not any(item["level"] == "error" for item in items):
            items.append(
                {
                    "level": "ok",
                    "title": "字段配置基础结构正常",
                    "detail": "未发现会阻断程序启动的字段配置错误。",
                }
            )

        error_count = sum(1 for item in items if item["level"] == "error")
        warning_count = sum(1 for item in items if item["level"] == "warning")
        ok_count = sum(1 for item in items if item["level"] == "ok")
        if error_count:
            status_code = "error"
            status_label = "存在错误"
        elif warning_count:
            status_code = "warning"
            status_label = "存在警告"
        else:
            status_code = "ok"
            status_label = "正常"
        return {
            "summary": {
                "status_code": status_code,
                "status_label": status_label,
                "error_count": error_count,
                "warning_count": warning_count,
                "ok_count": ok_count,
            },
            "items": items,
        }

    @staticmethod
    def _add(items: List[Dict[str, str]], level: str, title: str, detail: str) -> None:
        items.append({"level": level, "title": title, "detail": detail})

    def _check_duplicate_field_keys(self, fields: List[Dict[str, Any]], items: List[Dict[str, str]]) -> None:
        counts: Dict[str, int] = {}
        for row in fields:
            field_key = str(row.get("field_key", "") or "")
            counts[field_key] = counts.get(field_key, 0) + 1
        duplicates = sorted(key for key, count in counts.items() if key and count > 1)
        if duplicates:
            self._add(items, "error", "字段编码重复", "重复字段：{}".format(", ".join(duplicates)))
        else:
            self._add(items, "ok", "字段编码无重复", "field_definitions 中未发现重复 field_key。")

    def _check_field_basic_rules(
        self,
        fields: List[Dict[str, Any]],
        visible_pages_by_field: Dict[str, List[str]],
        items: List[Dict[str, str]],
    ) -> None:
        bad_keys = []
        empty_labels = []
        lonely_fields = []
        numeric_without_aggregation = []
        text_numeric_aggregation = []
        bad_formula_fields = []

        for row in fields:
            field_key = str(row.get("field_key", "") or "")
            label = str(row.get("label", "") or "")
            data_type = str(row.get("data_type", "") or "")
            category = str(row.get("category", "") or "")
            aggregation = str(row.get("aggregation", "") or "")
            formula_id = str(row.get("formula_id", "") or "")
            enabled = int(row.get("enabled", 0) or 0) == 1
            if field_key and not FIELD_KEY_RE.match(field_key):
                bad_keys.append(field_key)
            if not label.strip():
                empty_labels.append(field_key or "(空编码)")
            if enabled and field_key and not visible_pages_by_field.get(field_key):
                lonely_fields.append(field_key)
            if enabled and category == CATEGORY_RAW_DAILY and data_type in NUMERIC_TYPES and aggregation in {"", "none"}:
                numeric_without_aggregation.append(field_key)
            if enabled and data_type in TEXT_TYPES and aggregation in NUMERIC_AGGREGATIONS:
                text_numeric_aggregation.append(field_key)
            if enabled and (category == CATEGORY_FORMULA or aggregation == "formula"):
                if not formula_id or not self.formula_service.is_formula_known(formula_id):
                    bad_formula_fields.append(field_key)

        if bad_keys:
            self._add(items, "error", "字段编码格式错误", "字段编码只能使用小写英文、数字、下划线：{}".format(", ".join(bad_keys)))
        if empty_labels:
            self._add(items, "error", "存在空显示名称", "字段显示名称不能为空：{}".format(", ".join(empty_labels)))
        if lonely_fields:
            self._add(items, "warning", "启用字段未显示在任何页面", "这些字段已启用但没有页面使用：{}".format(", ".join(lonely_fields)))
        if numeric_without_aggregation:
            self._add(items, "warning", "数值字段缺少统计方式", "建议为数值日报字段设置 sum 等统计方式：{}".format(", ".join(numeric_without_aggregation)))
        if text_numeric_aggregation:
            self._add(items, "error", "文本字段使用了数值统计", "文本字段不能使用 sum/avg/max/min：{}".format(", ".join(text_numeric_aggregation)))
        if bad_formula_fields:
            self._add(items, "error", "公式字段缺少有效公式", "请为这些字段选择系统内置公式：{}".format(", ".join(bad_formula_fields)))

    def _check_visibility_references(
        self,
        visibility: List[Dict[str, Any]],
        field_by_key: Dict[str, Dict[str, Any]],
        items: List[Dict[str, str]],
    ) -> None:
        missing = []
        disabled = []
        for row in visibility:
            field_key = str(row.get("field_key", "") or "")
            if not field_key:
                continue
            field = field_by_key.get(field_key)
            if field is None:
                missing.append("{}@{}".format(field_key, row.get("page_key", "")))
                continue
            if int(row.get("visible", 0) or 0) == 1 and int(field.get("enabled", 0) or 0) != 1:
                disabled.append("{}@{}".format(field_key, row.get("page_key", "")))
        if missing:
            self._add(items, "error", "页面配置引用了不存在字段", "无效引用：{}".format(", ".join(missing)))
        if disabled:
            self._add(items, "warning", "页面配置引用了停用字段", "建议关闭这些页面显示项：{}".format(", ".join(disabled)))

    def _check_page_semantics(
        self,
        visibility: List[Dict[str, Any]],
        field_by_key: Dict[str, Dict[str, Any]],
        items: List[Dict[str, str]],
    ) -> None:
        query_non_aggregatable = []
        analysis_text = []
        entry_formula = []
        for row in visibility:
            if int(row.get("visible", 0) or 0) != 1:
                continue
            page_key = str(row.get("page_key", "") or "")
            field_key = str(row.get("field_key", "") or "")
            field = field_by_key.get(field_key)
            if not field or int(field.get("enabled", 0) or 0) != 1:
                continue
            data_type = str(field.get("data_type", "") or "")
            category = str(field.get("category", "") or "")
            aggregation = str(field.get("aggregation", "") or "")
            if page_key == PAGE_QUERY_SUMMARY and data_type in TEXT_TYPES and aggregation != "latest":
                query_non_aggregatable.append(field_key)
            if page_key == PAGE_ANALYSIS and data_type in TEXT_TYPES:
                analysis_text.append(field_key)
            if page_key == PAGE_DATA_ENTRY and category == CATEGORY_FORMULA:
                entry_formula.append(field_key)

        if query_non_aggregatable:
            self._add(items, "warning", "查询汇总包含不适合聚合的文本字段", "建议关闭或改为 latest：{}".format(", ".join(query_non_aggregatable)))
        if analysis_text:
            self._add(items, "warning", "数据分析包含文本字段", "文本字段无法做数值分析：{}".format(", ".join(analysis_text)))
        if entry_formula:
            self._add(items, "error", "数据录入包含公式字段", "公式字段不应作为普通录入项：{}".format(", ".join(entry_formula)))

    def _check_png_templates(
        self,
        templates: List[Dict[str, Any]],
        field_by_key: Dict[str, Dict[str, Any]],
        items: List[Dict[str, str]],
    ) -> None:
        for template in templates:
            if str(template.get("page_key", "") or "") != PAGE_PNG_TODAY:
                continue
            template_key = str(template.get("template_key", "") or "")
            try:
                payload = json.loads(str(template.get("config_json", "{}") or "{}"))
            except ValueError as exc:
                self._add(items, "error", "PNG 模板 JSON 损坏", "{}：{}".format(template_key, exc))
                continue
            sections = payload.get("sections", [])
            if not isinstance(sections, list):
                self._add(items, "error", "PNG 模板缺少分图配置", "{} 缺少 sections 数组。".format(template_key))
                continue
            for section in sections:
                if not isinstance(section, dict):
                    self._add(items, "error", "PNG 分图配置格式错误", "{} 存在非对象 section。".format(template_key))
                    continue
                title = str(section.get("title") or section.get("key") or "未命名分图")
                field_keys = section.get("field_keys", [])
                if not isinstance(field_keys, list):
                    self._add(items, "error", "PNG 分图字段格式错误", "{} / {} 的 field_keys 不是数组。".format(template_key, title))
                    continue
                if len(field_keys) > 14:
                    self._add(
                        items,
                        "warning",
                        "PNG 分图字段过多",
                        "{} / {} 有 {} 个字段，建议控制在 14 个以内。".format(template_key, title, len(field_keys)),
                    )
                missing = [str(field_key) for field_key in field_keys if str(field_key) not in field_by_key]
                if missing:
                    self._add(
                        items,
                        "error",
                        "PNG 模板引用不存在字段",
                        "{} / {}：{}".format(template_key, title, ", ".join(missing)),
                    )
