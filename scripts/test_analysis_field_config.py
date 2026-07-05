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
    return int(cursor.lastrowid)


def _insert_dynamic_analysis_field(conn):
    now = _now()
    conn.execute(
        """
        INSERT INTO field_definitions (
            field_key, label, data_type, category, group_key,
            editable, required, default_value, aggregation, formula_id,
            enabled, system_field, storage_type, storage_column,
            created_at, updated_at
        )
        VALUES (
            'dynamic_analysis_count', '动态分析数', 'int', 'raw_daily', 'process_behavior',
            1, 0, '0', 'sum', '',
            1, 0, 'dynamic_metric', '',
            ?, ?
        )
        """,
        (now, now),
    )
    conn.execute(
        """
        INSERT INTO field_page_visibility (
            field_key, page_key, visible, group_key, display_order, created_at, updated_at
        )
        VALUES ('dynamic_analysis_count', 'analysis', 1, 'process_behavior', 999, ?, ?)
        """,
        (now, now),
    )


def main():
    from app.db.database import DatabaseManager
    from app.db.repositories import (
        AccountManagerRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        TeamRepository,
    )
    from app.fields.field_value_service import FieldValueService
    from app.services.analytics_service import AnalyticsService
    from app.services.record_service import RecordService

    class _TemplateService:
        @staticmethod
        def get_active_template_version():
            return "test"

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_analysis_config_test_"))
    try:
        db_path = tmp_dir / "analysis_config_test.db"
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
            conn.execute(
                """
                INSERT INTO account_managers (id, team_id, account_manager_name, is_active, created_at, updated_at)
                VALUES (102, 1, '李四', 1, ?, ?)
                """,
                (now, now),
            )
            _insert_dynamic_analysis_field(conn)
            record_1 = _insert_record(
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
                repayment_customer_count_daily=1,
                four_star_customer_count_daily=1,
                five_star_customer_count_daily=2,
            )
            record_2 = _insert_record(
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
                repayment_customer_count_daily=1,
                four_star_customer_count_daily=3,
                five_star_customer_count_daily=4,
            )
            record_3 = _insert_record(
                conn,
                1,
                102,
                "李四",
                "2026-06-02",
                repayment_amount_daily=50,
                visit_count_daily=4,
                signing_count_daily=1,
                quality_visit_count_daily=1,
                repayment_customer_count_daily=1,
                four_star_customer_count_daily=5,
                five_star_customer_count_daily=1,
            )
            conn.commit()

        field_value_service = FieldValueService(db)
        field_value_service.set_value(record_1, "dynamic_analysis_count", 7)
        field_value_service.set_value(record_2, "dynamic_analysis_count", 8)
        field_value_service.set_value(record_3, "dynamic_analysis_count", 9)

        service = RecordService(
            record_repo=DailyRecordRepository(db),
            team_repo=TeamRepository(db),
            account_manager_repo=AccountManagerRepository(db),
            cycle_target_repo=CycleTargetRepository(db),
            template_service=_TemplateService(),
            field_value_service=field_value_service,
        )
        analytics = AnalyticsService(service)

        trend_options = dict((key, label) for label, key in analytics.get_analysis_metric_options("trend"))
        ranking_options = dict((key, label) for label, key in analytics.get_analysis_metric_options("ranking"))
        _assert("four_star_customer_count_daily" in trend_options, "四星客户数未进入趋势指标")
        _assert("five_star_customer_count_daily" in trend_options, "五星客户数未进入趋势指标")
        _assert("dynamic_analysis_count" in trend_options, "动态分析字段未进入趋势指标")
        _assert("four_star_customer_count" in ranking_options, "四星客户数未进入排行指标")
        _assert("five_star_customer_count" in ranking_options, "五星客户数未进入排行指标")

        trend = analytics.get_trend_by_day("2026-06-01", "2026-06-02", [1])
        by_date = {row["date"]: row for row in trend}
        _assert(by_date["2026-06-01"]["four_star_customer_count_daily"] == 1, "四星趋势第一天错误")
        _assert(by_date["2026-06-02"]["four_star_customer_count_daily"] == 8, "四星趋势第二天聚合错误")
        _assert(by_date["2026-06-02"]["five_star_customer_count_daily"] == 5, "五星趋势第二天聚合错误")
        _assert(by_date["2026-06-01"]["dynamic_analysis_count"] == 7, "动态字段趋势第一天错误")
        _assert(by_date["2026-06-02"]["dynamic_analysis_count"] == 17, "动态字段趋势第二天聚合错误")

        query_result = service.get_query_summary_grouped_by_account_manager(
            mode="自定义",
            base_date="2026-06-01",
            team_id=None,
            team_ids=[1],
            custom_start="2026-06-01",
            custom_end="2026-06-02",
        )
        ranking = analytics.get_ranking_by_account_manager(query_result["rows"], "four_star_customer_count", top_n=2)
        _assert(ranking[0]["account_manager_name"] == "李四", "四星客户数排行未按区间合计排序")
        _assert(ranking[0]["value"] == 5, "四星客户数排行值错误")

        funnel = analytics.get_funnel_metrics(query_result["rows"])
        _assert_close(funnel["signing_rate"], 4.0 / 13.0, "签约率应按总分子/总分母计算")
        _assert_close(funnel["sales_conversion_rate"], 4.0 / 14.0, "销售转化率应按总分子/总分母计算")
        _assert_close(funnel["warrant_conversion_rate"], 3.0 / 4.0, "权证转化率应按总分子/总分母计算")

        print("[analysis_config] PASS")
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
