from __future__ import annotations

"""Exercise default field metadata validation and runtime template fallback."""

import shutil
import sys
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _field_keys(rows):
    return [str(row.get("field_key", "")) for row in rows]


def main():
    from app.config.field_profiles import PROFILE_PREVIEW_TABLE, get_profile_field_keys
    from app.db.database import DatabaseManager
    from app.fields.display_config_service import DisplayFieldConfigService
    from app.fields.registry import PAGE_TODAY_DISPLAY
    from app.services.field_admin_config_service import FieldAdminConfigService

    temp_dir = Path(tempfile.mkdtemp(prefix="daybyday_field_health_test_"))
    try:
        db = DatabaseManager(str(temp_dir / "field_health.db"))
        db.initialize()
        admin_service = FieldAdminConfigService(db)

        healthy = admin_service.get_config_health()
        _assert(
            int(healthy["summary"].get("error_count", 0) or 0) == 0,
            "a new database should have no field configuration errors",
        )

        with db.get_connection() as conn:
            formula_rows = conn.execute(
                """
                SELECT field_key, formula_id
                FROM field_definitions
                WHERE category = 'formula' AND enabled = 1
                """
            ).fetchall()
            _assert(formula_rows, "default formula fields are missing")
            _assert(
                all(str(row["formula_id"] or "").strip() for row in formula_rows),
                "default formula fields must have formula_id values",
            )
            conn.execute(
                "UPDATE field_definitions SET formula_id = '' WHERE field_key = 'target_progress'"
            )
            conn.commit()

        db.initialize()
        with db.get_connection() as conn:
            repaired = conn.execute(
                "SELECT formula_id FROM field_definitions WHERE field_key = 'target_progress'"
            ).fetchone()
            _assert(
                repaired is not None and str(repaired["formula_id"] or "") == "target_completion_rate",
                "startup default sync should repair a missing system formula id",
            )

        with db.get_connection() as conn:
            conn.execute(
                "DELETE FROM field_page_visibility WHERE page_key = ?",
                (PAGE_TODAY_DISPLAY,),
            )
            conn.execute(
                "UPDATE view_templates SET config_json = ? WHERE template_key = ?",
                ("{invalid-json", "today_display_default"),
            )
            conn.commit()

        damaged = admin_service.get_config_health()
        _assert(
            int(damaged["summary"].get("error_count", 0) or 0) > 0,
            "damaged default template should be reported",
        )

        display_service = DisplayFieldConfigService(db)
        rows = display_service.get_page_fields(
            page_key=PAGE_TODAY_DISPLAY,
            fallback_profile_key=PROFILE_PREVIEW_TABLE,
            template_key="today_display_default",
        )
        _assert(
            _field_keys(rows) == list(get_profile_field_keys(PROFILE_PREVIEW_TABLE)),
            "damaged template should fall back to the stable today display profile",
        )

        db.initialize()
        still_damaged = admin_service.get_config_health()
        _assert(
            int(still_damaged["summary"].get("error_count", 0) or 0) > 0,
            "startup default sync must not overwrite an administrator template",
        )

        print("[field_config_health] PASS")
        return 0
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
