from __future__ import annotations

"""Verify coordinated writes leave no partial SQLite data when a later step fails."""

import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


DYNAMIC_FIELD_KEY = "transaction_test_dynamic_count"


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _build_services(db):
    from app.db.repositories import (
        AccountManagerRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        ImportLogRepository,
        SettingsRepository,
        TeamRepository,
        TemplateRepository,
        WeeklyTargetRepository,
    )
    from app.fields.field_value_service import FieldValueService
    from app.services.field_admin_config_service import FieldAdminConfigService
    from app.services.import_service import ImportService
    from app.services.record_service import RecordService
    from app.services.settings_service import SettingsService
    from app.services.team_service import TeamService
    from app.services.template_service import TemplateService
    from app.services.weekly_target_service import WeeklyTargetService

    settings_service = SettingsService(SettingsRepository(db))
    team_repo = TeamRepository(db)
    manager_repo = AccountManagerRepository(db)
    cycle_target_repo = CycleTargetRepository(db)
    record_repo = DailyRecordRepository(db)
    template_service = TemplateService(TemplateRepository(db), settings_service)
    field_value_service = FieldValueService(db)
    team_service = TeamService(team_repo, manager_repo, cycle_target_repo, settings_service)
    record_service = RecordService(
        record_repo=record_repo,
        team_repo=team_repo,
        account_manager_repo=manager_repo,
        cycle_target_repo=cycle_target_repo,
        template_service=template_service,
        field_value_service=field_value_service,
    )
    return {
        "team_repo": team_repo,
        "manager_repo": manager_repo,
        "cycle_target_repo": cycle_target_repo,
        "record_repo": record_repo,
        "weekly_target_repo": WeeklyTargetRepository(db),
        "field_value_service": field_value_service,
        "field_admin_service": FieldAdminConfigService(db),
        "record_service": record_service,
        "team_service": team_service,
        "import_service": ImportService(
            record_repo=record_repo,
            import_log_repo=ImportLogRepository(db),
            settings_service=settings_service,
            template_service=template_service,
            record_service=record_service,
            team_service=team_service,
            team_repo=team_repo,
            account_manager_repo=manager_repo,
        ),
        "weekly_target_service": WeeklyTargetService(
            WeeklyTargetRepository(db),
            cycle_target_repo,
            team_repo,
            manager_repo,
        ),
    }


def _setup_team(services):
    ok, message, team_id = services["team_service"].save_team_config(
        team_id=None,
        region="Transaction Test",
        team_name="Atomic Team",
        team_manager_name="Manager",
        settlement_cycle_code="2026-06",
        members=[{"account_manager_name": "Alice", "target_amount": 0}],
    )
    _assert(ok and team_id, "team setup failed: {}".format(message))
    member = services["manager_repo"].list_by_team(int(team_id))[0]
    return int(team_id), int(member["id"])


def _create_dynamic_field(services):
    admin_service = services["field_admin_service"]
    ok, message = admin_service.create_field(
        {
            "field_key": DYNAMIC_FIELD_KEY,
            "label": "Transaction Dynamic Count",
            "data_type": "int",
            "category": "raw_daily",
            "group_key": "process_behavior",
            "default_value": "0",
            "aggregation": "sum",
            "editable": 1,
            "enabled": 1,
        },
        operator="test",
    )
    _assert(ok, "dynamic field creation failed: {}".format(message))
    ok, message = admin_service.save_field_visibility(
        DYNAMIC_FIELD_KEY,
        {"data_entry": 1},
        operator="test",
    )
    _assert(ok, "dynamic field visibility failed: {}".format(message))


def _raising_set_values(*_args, **_kwargs):
    raise RuntimeError("simulated dynamic write failure")


def _check_daily_record_rollback(services, team_id, manager_id):
    field_value_service = services["field_value_service"]
    original = field_value_service.set_values
    field_value_service.set_values = _raising_set_values
    try:
        ok, _message, _stats = services["record_service"].save_team_day_sheet(
            team_id=team_id,
            record_date="2026-06-10",
            rows=[
                {
                    "account_manager_id": manager_id,
                    "visit_count_daily": 3,
                    DYNAMIC_FIELD_KEY: 1,
                }
            ],
        )
    finally:
        field_value_service.set_values = original

    _assert(not ok, "daily save should fail when dynamic persistence fails")
    stored = services["record_repo"].get_by_unique("2026-06-10", team_id, manager_id)
    _assert(stored is None, "failed daily save left a fixed daily record behind")


