from __future__ import annotations

import shutil
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


TEST_FIELD_KEY = "phase9_test_count"


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _insert_record(conn):
    from app.utils.date_utils import settlement_cycle_display_code

    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO daily_records (
            record_id, business_key, record_date, region,
            team_id, team_name_snapshot, team_manager_name_snapshot,
            account_manager_id, account_manager_name_snapshot,
            settlement_cycle_code, repayment_amount_daily, loan_amount_daily,
            intention_daily, wechat_count_daily, visit_count_daily,
            invalid_visit_count_daily, signing_count_daily, quality_visit_count_daily,
            approval_customer_count_daily, repayment_customer_count_daily,
            debt_case_submit_count_daily, debt_case_repayment_count_daily,
            debt_case_repayment_amount_daily, large_order_repayment_count_daily,
            large_order_repayment_amount_daily, four_star_customer_count_daily,
            five_star_customer_count_daily, remark, version,
            created_at, updated_at, template_version, record_hash, source_type
        )
        VALUES (?, ?, '2026-06-01', '测试区域',
                1, '测试团队', '测试经理',
                101, '张三',
                ?, 100, 80,
                1, 2, 3,
                0, 1, 1,
                1, 1,
                0, 0,
                0, 0,
                0, 1,
                1, '', 1,
                ?, ?, 'test', 'hash', 'test')
        """,
        (
            str(uuid.uuid4()),
            "2026-06-01|1|101",
            settlement_cycle_display_code(record_date="2026-06-01"),
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _enable_field_on_page(service, page_key):
    rows = service.list_page_config(page_key)
    found = False
    for row in rows:
        if row["field_key"] == TEST_FIELD_KEY:
            row["visible"] = 1
            row["group_key"] = "process_behavior"
            found = True
            break
    _assert(found, "new field missing from page config {}".format(page_key))
    ok, message = service.save_page_config(page_key, rows, operator="tester")
    _assert(ok, message)


def main():
    from app.db.database import DatabaseManager
    from app.db.repositories import (
        AccountManagerRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        TeamRepository,
    )
    from app.fields.registry import (
        PAGE_DATA_ENTRY,
        PAGE_EXCEL_EXPORT,
        PAGE_JSON_EXPORT,
        PAGE_PNG_TODAY,
        PAGE_QUERY_SUMMARY,
        PAGE_TODAY_DISPLAY,
    )
    from app.fields.field_value_service import FieldValueService
    from app.services.field_admin_config_service import FieldAdminConfigService
    from app.services.record_service import RecordService

    class _TemplateService:
        @staticmethod
        def get_active_template_version():
            return "test"

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_field_admin_test_"))
    try:
        db_path = tmp_dir / "field_admin_test.db"
        db = DatabaseManager(str(db_path))
        db.initialize()

        now = _now()
        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO teams (id, region, team_name, team_manager_name, is_active, created_at, updated_at)
                VALUES (1, '测试区域', '测试团队', '测试经理', 1, ?, ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO account_managers (id, team_id, account_manager_name, is_active, created_at, updated_at)
                VALUES (101, 1, '张三', 1, ?, ?)
                """,
                (now, now),
            )
            record_id = _insert_record(conn)
            conn.commit()

        admin_service = FieldAdminConfigService(db)
        ok, message = admin_service.create_field(
            {
                "field_key": TEST_FIELD_KEY,
                "label": "阶段9测试数",
                "data_type": "int",
                "category": "raw_daily",
                "group_key": "process_behavior",
                "default_value": "0",
                "aggregation": "sum",
                "enabled": 1,
                "editable": 1,
            },
            operator="tester",
        )
        _assert(ok, message)

        ok, message = admin_service.save_field_visibility(
            TEST_FIELD_KEY,
            {
                PAGE_DATA_ENTRY: 1,
                PAGE_TODAY_DISPLAY: 1,
                PAGE_QUERY_SUMMARY: 1,
                PAGE_PNG_TODAY: 1,
                PAGE_EXCEL_EXPORT: 1,
                PAGE_JSON_EXPORT: 1,
            },
            operator="tester",
        )
        _assert(ok, message)

        for page_key in (
            PAGE_DATA_ENTRY,
            PAGE_TODAY_DISPLAY,
            PAGE_QUERY_SUMMARY,
            PAGE_PNG_TODAY,
            PAGE_EXCEL_EXPORT,
            PAGE_JSON_EXPORT,
        ):
            _enable_field_on_page(admin_service, page_key)

        field_value_service = FieldValueService(db)
        field_value_service.set_value(record_id, TEST_FIELD_KEY, 7)

        record_service = RecordService(
            record_repo=DailyRecordRepository(db),
            team_repo=TeamRepository(db),
            account_manager_repo=AccountManagerRepository(db),
            cycle_target_repo=CycleTargetRepository(db),
            template_service=_TemplateService(),
            field_value_service=field_value_service,
        )

        entry_keys = [row["field_key"] for row in record_service.get_entry_field_definitions()]
        today_keys = [row["field_key"] for row in record_service.get_today_display_field_definitions()]
        query_keys = [row["field_key"] for row in record_service.get_query_summary_field_definitions()]
        _assert(TEST_FIELD_KEY in entry_keys, "new field missing from entry config")
        _assert(TEST_FIELD_KEY in today_keys, "new field missing from today display config")
        _assert(TEST_FIELD_KEY in query_keys, "new field missing from query summary config")

        preview_rows = record_service.get_preview_rows(1, "2026-06-01")
        _assert(preview_rows and preview_rows[0].get(TEST_FIELD_KEY) == 7, "preview did not read dynamic field")

        query_result = record_service.get_query_summary_grouped_by_account_manager(
            mode="自定义",
            base_date="2026-06-01",
            team_id=None,
            team_ids=[1],
            custom_start="2026-06-01",
            custom_end="2026-06-01",
        )
        _assert(query_result["rows"][0].get(TEST_FIELD_KEY) == 7, "query summary did not aggregate dynamic field")

        ok, message = admin_service.disable_field(TEST_FIELD_KEY, operator="tester")
        _assert(ok, message)
        entry_keys_after_disable = [row["field_key"] for row in record_service.get_entry_field_definitions()]
        _assert(TEST_FIELD_KEY not in entry_keys_after_disable, "disabled field should not stay visible in entry")

        stored_value = field_value_service.get_value(
            field_value_service.read_record_with_dynamic_values(record_id),
            TEST_FIELD_KEY,
        )
        _assert(stored_value == 7, "disabled field historical value should remain")

        backup_path = tmp_dir / "field_config_backup.json"
        ok, message = admin_service.export_field_config_to_json(str(backup_path), operator="tester")
        _assert(ok and backup_path.exists(), "field config export failed: {}".format(message))

        ok, message = admin_service.import_field_config_from_json(str(backup_path), operator="tester")
        _assert(ok, "field config import failed: {}".format(message))

        ok, message = admin_service.reset_field_config_to_default(operator="tester")
        _assert(ok, "field config reset failed: {}".format(message))
        default_entry_keys = [row["field_key"] for row in record_service.get_entry_field_definitions()]
        _assert("repayment_amount_daily" in default_entry_keys, "default entry config missing repayment field")

        print("[field_admin_config] PASS")
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
