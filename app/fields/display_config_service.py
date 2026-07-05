from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from app.config.field_profiles import get_profile_field_keys
from app.config.field_registry import get_field_spec
from app.utils.log_utils import get_logger


class DisplayFieldConfigService:
    """Read page display fields from database config with legacy-profile fallback."""

    def __init__(self, db_manager: Any) -> None:
        self.db_manager = db_manager
        self.logger = get_logger("display_config_service")

    def get_page_fields(
        self,
        page_key: str,
        fallback_profile_key: str,
        template_key: str = "",
    ) -> List[Dict[str, Any]]:
        rows = self._rows_from_visibility(page_key)
        if rows:
            return rows

        if template_key:
            rows = self._rows_from_template(template_key)
            if rows:
                return rows

        return self._rows_from_profile(fallback_profile_key)

    def get_page_fields_with_fallback_keys(
        self,
        page_key: str,
        fallback_field_keys: Iterable[str],
        template_key: str = "",
    ) -> List[Dict[str, Any]]:
        rows = self._rows_from_visibility(page_key)
        if rows:
            return rows

        if template_key:
            rows = self._rows_from_template(template_key)
            if rows:
                return rows

        return self._rows_from_field_keys(fallback_field_keys)

    def _rows_from_visibility(self, page_key: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT
                fd.*,
                fpv.page_key,
                fpv.visible,
                fpv.group_key AS page_group_key,
                fpv.display_order
            FROM field_page_visibility fpv
            JOIN field_definitions fd ON fd.field_key = fpv.field_key
            WHERE fpv.page_key = ?
              AND fpv.visible = 1
              AND fd.enabled = 1
            ORDER BY fpv.display_order ASC, fd.id ASC
        """
        try:
            with self.db_manager.get_connection() as conn:
                return [dict(row) for row in conn.execute(sql, (page_key,)).fetchall()]
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("读取页面字段配置失败 page=%s，回退默认配置: %s", page_key, exc)
            return []

    def _rows_from_template(self, template_key: str) -> List[Dict[str, Any]]:
        try:
            with self.db_manager.get_connection() as conn:
                template = conn.execute(
                    """
                    SELECT config_json
                    FROM view_templates
                    WHERE template_key = ?
                      AND enabled = 1
                    LIMIT 1
                    """,
                    (template_key,),
                ).fetchone()
                if template is None:
                    return []
                payload = json.loads(str(template["config_json"] or "{}"))
                field_keys = self._field_keys_from_template_payload(payload)
                if not field_keys:
                    return []
                placeholders = ",".join(["?" for _ in field_keys])
                rows_by_key = {
                    str(row["field_key"]): dict(row)
                    for row in conn.execute(
                        """
                        SELECT *
                        FROM field_definitions
                        WHERE field_key IN ({})
                          AND enabled = 1
                        """.format(placeholders),
                        field_keys,
                    ).fetchall()
                }
                result = []
                for index, field_key in enumerate(field_keys, start=1):
                    row = rows_by_key.get(field_key)
                    if row is None:
                        self.logger.warning("模板字段不存在或已停用 template=%s field=%s，已跳过", template_key, field_key)
                        continue
                    row["display_order"] = index
                    result.append(row)
                return result
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("读取模板字段配置失败 template=%s，回退默认配置: %s", template_key, exc)
            return []

    @staticmethod
    def _field_keys_from_template_payload(payload: Dict[str, Any]) -> List[str]:
        field_keys = payload.get("field_keys", [])
        if isinstance(field_keys, list):
            return [str(item) for item in field_keys if str(item).strip()]

        metric_field_keys = payload.get("metric_field_keys", [])
        if isinstance(metric_field_keys, list):
            return [str(item) for item in metric_field_keys if str(item).strip()]

        sections = payload.get("sections", [])
        if isinstance(sections, list):
            result = []
            for section in sections:
                if not isinstance(section, dict):
                    continue
                section_keys = section.get("field_keys", [])
                if isinstance(section_keys, list):
                    result.extend(str(item) for item in section_keys if str(item).strip())
            return result
        return []

    @staticmethod
    def _rows_from_profile(profile_key: str) -> List[Dict[str, Any]]:
        rows = []
        for index, field_key in enumerate(get_profile_field_keys(profile_key), start=1):
            spec = get_field_spec(field_key)
            rows.append(field_spec_to_display_row(spec, display_order=index))
        return rows

    @staticmethod
    def _rows_from_field_keys(field_keys: Iterable[str]) -> List[Dict[str, Any]]:
        rows = []
        for index, field_key in enumerate(field_keys, start=1):
            spec = get_field_spec(str(field_key))
            rows.append(field_spec_to_display_row(spec, display_order=index))
        return rows


def field_spec_to_display_row(spec: Any, display_order: int = 0) -> Dict[str, Any]:
    return {
        "field_key": spec.field_key,
        "label": spec.label,
        "data_type": spec.data_type,
        "category": spec.category,
        "group_key": spec.group_key,
        "editable": 1 if spec.editable else 0,
        "required": 1 if spec.required else 0,
        "default_value": "" if spec.default_value is None else str(spec.default_value),
        "aggregation": spec.aggregation,
        "formula_id": spec.formula_id,
        "enabled": 1 if spec.enabled else 0,
        "system_field": 1 if spec.system_field else 0,
        "storage_type": spec.storage_type,
        "storage_column": spec.storage_column,
        "display_order": display_order,
    }


def field_keys(rows: Iterable[Dict[str, Any]]) -> List[str]:
    return [str(row.get("field_key", "")) for row in rows if str(row.get("field_key", "")).strip()]