def _check_json_import_rollback(services, team_id, manager_id):
    field_value_service = services["field_value_service"]
    original = field_value_service.set_values
    field_value_service.set_values = _raising_set_values
    record_id = str(uuid.uuid4())
    try:
        status, _message, _affected = services["import_service"]._upsert_record(
            raw_record={
                "record_id": record_id,
                "record_date": "2026-06-11",
                "region": "Transaction Test",
                "team_id": team_id,
                "team_name_snapshot": "Atomic Team",
                "team_manager_name_snapshot": "Manager",
                "account_manager_id": manager_id,
                "account_manager_name_snapshot": "Alice",
                "visit_count_daily": 3,
                DYNAMIC_FIELD_KEY: 1,
                "version": 1,
            },
            file_path="transaction-test.json",
            file_template_version="test-template",
        )
    finally:
        field_value_service.set_values = original

    _assert(status == "failed", "JSON import should fail when dynamic persistence fails")
    stored = services["record_repo"].get_by_record_id(record_id)
    _assert(stored is None, "failed JSON import left a fixed daily record behind")


def _check_week_target_rollback(services, team_id, manager_id):
    cycle_target_repo = services["cycle_target_repo"]
    original = cycle_target_repo.upsert_target

    def fail_cycle_target(*_args, **_kwargs):
        raise RuntimeError("simulated cycle target sync failure")

    cycle_target_repo.upsert_target = fail_cycle_target
    try:
        services["weekly_target_service"].save_week_targets_for_team(
            team_id=team_id,
            settlement_cycle_code="2026-06",
            week_index=1,
            rows=[
                {
                    "account_manager_id": manager_id,
                    "visit_target": 2,
                    "quality_visit_target": 1,
                    "repayment_target": 100,
                }
            ],
        )
    except RuntimeError:
        pass
    finally:
        cycle_target_repo.upsert_target = original

    rows = services["weekly_target_repo"].list_targets_for_team_cycle(team_id, "2026-06")
    _assert(not rows, "failed weekly target sync left weekly targets behind")


def _check_config_import_rollback(services, temp_dir):
    source = temp_dir / "invalid-field-config.json"
    source.write_text(
        json.dumps(
            {
                "field_definitions": [
                    {
                        "field_key": "transaction_import_valid",
                        "label": "Import Valid",
                        "data_type": "int",
                        "category": "raw_daily",
                        "group_key": "process_behavior",
                        "default_value": "0",
                        "aggregation": "sum",
                        "enabled": 1,
                    },
                    {
                        "field_key": "transaction_import_invalid",
                        "label": "Import Invalid",
                        "data_type": "unsupported_type",
                        "category": "raw_daily",
                        "default_value": "0",
                        "aggregation": "sum",
                    },
                ],
                "field_page_visibility": [],
                "view_templates": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ok, _message = services["field_admin_service"].import_field_config_from_json(str(source), operator="test")
    _assert(not ok, "invalid config import should fail")
    _assert(
        services["field_admin_service"].get_field("transaction_import_valid") is None,
        "failed config import left an earlier field update behind",
    )


def main():
    from app.db.database import DatabaseManager

    temp_dir = Path(tempfile.mkdtemp(prefix="daybyday_transaction_test_"))
    try:
        db = DatabaseManager(str(temp_dir / "transaction.db"))
        db.initialize()
        services = _build_services(db)
        team_id, manager_id = _setup_team(services)
        _create_dynamic_field(services)
        _check_daily_record_rollback(services, team_id, manager_id)
        _check_json_import_rollback(services, team_id, manager_id)
        _check_week_target_rollback(services, team_id, manager_id)
        _check_config_import_rollback(services, temp_dir)
        print("[transaction_integrity] PASS")
        return 0
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
