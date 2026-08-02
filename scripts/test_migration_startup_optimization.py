from __future__ import annotations

"""Verify one-time startup maintenance markers preserve migration safety."""

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


def _get_setting(db, key):
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
    return str(row["value"] or "") if row is not None else ""


def _has_table(db, table_name):
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
    return row is not None


def main():
    from app.db.database import DatabaseManager
    from app.db import migrations
    from app.fields import field_config_service

    temp_dir = Path(tempfile.mkdtemp(prefix="daybyday_migration_startup_test_"))
    try:
        db = DatabaseManager(str(temp_dir / "migration_startup.db"))
        db.initialize()

        _assert(
            _get_setting(db, migrations.DAILY_RECORD_MAINTENANCE_KEY)
            == migrations.DAILY_RECORD_MAINTENANCE_VERSION,
            "daily record maintenance marker was not written",
        )
        _assert(
            _get_setting(db, migrations.FIELD_CONFIG_DEFAULTS_KEY)
            == migrations.FIELD_CONFIG_DEFAULTS_VERSION,
            "field configuration defaults marker was not written",
        )
        _assert(
            not _has_table(db, "daily_records_migration_backup"),
            "a clean database must not receive an empty migration backup table",
        )

        with db.get_connection() as conn:
            conn.execute(
                "DELETE FROM app_settings WHERE key IN (?, ?)",
                (
                    migrations.DAILY_RECORD_MAINTENANCE_KEY,
                    migrations.FIELD_CONFIG_DEFAULTS_KEY,
                ),
            )
            conn.commit()

        db.initialize()
        _assert(
            _get_setting(db, migrations.DAILY_RECORD_MAINTENANCE_KEY)
            == migrations.DAILY_RECORD_MAINTENANCE_VERSION,
            "database maintenance did not rerun after its marker was removed",
        )
        _assert(
            _get_setting(db, migrations.FIELD_CONFIG_DEFAULTS_KEY)
            == migrations.FIELD_CONFIG_DEFAULTS_VERSION,
            "field default synchronization did not rerun after its marker was removed",
        )

        original_legacy_migration = migrations._migrate_legacy_daily_records
        original_cycle_normalization = migrations._normalize_daily_record_cycle_codes
        original_deduplication = migrations._deduplicate_for_unique_daily_key
        original_field_bootstrap = field_config_service.bootstrap_default_field_config

        def _unexpected_call(*_args, **_kwargs):
            raise AssertionError("completed startup maintenance ran again")

        migrations._migrate_legacy_daily_records = _unexpected_call
        migrations._normalize_daily_record_cycle_codes = _unexpected_call
        migrations._deduplicate_for_unique_daily_key = _unexpected_call
        field_config_service.bootstrap_default_field_config = _unexpected_call
        try:
            db.initialize()
        finally:
            migrations._migrate_legacy_daily_records = original_legacy_migration
            migrations._normalize_daily_record_cycle_codes = original_cycle_normalization
            migrations._deduplicate_for_unique_daily_key = original_deduplication
            field_config_service.bootstrap_default_field_config = original_field_bootstrap

        _assert(
            not _has_table(db, "daily_records_migration_backup"),
            "repeated clean startup must not create a migration backup table",
        )
        print("[migration_startup_optimization] PASS")
        return 0
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
