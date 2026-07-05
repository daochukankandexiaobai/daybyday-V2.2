from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, List, Optional


class FieldConfigRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def count_field_definitions(self) -> int:
        row = self.conn.execute("SELECT COUNT(1) AS c FROM field_definitions").fetchone()
        return int(row["c"] if row is not None else 0)

    def count_page_visibility(self) -> int:
        row = self.conn.execute("SELECT COUNT(1) AS c FROM field_page_visibility").fetchone()
        return int(row["c"] if row is not None else 0)

    def count_view_templates(self) -> int:
        row = self.conn.execute("SELECT COUNT(1) AS c FROM view_templates").fetchone()
        return int(row["c"] if row is not None else 0)

    def get_field_definition(self, field_key: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM field_definitions WHERE field_key = ?",
            (field_key,),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_field_definitions(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM field_definitions
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_page_visibility(self, page_key: str = "") -> List[Dict[str, Any]]:
        if page_key:
            rows = self.conn.execute(
                """
                SELECT *
                FROM field_page_visibility
                WHERE page_key = ?
                ORDER BY display_order, id
                """,
                (page_key,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT *
                FROM field_page_visibility
                ORDER BY page_key, display_order, id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_view_templates(self, page_key: str = "") -> List[Dict[str, Any]]:
        if page_key:
            rows = self.conn.execute(
                """
                SELECT *
                FROM view_templates
                WHERE page_key = ?
                ORDER BY is_default DESC, id
                """,
                (page_key,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT *
                FROM view_templates
                ORDER BY page_key, is_default DESC, id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_default_field_definitions(self, rows: Iterable[Dict[str, Any]], now: str) -> int:
        inserted = 0
        for row in rows:
            exists = self.conn.execute(
                "SELECT id FROM field_definitions WHERE field_key = ?",
                (row["field_key"],),
            ).fetchone()
            if exists is None:
                self.conn.execute(
                    """
                    INSERT INTO field_definitions (
                        field_key, label, data_type, category, group_key,
                        editable, required, default_value, aggregation, formula_id,
                        enabled, system_field, storage_type, storage_column, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        int(row.get("system_field", 1) or 0),
                        row.get("storage_type", "display_only"),
                        row.get("storage_column", ""),
                        now,
                        now,
                    ),
                )
                inserted += 1
                continue

            self.conn.execute(
                """
                UPDATE field_definitions
                SET system_field = CASE WHEN system_field = 1 THEN 1 ELSE ? END,
                    storage_type = CASE
                        WHEN storage_type IS NULL OR storage_type = '' THEN ?
                        WHEN system_field = 1 AND storage_type = 'display_only' THEN ?
                        ELSE storage_type
                    END,
                    storage_column = CASE
                        WHEN storage_column IS NULL OR storage_column = '' THEN ?
                        ELSE storage_column
                    END,
                    updated_at = COALESCE(NULLIF(updated_at, ''), ?)
                WHERE field_key = ?
                """,
                (
                    int(row.get("system_field", 1) or 0),
                    row.get("storage_type", "display_only"),
                    row.get("storage_type", "display_only"),
                    row.get("storage_column", ""),
                    now,
                    row["field_key"],
                ),
            )
        return inserted

    def upsert_default_page_visibility(self, rows: Iterable[Dict[str, Any]], now: str) -> int:
        inserted = 0
        for row in rows:
            exists = self.conn.execute(
                """
                SELECT id
                FROM field_page_visibility
                WHERE field_key = ? AND page_key = ?
                """,
                (row["field_key"], row["page_key"]),
            ).fetchone()
            if exists is not None:
                continue

            self.conn.execute(
                """
                INSERT INTO field_page_visibility (
                    field_key, page_key, visible, group_key, display_order,
                    created_at, updated_at
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
            inserted += 1
        return inserted

    def upsert_default_view_templates(self, rows: Iterable[Dict[str, Any]], now: str) -> int:
        inserted = 0
        for row in rows:
            exists = self.conn.execute(
                "SELECT id FROM view_templates WHERE template_key = ?",
                (row["template_key"],),
            ).fetchone()
            if exists is not None:
                continue

            self.conn.execute(
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
            inserted += 1
        return inserted
