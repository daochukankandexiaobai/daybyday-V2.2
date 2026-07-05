from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict

from app.fields.field_config_repository import FieldConfigRepository
from app.fields.registry import (
    build_default_field_rows,
    build_default_page_visibility_rows,
    build_default_view_template_rows,
)


def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


class FieldConfigService:
    def __init__(self, repository: FieldConfigRepository) -> None:
        self.repository = repository

    def bootstrap_defaults(self) -> Dict[str, Any]:
        now = _now_str()
        inserted_fields = self.repository.upsert_default_field_definitions(
            build_default_field_rows(),
            now,
        )
        inserted_visibility = self.repository.upsert_default_page_visibility(
            build_default_page_visibility_rows(),
            now,
        )
        inserted_templates = self.repository.upsert_default_view_templates(
            build_default_view_template_rows(),
            now,
        )
        return {
            "inserted_fields": inserted_fields,
            "inserted_visibility": inserted_visibility,
            "inserted_templates": inserted_templates,
            "field_count": self.repository.count_field_definitions(),
            "visibility_count": self.repository.count_page_visibility(),
            "template_count": self.repository.count_view_templates(),
        }


def bootstrap_default_field_config(conn: sqlite3.Connection) -> Dict[str, Any]:
    repository = FieldConfigRepository(conn)
    service = FieldConfigService(repository)
    return service.bootstrap_defaults()
