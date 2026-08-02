from __future__ import annotations

"""Verify settlement-cycle configuration safety without touching local user data."""

import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _build_service(db):
    from app.db.repositories import SettlementCycleRuleRepository
    from app.services.settlement_cycle_service import SettlementCycleService

    return SettlementCycleService(SettlementCycleRuleRepository(db))


def _insert_minimal_daily_record(db):
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_records
            (record_id, record_date, region, settlement_cycle_code,
             created_at, updated_at, template_version, record_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cycle-config-test-record",
                "2026-07-15",
                "test",
                "2026-07期",
                "2026-07-15T00:00:00",
                "2026-07-15T00:00:00",
                "test",
                "test",
            ),
        )
        conn.commit()


def main():
    from app.db.database import DatabaseManager
    from app.db.repositories import CycleTargetRepository

    temp_dir = Path(tempfile.mkdtemp(prefix="daybyday_cycle_rule_test_"))
    try:
        db = DatabaseManager(str(temp_dir / "cycle_rule.db"))
        db.initialize()
        service = _build_service(db)

        status = service.get_rule_status()
        _assert(status["rule_mode"] == "calendar_month", "new database must default to calendar month")
        _assert(not status["is_locked"], "new database rule should remain configurable before data exists")
        _assert(status["is_editable"], "new database rule should be editable before data exists")

        july = service.cycle_for_date(date(2026, 7, 15))
        _assert(july.code == "2026-07期", "calendar-month code mismatch")
        _assert(july.start.isoformat() == "2026-07-01", "calendar-month start mismatch")
        _assert(july.end_inclusive.isoformat() == "2026-07-31", "calendar-month end mismatch")

        ok, _message, status = service.update_initial_rule("fixed_start_day", 5, "test")
        _assert(ok, "empty database should allow custom start-day rule")
        _assert(status["rule_mode"] == "fixed_start_day" and status["start_day"] == 5, "custom rule was not saved")

        custom = service.cycle_for_date(date(2026, 7, 15))
        _assert(custom.code == "2026-08期", "custom rule should keep end-month naming")
        _assert(custom.start.isoformat() == "2026-07-05", "custom rule start mismatch")
        _assert(custom.end_inclusive.isoformat() == "2026-08-04", "custom rule end mismatch")

        ok, _message, _status = service.lock_active_rule("test")
        _assert(ok, "rule lock should succeed")
        ok, _message, _status = service.update_initial_rule("fixed_start_day", 6, "test")
        _assert(not ok, "locked rule must reject direct modification")

        second_db = DatabaseManager(str(temp_dir / "data_lock.db"))
        second_db.initialize()
        _insert_minimal_daily_record(second_db)
        second_service = _build_service(second_db)
        ok, _message, _status = second_service.update_initial_rule("fixed_start_day", 5, "test")
        _assert(not ok, "business data must block direct rule modification")
        _assert(not second_service.get_rule_status()["is_editable"], "business data should make rule read-only")

        legacy_db = DatabaseManager(str(temp_dir / "legacy_seed.db"))
        legacy_db.initialize()
        _insert_minimal_daily_record(legacy_db)
        with legacy_db.get_connection() as conn:
            conn.execute("DELETE FROM settlement_cycle_rules")
            conn.commit()
        legacy_db.initialize()
        legacy_status = _build_service(legacy_db).get_rule_status()
        _assert(legacy_status["rule_mode"] == "legacy_29", "existing database must keep legacy rule")
        _assert(legacy_status["is_locked"], "legacy rule must be locked to protect history")
        legacy_service = _build_service(legacy_db)
        legacy_feb = legacy_service.cycle_for_date(date(2026, 2, 28))
        legacy_mar = legacy_service.cycle_for_date(date(2026, 3, 1))
        _assert(legacy_feb.start.isoformat() == "2026-01-29", "legacy February start mismatch")
        _assert(legacy_feb.end_inclusive.isoformat() == "2026-02-28", "legacy February end mismatch")
        _assert(legacy_mar.start.isoformat() == "2026-03-01", "legacy March bridge start mismatch")
        _assert(legacy_mar.end_inclusive.isoformat() == "2026-03-28", "legacy March bridge end mismatch")

        # A later rule must form a new timeline without reclassifying legacy
        # rows.  The overlapping 2026-08 cycle code is intentionally isolated
        # by the immutable rule-key snapshot.
        ok, _message, _status = legacy_service.schedule_successor_rule(
            "calendar_month",
            1,
            "2026-08-01",
            "test",
        )
        _assert(ok, "legacy database should allow a future successor rule")
        before_switch = legacy_service.cycle_for_date(date(2026, 7, 31))
        after_switch = legacy_service.cycle_for_date(date(2026, 8, 1))
        _assert(before_switch.code == "2026-08期", "legacy transition code mismatch")
        _assert(before_switch.end_inclusive.isoformat() == "2026-07-31", "legacy cycle must stop at successor")
        _assert(after_switch.code == "2026-08期", "successor cycle code mismatch")
        _assert(after_switch.start.isoformat() == "2026-08-01", "successor cycle start mismatch")
        legacy_rule_key = legacy_service.rule_key_for_date(date(2026, 7, 31))
        successor_rule_key = legacy_service.rule_key_for_date(date(2026, 8, 1))
        _assert(legacy_rule_key != successor_rule_key, "rule snapshots must differ across the switch")
        legacy_code_slice = legacy_service.cycle_from_code("2026-08期", legacy_rule_key)
        _assert(
            legacy_code_slice.end_inclusive.isoformat() == "2026-07-31",
            "rule-key cycle lookup must also stop at the successor boundary",
        )
        _assert(
            legacy_service.range_crosses_cycles(date(2026, 7, 31), date(2026, 8, 1)),
            "same code under different rules must still cross cycle timelines",
        )

        with legacy_db.get_connection() as conn:
            now = "2026-07-31T00:00:00"
            conn.execute(
                """
                INSERT INTO teams (id, region, team_name, team_manager_name, is_active, created_at, updated_at)
                VALUES (1, 'test', 'test team', 'test manager', 1, ?, ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO account_managers (id, team_id, account_manager_name, is_active, created_at, updated_at)
                VALUES (1, 1, 'test member', 1, ?, ?)
                """,
                (now, now),
            )
            conn.commit()
        target_repo = CycleTargetRepository(legacy_db)
        target_repo.upsert_target(1, 1, "2026-08期", 100.0, "2026-07-31T00:00:00", settlement_cycle_rule_key=legacy_rule_key)
        target_repo.upsert_target(1, 1, "2026-08期", 200.0, "2026-08-01T00:00:00", settlement_cycle_rule_key=successor_rule_key)
        _assert(
            target_repo.get_target(1, 1, "2026-08期", legacy_rule_key) == 100.0,
            "legacy target must remain separate from successor target",
        )
        _assert(
            target_repo.get_target(1, 1, "2026-08期", successor_rule_key) == 200.0,
            "successor target must remain separate from legacy target",
        )

        import_db = DatabaseManager(str(temp_dir / "import_rule_history.db"))
        import_db.initialize()
        import_service = _build_service(import_db)
        ok, _message, _status = import_service.schedule_successor_rule(
            "calendar_month",
            1,
            "2026-08-01",
            "test",
        )
        _assert(ok, "empty import database should accept a scheduled natural-month rule")
        key_map = import_service.merge_imported_rule_history(
            [
                {
                    "rule_key": "legacy_29",
                    "rule_mode": "legacy_29",
                    "start_day": 29,
                    "effective_from": "1900-01-01",
                    "is_locked": True,
                },
                {
                    "rule_key": successor_rule_key,
                    "rule_mode": "calendar_month",
                    "start_day": 1,
                    "effective_from": "2026-08-01",
                    "is_locked": True,
                },
            ]
        )
        _assert(key_map.get("legacy_29") == "legacy_29", "import should retain the legacy base rule")
        _assert(
            import_service.get_rule_for_date(date(2026, 7, 31)).mode == "legacy_29",
            "imported history must use the legacy rule before the switch",
        )
        _assert(
            import_service.get_rule_for_date(date(2026, 8, 1)).mode == "calendar_month",
            "pre-scheduled natural-month rule must survive historical import",
        )

        print("[settlement_cycle_config] PASS")
        return 0
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
