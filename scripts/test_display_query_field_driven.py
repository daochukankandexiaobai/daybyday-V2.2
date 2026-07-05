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


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _assert_close(actual, expected, message):
    _assert(actual is not None, message + " returned None")
    _assert(abs(float(actual) - float(expected)) < 0.000001, message)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _insert_record(conn, team_id, manager_id, manager_name, record_date, **metrics):
    from app.utils.date_utils import settlement_cycle_display_code

    now = _now()
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
        VALUES (?, ?, ?, '测试区域',
                ?, '测试团队', '测试经理',
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, '', 1,
                ?, ?, 'test', ?, 'test')
        """,
        (
            str(uuid.uuid4()),
            "{}|{}|{}".format(record_date, team_id, manager_id),
            record_date,
            team_id,
            manager_id,
            manager_name,
            settlement_cycle_display_code(record_date=record_date),
            float(metrics.get("repayment_amount_daily", 0) or 0),
            float(metrics.get("loan_amount_daily", 0) or 0),
            int(metrics.get("intention_daily", 0) or 0),
            int(metrics.get("wechat_count_daily", 0) or 0),
            int(metrics.get("visit_count_daily", 0) or 0),
            int(metrics.get("invalid_visit_count_daily", 0) or 0),
            int(metrics.get("signing_count_daily", 0) or 0),
            int(metrics.get("quality_visit_count_daily", 0) or 0),
            int(metrics.get("approval_customer_count_daily", 0) or 0),
            int(metrics.get("repayment_customer_count_daily", 0) or 0),
            int(metrics.get("debt_case_submit_count_daily", 0) or 0),
            int(metrics.get("debt_case_repayment_count_daily", 0) or 0),
            float(metrics.get("debt_case_repayment_amount_daily", 0) or 0),
            int(metrics.get("large_order_repayment_count_daily", 0) or 0),
            float(metrics.get("large_order_repayment_amount_daily", 0) or 0),
            int(metrics.get("four_star_customer_count_daily", 0) or 0),
            int(metrics.get("five_star_customer_count_daily", 0) or 0),
            now,
            now,
            "hash-{}-{}".format(record_date, manager_id),
        ),
    )


def main():
    from app.db.database import DatabaseManager
    from app.db.repositories import (
        AccountManagerRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        TeamRepository,
    )
    from app.services.record_service import RecordService
    from app.utils.date_utils import settlement_cycle_for_date

    class _TemplateService:
        @staticmethod
        def get_active_template_version():
            return "test"

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_display_query_test_"))
    try:
        db_path = tmp_dir / "display_query_test.db"
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
            cycle = settlement_cycle_for_date(datetime.strptime("2026-06-01", "%Y-%m-%d").date())
            conn.execute(
                """
                INSERT INTO cycle_targets (
                    team_id, account_manager_id, settlement_cycle_code,
                    target_amount, created_at, updated_at
                )
                VALUES (1, 101, ?, 1000, ?, ?)
                """,
                (cycle.code, now, now),
            )
            _insert_record(
                conn,
                1,
                101,
                "张三",
                "2026-06-01",
                repayment_amount_daily=100,
                visit_count_daily=5,
                invalid_visit_count_daily=1,
                signing_count_daily=1,
                quality_visit_count_daily=2,
                approval_customer_count_daily=1,
                repayment_customer_count_daily=1,
                four_star_customer_count_daily=1,
                five_star_customer_count_daily=2,
            )
            _insert_record(
                conn,
                1,
                101,
                "张三",
                "2026-06-02",
                repayment_amount_daily=200,
                visit_count_daily=5,
                invalid_visit_count_daily=0,
                signing_count_daily=2,
                quality_visit_count_daily=1,
                approval_customer_count_daily=1,
                repayment_customer_count_daily=1,
                four_star_customer_count_daily=3,
                five_star_customer_count_daily=4,
            )
            _insert_record(
                conn,
                1,
                101,
                "张三",
                "2026-06-29",
                repayment_amount_daily=50,
                visit_count_daily=1,
                signing_count_daily=1,
                four_star_customer_count_daily=1,
                five_star_customer_count_daily=1,
            )
            conn.commit()

        service = RecordService(
            record_repo=DailyRecordRepository(db),
            team_repo=TeamRepository(db),
            account_manager_repo=AccountManagerRepository(db),
            cycle_target_repo=CycleTargetRepository(db),
            template_service=_TemplateService(),
        )

        today_keys = [row["field_key"] for row in service.get_today_display_field_definitions()]
        query_keys = [row["field_key"] for row in service.get_query_summary_field_definitions()]
        _assert("four_star_customer_count_daily" in today_keys, "today display missing four-star field")
        _assert("five_star_customer_count_daily" in today_keys, "today display missing five-star field")
        _assert("four_star_customer_count" in query_keys, "query summary missing four-star field")
        _assert("five_star_customer_count" in query_keys, "query summary missing five-star field")

        result = service.get_query_summary_grouped_by_account_manager(
            mode="自定义",
            base_date="2026-06-01",
            team_id=None,
            team_ids=[1],
            custom_start="2026-06-01",
            custom_end="2026-06-02",
        )
        rows = result["rows"]
        _assert(len(rows) == 1, "query summary should keep one row per manager")
        row = rows[0]
        _assert(row["four_star_customer_count"] == 4, "four-star count should be summed by range")
        _assert(row["five_star_customer_count"] == 6, "five-star count should be summed by range")
        _assert_close(row["signing_rate"], 3.0 / 9.0, "signing rate should use total numerator/denominator")
        _assert_close(row["quality_visit_rate"], 3.0 / 10.0, "quality visit rate should use totals")
        _assert_close(row["approval_rate"], 2.0 / 3.0, "approval rate should use totals")
        _assert_close(row["target_progress"], 300.0 / 1000.0, "target progress should use repayment/target")

        cross = service.get_query_summary_grouped_by_account_manager(
            mode="自定义",
            base_date="2026-06-28",
            team_id=None,
            team_ids=[1],
            custom_start="2026-06-28",
            custom_end="2026-06-29",
        )
        _assert(cross["cross_cycle"], "range should cross settlement cycles")
        _assert(cross["rows"][0]["target_progress"] is None, "cross-cycle target progress should be empty")

        print("[display_query] PASS")
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
