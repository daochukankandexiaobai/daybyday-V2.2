from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config.field_registry import (
    CATEGORY_CUMULATIVE,
    CATEGORY_DISPLAY,
    CATEGORY_FORMULA,
    CATEGORY_RAW_DAILY,
    DATA_TYPE_AMOUNT,
    DATA_TYPE_DATE,
    DATA_TYPE_INT,
    DATA_TYPE_PERCENT,
    DATA_TYPE_TEXT,
    DATA_TYPE_TEXTAREA,
    STORAGE_COMPUTED,
    STORAGE_DISPLAY_ONLY,
    STORAGE_DYNAMIC_METRIC,
)
from app.fields.registry import (
    PAGE_ANALYSIS,
    PAGE_DATA_ENTRY,
    PAGE_EXCEL_EXPORT,
    PAGE_JSON_EXPORT,
    PAGE_PNG_TODAY,
    PAGE_QUERY_SUMMARY,
    PAGE_TODAY_DISPLAY,
    build_default_field_rows,
    build_default_page_visibility_rows,
    build_default_view_template_rows,
)
from app.fields.formula_service import FormulaService
from app.services.field_config_health_service import FieldConfigHealthService


FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

DATA_TYPES = (
    DATA_TYPE_INT,
    DATA_TYPE_AMOUNT,
    "money",
    "decimal",
    DATA_TYPE_PERCENT,
    DATA_TYPE_TEXT,
    DATA_TYPE_TEXTAREA,
    DATA_TYPE_DATE,
)
CATEGORIES = (CATEGORY_RAW_DAILY, CATEGORY_CUMULATIVE, CATEGORY_FORMULA, CATEGORY_DISPLAY, "config")
AGGREGATIONS = ("none", "sum", "avg", "max", "min", "latest", "count", "derived", "formula")
NUMERIC_TYPES = {DATA_TYPE_INT, DATA_TYPE_AMOUNT, "money", "decimal", DATA_TYPE_PERCENT}
NUMERIC_AGGREGATIONS = {"sum", "avg", "max", "min"}
PAGE_KEYS = (
    PAGE_DATA_ENTRY,
    PAGE_TODAY_DISPLAY,
    PAGE_QUERY_SUMMARY,
    PAGE_ANALYSIS,
    PAGE_PNG_TODAY,
    PAGE_EXCEL_EXPORT,
    PAGE_JSON_EXPORT,
)


def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


