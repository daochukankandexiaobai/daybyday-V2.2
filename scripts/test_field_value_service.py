from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _now_str():
    return datetime.now().isoformat(timespec="seconds")


def _insert_daily_record(conn):
    now = _now_str()
    cursor = conn.execute(
        """
        INSERT INTO daily_records (
            record_id, business_key, record_date, region,
            team_id, team_name_snapshot, team_manager_name_snapshot,
            account_manager_id, account_manager_name_snapshot,
            settlement_cycle_code, repayment_amount_daily,
            created_at, updated_at, template_version, record_hash, source_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "field-value-test-001",
            "2026-07-01|测试区域|测试团队|测试客户经理",
            "2026-07-01",
            "测试区域",
            1,
            "测试团队",
            "测试经理",
            1001,
            "测试客户经理",
            "2026-07期",
            123.45,
            now,
            now,
            "test",
            "hash",
            "test",
        ),
    )
    return int(cursor.lastrowid)


def _insert_dynamic_field(conn, field_key, label, data_type, default_value):
    now = _now_str()
    conn.execute(
        """
        INSERT INTO field_definitions (
            field_key, label, data_type, category, group_key,
            editable, required, default_value, aggregation, formula_id,
            enabled, system_field, storage_type, storage_column,
            created_at, updated_at
        )
        VALUES (?, ?, ?, 'raw_daily', 'process_behavior',
                1, 0, ?, 'sum', '',
                1, 0, 'dynamic_metric', '',
                ?, ?)
        """,
        (field_key, label, data_type, str(default_value), now, now),
    )


def main():
    from app.db.database import DatabaseManager
    from app.fields.field_value_service import FieldValueService

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_field_value_test_"))
    try:
        db_path = tmp_dir / "field_value_test.db"
        db = DatabaseManager(str(db_path))
        db.initialize()

        with db.get_connection() as conn:
            record_id = _insert_daily_record(conn)
            _insert_dynamic_field(conn, "dynamic_test_count", "动态测试整数", "int", 7)
            _insert_dynamic_field(conn, "dynamic_test_amount", "动态测试金额", "amount", 0)
            conn.commit()

        service = FieldValueService(db)
        record = service.read_record_with_dynamic_values(record_id)
        _assert(service.get_value(record, "repayment_amount_daily") == 123.45, "固定列读取失败")

        service.set_value(record_id, "dynamic_test_count", 3)
        record = service.read_record_with_dynamic_values(record_id)
        _assert(service.get_value(record, "dynamic_test_count") == 3, "动态整数字段写入/读取失败")

        service.set_value(record_id, "dynamic_test_count", 5)
        record = service.read_record_with_dynamic_values(record_id)
        _assert(service.get_value(record, "dynamic_test_count") == 5, "动态整数字段更新失败")

        with db.get_connection() as conn:
            count = int(
                conn.execute(
                    """
                    SELECT COUNT(1) AS c
                    FROM daily_metric_values
                    WHERE record_id = ? AND field_key = ?
                    """,
                    (record_id, "dynamic_test_count"),
                ).fetchone()["c"]
            )
        _assert(count == 1, "动态字段重复写入产生了重复行")

        service.set_value(record_id, "dynamic_test_count", None)
        record = service.read_record_with_dynamic_values(record_id)
        _assert(service.get_value(record, "dynamic_test_count") == 7, "空值未按默认值处理")

        service.set_value(record_id, "dynamic_test_amount", "88.50")
        record = service.read_record_with_dynamic_values(record_id)
        _assert(abs(service.get_value(record, "dynamic_test_amount") - 88.5) < 0.0001, "动态金额字段写入/读取失败")

        ok, _msg = service.validate_value({"label": "动态测试整数", "data_type": "int"}, "2")
        _assert(ok, "整数字段合法值校验失败")
        ok, _msg = service.validate_value({"label": "动态测试金额", "data_type": "amount"}, "1.25")
        _assert(ok, "金额字段合法值校验失败")

        try:
            service.set_value(record_id, "dynamic_test_count", -1)
            raise AssertionError("负整数未被拒绝")
        except ValueError:
            pass

        try:
            service.set_value(record_id, "dynamic_test_amount", -0.01)
            raise AssertionError("负金额未被拒绝")
        except ValueError:
            pass

        values = service.get_values(record_id, ["repayment_amount_daily", "dynamic_test_count"])
        _assert(values["repayment_amount_daily"] == 123.45, "批量读取固定列失败")
        _assert(values["dynamic_test_count"] == 7, "批量读取动态字段失败")

        print("[field_value] PASS")
        print("[field_value] record_id:", record_id)
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
