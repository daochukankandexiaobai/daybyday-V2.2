from __future__ import annotations

import json
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


def _count(conn, table):
    row = conn.execute("SELECT COUNT(1) AS c FROM {}".format(table)).fetchone()
    return int(row["c"] or 0)


def _insert_daily_record(conn):
    from app.utils.date_utils import now_iso, settlement_cycle_display_code

    now = now_iso()
    conn.execute(
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
        VALUES (
            'config-pack-record-001', '2026-07-01|1|101', '2026-07-01', '测试区域',
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
            ?, ?, 'test', 'hash-config-pack-001', 'test'
        )
        """,
        (settlement_cycle_display_code(record_date="2026-07-01"), now, now),
    )


def _clone_pack(pack):
    return json.loads(json.dumps(pack, ensure_ascii=False))


def _field_keys(pack):
    return [str(row.get("field_key", "")) for row in pack.get("field_definitions", [])]


def main():
    from app.db.database import DatabaseManager
    from app.db.repositories import AdminActionLogRepository
    from app.fields.config_pack_service import (
        ConfigPackService,
        IMPORT_MODE_ADD_MISSING,
        IMPORT_MODE_MERGE_UPDATE,
        IMPORT_MODE_REPLACE,
        PACK_TYPE,
    )
    from app.services.admin_action_log_service import AdminActionLogService

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_config_pack_test_"))
    try:
        db = DatabaseManager(str(tmp_dir / "config_pack.db"))
        db.initialize()
        admin_log_service = AdminActionLogService(AdminActionLogRepository(db))
        service = ConfigPackService(db, admin_action_log_service=admin_log_service)

        with db.get_connection() as conn:
            _insert_daily_record(conn)
            daily_before = _count(conn, "daily_records")
            dynamic_before = _count(conn, "daily_metric_values")
            conn.commit()

        export_path = tmp_dir / "YST-Config-Test.json"
        ok, message = service.export_config_pack(
            str(export_path),
            {
                "pack_id": "YST-Config-Test",
                "pack_version": "2026.07.01",
                "app_min_version": "1.0.0",
                "created_by": "tester",
                "description": "配置包测试",
            },
        )
        _assert(ok, "export_config_pack failed: {}".format(message))
        _assert(export_path.exists(), "export file missing")

        pack = service.load_config_pack(str(export_path))
        _assert(pack.get("pack_type") == PACK_TYPE, "pack_type should identify config pack")
        _assert(pack.get("checksum"), "export should calculate checksum")
        _assert("daily_records" not in pack, "config pack must not include daily_records")
        _assert("daily_metric_values" not in pack, "config pack must not include daily_metric_values")

        validation = service.validate_config_pack(pack)
        _assert(not validation.errors, "exported pack should validate: {}".format(validation.errors))

        non_config_path = tmp_dir / "daily_payload.json"
        non_config_path.write_text(json.dumps({"pack_type": "daily_records", "records": []}), encoding="utf-8")
        bad_pack = service.load_config_pack(str(non_config_path))
        bad_validation = service.validate_config_pack(bad_pack)
        _assert(bad_validation.errors, "non config pack should be rejected")
        _assert("该文件不是字段与报表配置包" in "\n".join(bad_validation.errors), "wrong pack_type message missing")

        missing_version = _clone_pack(pack)
        missing_version.pop("pack_version", None)
        missing_validation = service.validate_config_pack(missing_version)
        _assert(missing_validation.errors, "missing pack_version should fail validation")

        modified_pack = _clone_pack(pack)
        modified_pack["field_definitions"].append(
            {
                "field_key": "config_pack_test_count",
                "label": "配置包测试数",
                "data_type": "int",
                "category": "raw_daily",
                "group_key": "process_behavior",
                "editable": 1,
                "required": 0,
                "default_value": "0",
                "aggregation": "sum",
                "formula_id": "",
                "enabled": 1,
                "system_field": 0,
                "storage_type": "dynamic_metric",
                "storage_column": "",
            }
        )
        modified_pack["field_page_visibility"].append(
            {
                "field_key": "config_pack_test_count",
                "page_key": "data_entry",
                "visible": 1,
                "group_key": "process_behavior",
                "display_order": 999,
            }
        )
        modified_pack["checksum"] = service.calculate_checksum(modified_pack)
        preview = service.preview_config_pack(modified_pack)
        _assert(preview.add_count >= 1, "preview should detect added field")
        _assert(
            any(row.get("field_key") == "config_pack_test_count" for row in preview.add_fields),
            "preview added field list missing test field",
        )

        backup_count_before = len(list((tmp_dir / "backups" / "config").glob("*.json")))
        result = service.import_config_pack(
            modified_pack,
            mode=IMPORT_MODE_ADD_MISSING,
            operator="tester",
            source_file=str(export_path),
        )
        _assert(result.success, "add-missing import failed: {}".format(result.message))
        _assert(result.added_count >= 1, "add-missing import should add field")
        _assert(result.backup_path, "import should create backup")
        _assert(Path(result.backup_path).exists(), "backup file should exist")
        backup_count_after = len(list((tmp_dir / "backups" / "config").glob("*.json")))
        _assert(backup_count_after > backup_count_before, "backup count should increase")

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT field_key, label FROM field_definitions WHERE field_key = 'config_pack_test_count'"
            ).fetchone()
            _assert(row is not None, "imported field should exist")
            _assert(str(row["label"]) == "配置包测试数", "imported field label mismatch")
            daily_after_add = _count(conn, "daily_records")
            dynamic_after_add = _count(conn, "daily_metric_values")
        _assert(daily_after_add == daily_before, "import must not delete daily_records")
        _assert(dynamic_after_add == dynamic_before, "import must not delete daily_metric_values")

        merge_pack = _clone_pack(modified_pack)
        for row in merge_pack["field_definitions"]:
            if row.get("field_key") == "config_pack_test_count":
                row["label"] = "配置包测试数已更新"
        merge_pack["checksum"] = service.calculate_checksum(merge_pack)
        merge_result = service.import_config_pack(merge_pack, mode=IMPORT_MODE_MERGE_UPDATE, operator="tester")
        _assert(merge_result.success, "merge import failed: {}".format(merge_result.message))
        _assert(merge_result.updated_count >= 1, "merge import should update existing field")
        with db.get_connection() as conn:
            label = conn.execute(
                "SELECT label FROM field_definitions WHERE field_key = 'config_pack_test_count'"
            ).fetchone()["label"]
        _assert(str(label) == "配置包测试数已更新", "merge mode should update field label")

        replace_pack = _clone_pack(pack)
        _assert("config_pack_test_count" not in _field_keys(replace_pack), "baseline pack should not include imported test field")
        replace_pack["checksum"] = service.calculate_checksum(replace_pack)
        replace_result = service.import_config_pack(replace_pack, mode=IMPORT_MODE_REPLACE, operator="tester")
        _assert(replace_result.success, "replace import failed: {}".format(replace_result.message))
        with db.get_connection() as conn:
            disabled_row = conn.execute(
                "SELECT enabled FROM field_definitions WHERE field_key = 'config_pack_test_count'"
            ).fetchone()
            _assert(disabled_row is not None, "replace mode must not physically delete extra field")
            _assert(int(disabled_row["enabled"] or 0) == 0, "replace mode should disable extra field")
            _assert(_count(conn, "daily_records") == daily_before, "replace mode must not delete daily_records")

        restore_ok, restore_message = service.restore_config_from_backup(result.backup_path, operator="tester")
        _assert(restore_ok, "restore backup failed: {}".format(restore_message))
        with db.get_connection() as conn:
            restored = conn.execute(
                "SELECT field_key FROM field_definitions WHERE field_key = 'config_pack_test_count'"
            ).fetchone()
            _assert(restored is None or int(conn.execute(
                "SELECT enabled FROM field_definitions WHERE field_key = 'config_pack_test_count'"
            ).fetchone()["enabled"] or 0) == 0, "backup restore should not make later test field active")
            _assert(_count(conn, "daily_records") == daily_before, "backup restore must not delete daily_records")

        default_ok, default_message = service.restore_default_config(operator="tester")
        _assert(default_ok, "restore default failed: {}".format(default_message))
        with db.get_connection() as conn:
            _assert(_count(conn, "daily_records") == daily_before, "default restore must not delete daily_records")
            _assert(_count(conn, "daily_metric_values") == dynamic_before, "default restore must not delete dynamic values")

        state = service.get_current_config_pack_state()
        _assert("health_status" in state, "config pack state should include health_status")

        logs = admin_log_service.list_logs(target_type="config_pack")
        _assert(logs, "config pack operations should be logged")

        print("[config_pack] PASS")
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