class FieldAdminConfigService:
    """Admin-facing field and report configuration service."""

    def __init__(self, db_manager: Any, admin_action_log_service: Optional[Any] = None) -> None:
        self.db_manager = db_manager
        self.admin_action_log_service = admin_action_log_service
        self.formula_service = FormulaService()
        self.health_service = FieldConfigHealthService(db_manager, self.formula_service)

    def get_config_overview(self) -> Dict[str, Any]:
        health = self.health_service.run_checks()
        with self.db_manager.get_connection() as conn:
            enabled_field_count = self._count_scalar(
                conn,
                "SELECT COUNT(1) AS c FROM field_definitions WHERE enabled = 1",
            )
            entry_field_count = self._count_visible_fields(conn, PAGE_DATA_ENTRY)
            today_field_count = self._count_visible_fields(conn, PAGE_TODAY_DISPLAY)
            query_field_count = self._count_visible_fields(conn, PAGE_QUERY_SUMMARY)
            analysis_field_count = self._count_visible_fields(conn, PAGE_ANALYSIS)
            png_template_count = self._count_scalar(
                conn,
                "SELECT COUNT(1) AS c FROM view_templates WHERE page_key = ? AND enabled = 1",
                (PAGE_PNG_TODAY,),
            )
            latest = self._latest_config_log(conn)
        return {
            "enabled_field_count": enabled_field_count,
            "entry_field_count": entry_field_count,
            "today_field_count": today_field_count,
            "query_field_count": query_field_count,
            "analysis_field_count": analysis_field_count,
            "png_template_count": png_template_count,
            "latest_action_time": latest.get("action_time", ""),
            "latest_operator": latest.get("operator", ""),
            "latest_action_type": latest.get("action_type", ""),
            "health": health["summary"],
            "backup_status": "可导出配置备份",
            "version_status": "版本记录将在后续阶段启用",
        }

    def run_config_health_check(self, operator: str = "admin") -> Dict[str, Any]:
        result = self.health_service.run_checks()
        self._log(
            "check_field_config_health",
            "all",
            operator,
            None,
            {
                "summary": result.get("summary", {}),
            },
        )
        return result

    def export_field_config_to_json(self, path: str, operator: str = "admin") -> Tuple[bool, str]:
        target = Path(path)
        payload = {
            "metadata": {
                "type": "daybyday_field_config",
                "version": 1,
                "exported_at": _now_str(),
            },
            "field_definitions": self.list_fields(include_disabled=True),
            "field_page_visibility": self._list_all_page_visibility(),
            "view_templates": self.list_templates(),
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return False, "字段配置导出失败: {}".format(exc)
        self._log("export_field_config", str(target), operator, None, {"path": str(target)})
        return True, str(target)

    def import_field_config_from_json(self, path: str, operator: str = "admin") -> Tuple[bool, str]:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return False, "字段配置导入读取失败: {}".format(exc)

        if not isinstance(payload, dict):
            return False, "字段配置文件格式错误"
        field_rows = payload.get("field_definitions", [])
        visibility_rows = payload.get("field_page_visibility", [])
        template_rows = payload.get("view_templates", [])
        if not isinstance(field_rows, list) or not isinstance(visibility_rows, list) or not isinstance(template_rows, list):
            return False, "字段配置文件缺少必要数组"

        before = {
            "field_count": len(self.list_fields(include_disabled=True)),
            "visibility_count": len(self._list_all_page_visibility()),
            "template_count": len(self.list_templates()),
        }
        now = _now_str()
        try:
            with self.db_manager.get_connection() as conn:
                for row in field_rows:
                    if not isinstance(row, dict):
                        continue
                    normalized = self._normalize_field_payload(row, create=False)
                    ok, message = self._validate_field_payload(normalized, create=not bool(self.get_field(normalized["field_key"])))
                    if not ok:
                        return False, "字段 {} 配置无效: {}".format(normalized.get("field_key", ""), message)
                    existing = conn.execute(
                        "SELECT system_field, storage_type, storage_column FROM field_definitions WHERE field_key = ?",
                        (normalized["field_key"],),
                    ).fetchone()
                    system_field = int(row.get("system_field", 0) or 0)
                    storage_type = normalized["storage_type"]
                    storage_column = str(row.get("storage_column", "") or "")
                    if existing is not None:
                        system_field = 1 if int(existing["system_field"] or 0) == 1 else system_field
                        if int(existing["system_field"] or 0) == 1:
                            storage_type = str(existing["storage_type"] or storage_type)
                            storage_column = str(existing["storage_column"] or storage_column)
                    conn.execute(
                        """
                        INSERT INTO field_definitions (
                            field_key, label, data_type, category, group_key,
                            editable, required, default_value, aggregation, formula_id,
                            enabled, system_field, storage_type, storage_column, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(field_key) DO UPDATE SET
                            label = excluded.label,
                            data_type = CASE WHEN field_definitions.system_field = 1 THEN field_definitions.data_type ELSE excluded.data_type END,
                            category = excluded.category,
                            group_key = excluded.group_key,
                            editable = excluded.editable,
                            required = excluded.required,
                            default_value = excluded.default_value,
                            aggregation = excluded.aggregation,
                            formula_id = excluded.formula_id,
                            enabled = excluded.enabled,
                            system_field = CASE WHEN field_definitions.system_field = 1 THEN 1 ELSE excluded.system_field END,
                            storage_type = CASE WHEN field_definitions.system_field = 1 THEN field_definitions.storage_type ELSE excluded.storage_type END,
                            storage_column = CASE WHEN field_definitions.system_field = 1 THEN field_definitions.storage_column ELSE excluded.storage_column END,
                            updated_at = excluded.updated_at
                        """,
                        (
                            normalized["field_key"],
                            normalized["label"],
                            normalized["data_type"],
                            normalized["category"],
                            normalized["group_key"],
                            normalized["editable"],
                            normalized["required"],
                            normalized["default_value"],
                            normalized["aggregation"],
                            normalized["formula_id"],
                            normalized["enabled"],
                            system_field,
                            storage_type,
                            storage_column,
                            now,
                            now,
                        ),
                    )

                conn.execute("DELETE FROM field_page_visibility")
                for row in visibility_rows:
                    if not isinstance(row, dict):
                        continue
                    field_key = str(row.get("field_key", "")).strip()
                    page_key = self._normalize_page_key(str(row.get("page_key", "")).strip())
                    if not field_key or not page_key:
                        continue
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO field_page_visibility (
                            field_key, page_key, visible, group_key, display_order, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            field_key,
                            page_key,
                            1 if int(row.get("visible", 1) or 0) else 0,
                            str(row.get("group_key", "") or ""),
                            int(row.get("display_order", 0) or 0),
                            now,
                            now,
                        ),
                    )

                for row in template_rows:
                    if not isinstance(row, dict):
                        continue
                    template_key = str(row.get("template_key", "")).strip()
                    if not template_key:
                        continue
                    json.loads(str(row.get("config_json", "{}") or "{}"))
                    conn.execute(
                        """
                        INSERT INTO view_templates (
                            template_key, template_name, page_key, config_json,
                            is_default, enabled, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(template_key) DO UPDATE SET
                            template_name = excluded.template_name,
                            page_key = excluded.page_key,
                            config_json = excluded.config_json,
                            is_default = excluded.is_default,
                            enabled = excluded.enabled,
                            updated_at = excluded.updated_at
                        """,
                        (
                            template_key,
                            str(row.get("template_name", template_key) or template_key),
                            self._normalize_page_key(str(row.get("page_key", "") or "")),
                            str(row.get("config_json", "{}") or "{}"),
                            int(row.get("is_default", 0) or 0),
                            int(row.get("enabled", 1) or 0),
                            now,
                            now,
                        ),
                    )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            return False, "字段配置导入失败: {}".format(exc)

        after = {
            "field_count": len(self.list_fields(include_disabled=True)),
            "visibility_count": len(self._list_all_page_visibility()),
            "template_count": len(self.list_templates()),
        }
        self._log("import_field_config", str(source), operator, before, after)
        return True, "字段配置已导入"

    def reset_field_config_to_default(self, operator: str = "admin") -> Tuple[bool, str]:
        before = {
            "field_count": len(self.list_fields(include_disabled=True)),
            "visibility_count": len(self._list_all_page_visibility()),
            "template_count": len(self.list_templates()),
        }
        now = _now_str()
        try:
            with self.db_manager.get_connection() as conn:
                conn.execute("UPDATE field_definitions SET enabled = 0, updated_at = ? WHERE system_field = 0", (now,))
                for row in build_default_field_rows():
                    conn.execute(
                        """
                        INSERT INTO field_definitions (
                            field_key, label, data_type, category, group_key,
                            editable, required, default_value, aggregation, formula_id,
                            enabled, system_field, storage_type, storage_column, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                        ON CONFLICT(field_key) DO UPDATE SET
                            label = excluded.label,
                            category = excluded.category,
                            group_key = excluded.group_key,
                            editable = excluded.editable,
                            required = excluded.required,
                            default_value = excluded.default_value,
                            aggregation = excluded.aggregation,
                            formula_id = excluded.formula_id,
                            enabled = excluded.enabled,
                            system_field = 1,
                            updated_at = excluded.updated_at
                        """,
                        (
                            row["field_key"],
                            row["label"],
                            row["data_type"],
                            row["category"],
                            row.get("group_key", ""),
                            int(row.get("editable", 0) or 0),
                            int(row.get("required", 0) or 0),
                            row.get("default_value", ""),
                            row.get("aggregation", "none"),
                            row.get("formula_id", ""),
                            int(row.get("enabled", 1) or 0),
                            row.get("storage_type", "display_only"),
                            row.get("storage_column", ""),
                            now,
                            now,
                        ),
                    )
                conn.execute("DELETE FROM field_page_visibility")
                for row in build_default_page_visibility_rows():
                    conn.execute(
                        """
                        INSERT INTO field_page_visibility (
                            field_key, page_key, visible, group_key, display_order, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(field_key, page_key) DO UPDATE SET
                            visible = excluded.visible,
                            group_key = excluded.group_key,
                            display_order = excluded.display_order,
                            updated_at = excluded.updated_at
                        """,
                        (
                            row["field_key"],
                            row["page_key"],
                            int(row.get("visible", 1) or 0),
                            row.get("group_key", ""),
                            int(row.get("display_order", 0) or 0),
                            now,
                            now,
                        ),
                    )
                conn.execute("DELETE FROM view_templates")
                for row in build_default_view_template_rows():
                    conn.execute(
                        """
                        INSERT INTO view_templates (
                            template_key, template_name, page_key, config_json,
                            is_default, enabled, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["template_key"],
                            row["template_name"],
                            row["page_key"],
                            row["config_json"],
                            int(row.get("is_default", 0) or 0),
                            int(row.get("enabled", 1) or 0),
                            now,
                            now,
                        ),
                    )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            return False, "恢复默认字段配置失败: {}".format(exc)
        after = {
            "field_count": len(self.list_fields(include_disabled=True)),
            "visibility_count": len(self._list_all_page_visibility()),
            "template_count": len(self.list_templates()),
        }
        self._log("reset_field_config_default", "all", operator, before, after)
        return True, "字段配置已恢复默认"

    @staticmethod
    def _count_scalar(conn: Any, sql: str, params: Tuple[Any, ...] = ()) -> int:
        row = conn.execute(sql, params).fetchone()
        if row is None:
            return 0
        return int(row["c"] or 0)

    def _count_visible_fields(self, conn: Any, page_key: str) -> int:
        return self._count_scalar(
            conn,
            """
            SELECT COUNT(1) AS c
            FROM field_page_visibility fpv
            JOIN field_definitions fd ON fd.field_key = fpv.field_key
            WHERE fpv.page_key = ? AND fpv.visible = 1 AND fd.enabled = 1
            """,
            (page_key,),
        )

    @staticmethod
    def _latest_config_log(conn: Any) -> Dict[str, Any]:
        try:
            row = conn.execute(
                """
                SELECT action_time, operator, action_type
                FROM admin_action_logs
                WHERE target_type = 'field_config'
                ORDER BY action_time DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        except Exception:  # noqa: BLE001
            row = None
        return dict(row) if row is not None else {}

    def list_fields(self, include_disabled: bool = True) -> List[Dict[str, Any]]:
        where = "" if include_disabled else "WHERE enabled = 1"
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM field_definitions
                {}
                ORDER BY system_field DESC, category, group_key, field_key
                """.format(where)
            ).fetchall()
            return [dict(row) for row in rows]

    def _list_all_page_visibility(self) -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM field_page_visibility
                ORDER BY page_key, display_order, field_key
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_field(self, field_key: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM field_definitions WHERE field_key = ?",
                (str(field_key or "").strip(),),
            ).fetchone()
            return dict(row) if row is not None else None

    def create_field(self, payload: Dict[str, Any], operator: str = "admin") -> Tuple[bool, str]:
        normalized = self._normalize_field_payload(payload, create=True)
        ok, message = self._validate_field_payload(normalized, create=True)
        if not ok:
            return False, message

        now = _now_str()
        with self.db_manager.get_connection() as conn:
            exists = conn.execute(
                "SELECT id FROM field_definitions WHERE field_key = ?",
                (normalized["field_key"],),
            ).fetchone()
            if exists is not None:
                return False, "字段编码已存在"

            conn.execute(
                """
                INSERT INTO field_definitions (
                    field_key, label, data_type, category, group_key,
                    editable, required, default_value, aggregation, formula_id,
                    enabled, system_field, storage_type, storage_column,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, '', ?, ?)
                """,
                (
                    normalized["field_key"],
                    normalized["label"],
                    normalized["data_type"],
                    normalized["category"],
                    normalized["group_key"],
                    normalized["editable"],
                    normalized["required"],
                    normalized["default_value"],
                    normalized["aggregation"],
                    normalized["formula_id"],
                    normalized["enabled"],
                    normalized["storage_type"],
                    now,
                    now,
                ),
            )
            conn.commit()

        self._log("create_field", normalized["field_key"], operator, None, normalized)
        return True, "字段已新增"

    def update_field(self, field_key: str, payload: Dict[str, Any], operator: str = "admin") -> Tuple[bool, str]:
        existing = self.get_field(field_key)
        if existing is None:
            return False, "字段不存在"

        normalized = self._normalize_field_payload(payload, create=False, existing=existing)
        ok, message = self._validate_field_payload(normalized, create=False, existing=existing)
        if not ok:
            return False, message

        if int(existing.get("system_field", 0) or 0) == 1:
            normalized["data_type"] = str(existing.get("data_type") or normalized["data_type"])
            normalized["storage_type"] = str(existing.get("storage_type") or normalized["storage_type"])

        now = _now_str()
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                UPDATE field_definitions
                SET label = ?,
                    data_type = ?,
                    category = ?,
                    group_key = ?,
                    editable = ?,
                    required = ?,
                    default_value = ?,
                    aggregation = ?,
                    formula_id = ?,
                    enabled = ?,
                    storage_type = ?,
                    updated_at = ?
                WHERE field_key = ?
                """,
                (
                    normalized["label"],
                    normalized["data_type"],
                    normalized["category"],
                    normalized["group_key"],
                    normalized["editable"],
                    normalized["required"],
                    normalized["default_value"],
                    normalized["aggregation"],
                    normalized["formula_id"],
                    normalized["enabled"],
                    normalized["storage_type"],
                    now,
                    str(field_key),
                ),
            )
            conn.commit()

        self._log("update_field", str(field_key), operator, existing, normalized)
        return True, "字段已保存"

    def disable_field(self, field_key: str, operator: str = "admin") -> Tuple[bool, str]:
        existing = self.get_field(field_key)
        if existing is None:
            return False, "字段不存在"
        now = _now_str()
        with self.db_manager.get_connection() as conn:
            conn.execute(
                "UPDATE field_definitions SET enabled = 0, updated_at = ? WHERE field_key = ?",
                (now, field_key),
            )
            conn.commit()
        after = dict(existing)
        after["enabled"] = 0
        self._log("disable_field", field_key, operator, existing, after)
        return True, "字段已停用，历史数据不会删除"

    def list_page_config(self, page_key: str) -> List[Dict[str, Any]]:
        normalized_page = self._normalize_page_key(page_key)
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    fd.field_key,
                    fd.label,
                    fd.data_type,
                    fd.category,
                    fd.group_key AS field_group_key,
                    fd.enabled,
                    fd.system_field,
                    COALESCE(fpv.visible, 0) AS visible,
                    COALESCE(fpv.group_key, fd.group_key, '') AS group_key,
                    COALESCE(fpv.display_order, 0) AS display_order
                FROM field_definitions fd
                LEFT JOIN field_page_visibility fpv
                  ON fpv.field_key = fd.field_key AND fpv.page_key = ?
                WHERE fd.enabled = 1
                ORDER BY COALESCE(fpv.display_order, 999999), fd.system_field DESC, fd.field_key
                """,
                (normalized_page,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_field_visibility_map(self, field_key: str) -> Dict[str, int]:
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT page_key, visible
                FROM field_page_visibility
                WHERE field_key = ?
                """,
                (str(field_key or "").strip(),),
            ).fetchall()
            return {str(row["page_key"]): int(row["visible"] or 0) for row in rows}

    def save_field_visibility(
        self,
        field_key: str,
        visibility_by_page: Dict[str, int],
        operator: str = "admin",
    ) -> Tuple[bool, str]:
        field = self.get_field(field_key)
        if field is None:
            return False, "字段不存在"
        before = self.get_field_visibility_map(field_key)
        now = _now_str()
        with self.db_manager.get_connection() as conn:
            for page_key, visible in visibility_by_page.items():
                normalized_page = self._normalize_page_key(page_key)
                existing = conn.execute(
                    """
                    SELECT display_order, group_key
                    FROM field_page_visibility
                    WHERE field_key = ? AND page_key = ?
                    """,
                    (field_key, normalized_page),
                ).fetchone()
                if existing is not None:
                    display_order = int(existing["display_order"] or 0)
                    group_key = str(existing["group_key"] or field.get("group_key") or "")
                else:
                    max_row = conn.execute(
                        """
                        SELECT MAX(display_order) AS max_order
                        FROM field_page_visibility
                        WHERE page_key = ?
                        """,
                        (normalized_page,),
                    ).fetchone()
                    display_order = int((max_row["max_order"] if max_row is not None else 0) or 0) + 1
                    group_key = str(field.get("group_key") or "")
                conn.execute(
                    """
                    INSERT INTO field_page_visibility (
                        field_key, page_key, visible, group_key, display_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(field_key, page_key) DO UPDATE SET
                        visible = excluded.visible,
                        updated_at = excluded.updated_at
                    """,
                    (
                        field_key,
                        normalized_page,
                        1 if int(visible or 0) else 0,
                        group_key,
                        display_order,
                        now,
                        now,
                    ),
                )
            conn.commit()
        after = self.get_field_visibility_map(field_key)
        self._log("save_field_visibility", field_key, operator, before, after)
        return True, "字段显示位置已保存"

    def save_page_config(
        self,
        page_key: str,
        rows: Iterable[Dict[str, Any]],
        operator: str = "admin",
    ) -> Tuple[bool, str]:
        normalized_page = self._normalize_page_key(page_key)
        now = _now_str()
        normalized_rows = []
        order = 1
        for row in rows:
            field_key = str(row.get("field_key", "")).strip()
            if not field_key:
                continue
            visible = 1 if int(row.get("visible", 0) or 0) else 0
            group_key = str(row.get("group_key", "") or "").strip()
            normalized_rows.append(
                {
                    "field_key": field_key,
                    "page_key": normalized_page,
                    "visible": visible,
                    "group_key": group_key,
                    "display_order": order,
                }
            )
            order += 1

        before = self.list_page_config(normalized_page)
        with self.db_manager.get_connection() as conn:
            for row in normalized_rows:
                conn.execute(
                    """
                    INSERT INTO field_page_visibility (
                        field_key, page_key, visible, group_key, display_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(field_key, page_key) DO UPDATE SET
                        visible = excluded.visible,
                        group_key = excluded.group_key,
                        display_order = excluded.display_order,
                        updated_at = excluded.updated_at
                    """,
                    (
                        row["field_key"],
                        row["page_key"],
                        row["visible"],
                        row["group_key"],
                        row["display_order"],
                        now,
                        now,
                    ),
                )
            conn.commit()
        self._log("save_page_config", normalized_page, operator, {"rows": before}, {"rows": normalized_rows})
        return True, "页面字段配置已保存"

    def restore_default_page_config(self, page_key: str, operator: str = "admin") -> Tuple[bool, str]:
        normalized_page = self._normalize_page_key(page_key)
        default_rows = [row for row in build_default_page_visibility_rows() if row["page_key"] == normalized_page]
        if not default_rows:
            return False, "该页面没有默认字段配置"
        before = self.list_page_config(normalized_page)
        now = _now_str()
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM field_page_visibility WHERE page_key = ?", (normalized_page,))
            for row in default_rows:
                conn.execute(
                    """
                    INSERT INTO field_page_visibility (
                        field_key, page_key, visible, group_key, display_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["field_key"],
                        row["page_key"],
                        int(row.get("visible", 1) or 0),
                        row.get("group_key", ""),
                        int(row.get("display_order", 0) or 0),
                        now,
                        now,
                    ),
                )
            conn.commit()
        self._log("restore_page_config", normalized_page, operator, {"rows": before}, {"rows": default_rows})
        return True, "已恢复默认页面配置"

    def list_templates(self, page_key: str = "") -> List[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            if page_key:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM view_templates
                    WHERE page_key = ?
                    ORDER BY is_default DESC, template_key
                    """,
                    (page_key,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM view_templates
                    ORDER BY page_key, is_default DESC, template_key
                    """
                ).fetchall()
            return [dict(row) for row in rows]

    def get_template(self, template_key: str) -> Optional[Dict[str, Any]]:
        with self.db_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM view_templates WHERE template_key = ?",
                (str(template_key or "").strip(),),
            ).fetchone()
            return dict(row) if row is not None else None

    def save_template_config(
        self,
        template_key: str,
        config_json: str,
        operator: str = "admin",
    ) -> Tuple[bool, str]:
        template = self.get_template(template_key)
        if template is None:
            return False, "模板不存在"
        try:
            payload = json.loads(config_json or "{}")
        except ValueError as exc:
            return False, "模板 JSON 格式错误: {}".format(exc)

        ok, message = self._validate_png_template(payload) if str(template.get("page_key")) == PAGE_PNG_TODAY else (True, "")
        if not ok:
            return False, message

        normalized_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        now = _now_str()
        with self.db_manager.get_connection() as conn:
            conn.execute(
                "UPDATE view_templates SET config_json = ?, updated_at = ? WHERE template_key = ?",
                (normalized_json, now, template_key),
            )
            conn.commit()
        after = dict(template)
        after["config_json"] = normalized_json
        self._log("save_template", template_key, operator, template, after)
        return True, "模板配置已保存"

    def restore_default_template(self, template_key: str, operator: str = "admin") -> Tuple[bool, str]:
        template = self.get_template(template_key)
        default_rows = {
            str(row["template_key"]): row for row in build_default_view_template_rows()
        }
        default = default_rows.get(str(template_key))
        if template is None or default is None:
            return False, "模板不存在或没有默认值"
        now = _now_str()
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                UPDATE view_templates
                SET config_json = ?, enabled = ?, is_default = ?, updated_at = ?
                WHERE template_key = ?
                """,
                (
                    default["config_json"],
                    int(default.get("enabled", 1) or 0),
                    int(default.get("is_default", 0) or 0),
                    now,
                    template_key,
                ),
            )
            conn.commit()
        self._log("restore_template", template_key, operator, template, default)
        return True, "模板已恢复默认"

    def _normalize_field_payload(
        self,
        payload: Dict[str, Any],
        create: bool,
        existing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        category = str(payload.get("category") or (existing or {}).get("category") or CATEGORY_RAW_DAILY).strip()
        data_type = str(payload.get("data_type") or (existing or {}).get("data_type") or DATA_TYPE_INT).strip()
        aggregation = str(payload.get("aggregation") or (existing or {}).get("aggregation") or "sum").strip()
        field_key = str(payload.get("field_key") or (existing or {}).get("field_key") or "").strip()
        storage_type = str((existing or {}).get("storage_type") or "").strip()
        if create or not storage_type:
            storage_type = self._default_storage_type(category, aggregation)
        return {
            "field_key": field_key,
            "label": str(payload.get("label") or (existing or {}).get("label") or field_key).strip(),
            "data_type": data_type,
            "category": category,
            "group_key": str(payload.get("group_key") or (existing or {}).get("group_key") or "process_behavior").strip(),
            "editable": 1 if int(payload.get("editable", (existing or {}).get("editable", 1)) or 0) else 0,
            "required": 1 if int(payload.get("required", (existing or {}).get("required", 0)) or 0) else 0,
            "default_value": str(payload.get("default_value", (existing or {}).get("default_value", ""))),
            "aggregation": aggregation,
            "formula_id": str(payload.get("formula_id") or (existing or {}).get("formula_id") or "").strip(),
            "enabled": 1 if int(payload.get("enabled", (existing or {}).get("enabled", 1)) or 0) else 0,
            "storage_type": storage_type,
        }

    def _validate_field_payload(
        self,
        payload: Dict[str, Any],
        create: bool,
        existing: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        field_key = payload["field_key"]
        if create and not FIELD_KEY_RE.match(field_key):
            return False, "字段编码只能使用英文小写、数字、下划线，并以英文开头"
        if not payload["label"]:
            return False, "字段名称不能为空"
        if payload["data_type"] not in DATA_TYPES:
            return False, "字段类型不支持"
        if payload["category"] not in CATEGORIES:
            return False, "字段分类不支持"
        if payload["aggregation"] not in AGGREGATIONS:
            return False, "统计方式不支持"
        if payload["aggregation"] in NUMERIC_AGGREGATIONS and payload["data_type"] not in NUMERIC_TYPES:
            return False, "sum/avg/max/min 只能用于数值字段"
        if payload["data_type"] == DATA_TYPE_TEXT and payload["category"] == CATEGORY_FORMULA:
            return False, "文本字段不能作为公式字段"
        if payload["aggregation"] == "formula":
            formula_id = payload["formula_id"]
            if not formula_id or not self.formula_service.is_formula_known(formula_id):
                return False, "公式字段只能选择系统内置公式"
        if payload["data_type"] in NUMERIC_TYPES:
            try:
                if str(payload["default_value"]).strip():
                    float(payload["default_value"])
            except (TypeError, ValueError):
                return False, "数值字段默认值必须是数字"
        if existing and int(existing.get("system_field", 0) or 0) == 1:
            if payload["field_key"] != str(existing.get("field_key")):
                return False, "系统字段编码不可修改"
        return True, ""

    @staticmethod
    def _default_storage_type(category: str, aggregation: str) -> str:
        if category == CATEGORY_RAW_DAILY:
            return STORAGE_DYNAMIC_METRIC
        if category in {CATEGORY_CUMULATIVE, CATEGORY_FORMULA} or aggregation in {"derived", "formula"}:
            return STORAGE_COMPUTED
        return STORAGE_DISPLAY_ONLY

    @staticmethod
    def _normalize_page_key(page_key: str) -> str:
        normalized = str(page_key or "").strip()
        aliases = {
            "entry": PAGE_DATA_ENTRY,
            "data_entry": PAGE_DATA_ENTRY,
            "today": PAGE_TODAY_DISPLAY,
            "today_display": PAGE_TODAY_DISPLAY,
            "query": PAGE_QUERY_SUMMARY,
            "query_summary": PAGE_QUERY_SUMMARY,
            "analysis": PAGE_ANALYSIS,
            "png_today": PAGE_PNG_TODAY,
            "excel_export": PAGE_EXCEL_EXPORT,
            "json_export": PAGE_JSON_EXPORT,
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _validate_png_template(payload: Dict[str, Any]) -> Tuple[bool, str]:
        sections = payload.get("sections", [])
        if not isinstance(sections, list):
            return False, "PNG 模板必须包含 sections 数组"
        for section in sections:
            if not isinstance(section, dict):
                return False, "PNG sections 项必须是对象"
            field_keys = section.get("field_keys", [])
            if not isinstance(field_keys, list):
                return False, "PNG 分图 field_keys 必须是数组"
            if len(field_keys) > 14:
                return False, "每张 PNG 分图字段数建议不超过 14 个，请减少字段"
        return True, ""

    def _log(
        self,
        action_type: str,
        target_id: str,
        operator: str,
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
    ) -> None:
        if self.admin_action_log_service is None:
            return
        try:
            self.admin_action_log_service.log_action(
                action_type=action_type,
                target_type="field_config",
                target_id=target_id,
                operator=operator,
                before_snapshot=before,
                after_snapshot=after,
            )
        except Exception:  # noqa: BLE001
            pass
