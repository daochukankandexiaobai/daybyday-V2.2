from __future__ import annotations

import sys
import tempfile
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    from app.db.database import DatabaseManager
    from app.db.repositories import (
        AccountManagerRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        TeamRepository,
    )
    from app.config.field_profiles import PROFILE_PREVIEW_TABLE, PROFILE_QUERY_SUMMARY_TABLE, get_profile_field_keys
    from app.config.field_registry import (
        CATEGORY_CONFIG,
        CATEGORY_FORMULA,
        CATEGORY_RAW_DAILY,
        get_all_fields,
        get_analysis_fields,
        get_entry_fields,
        get_field,
        get_fields_by_group,
        get_fields_for_page,
        get_png_export_fields,
        get_query_summary_fields,
        get_today_display_fields,
        is_field_known,
    )
    from app.config.field_rules import get_aggregation_strategy, get_default_value, get_format_type
    from app.services.field_admin_config_service import FieldAdminConfigService
    from app.services.record_service import RecordService

    fields = get_all_fields()
    _assert(len(fields) >= 40, "字段注册中心字段数量异常")

    required_keys = [
        "record_date",
        "team_name_snapshot",
        "account_manager_name_snapshot",
        "repayment_amount_daily",
        "loan_amount_daily",
        "intention_daily",
        "wechat_count_daily",
        "visit_count_daily",
        "invalid_visit_count_daily",
        "signing_count_daily",
        "quality_visit_count_daily",
        "approval_customer_count_daily",
        "repayment_customer_count_daily",
        "debt_case_submit_count_daily",
        "debt_case_repayment_count_daily",
        "debt_case_repayment_amount_daily",
        "large_order_repayment_count_daily",
        "large_order_repayment_amount_daily",
        "four_star_customer_count_daily",
        "five_star_customer_count_daily",
        "repayment_amount_cumulative",
        "loan_amount_cumulative",
        "invitation_cumulative",
        "signing_count_cumulative",
        "quality_visit_count_cumulative",
        "target_progress",
        "daily_signing_rate",
        "signing_rate",
        "daily_quality_visit_rate",
        "quality_visit_rate",
        "approval_rate",
        "sales_conversion_rate",
        "warrant_conversion_rate",
        "visit_target",
        "quality_visit_target",
        "repayment_target",
        "cycle_repayment_target",
    ]
    for key in required_keys:
        _assert(is_field_known(key), "字段未注册: {}".format(key))

    four_star = get_field("four_star_customer_count_daily")
    five_star = get_field("five_star_customer_count_daily")
    _assert(four_star is not None and four_star.category == CATEGORY_RAW_DAILY, "四星客户数字段分类异常")
    _assert(five_star is not None and five_star.category == CATEGORY_RAW_DAILY, "五星客户数字段分类异常")
    _assert(four_star.editable and five_star.editable, "四星/五星字段应可录入")
    _assert(four_star.default_value == 0 and five_star.default_value == 0, "四星/五星默认值应为 0")

    target_field = get_field("repayment_target")
    _assert(target_field is not None and target_field.category == CATEGORY_CONFIG, "周回款目标字段分类异常")

    formula_field = get_field("target_progress")
    _assert(formula_field is not None and formula_field.category == CATEGORY_FORMULA, "目标完成进度字段分类异常")

    _assert(get_entry_fields(), "数据录入字段集合为空")
    _assert(get_today_display_fields(), "今日展示字段集合为空")
    _assert(get_query_summary_fields(), "查询汇总字段集合为空")
    _assert(get_analysis_fields(), "数据分析字段集合为空")
    _assert(get_png_export_fields(), "PNG 导出字段集合为空")
    _assert(get_fields_for_page("数据录入"), "页面字段查询接口异常")
    _assert(get_fields_by_group("process_behavior"), "过程行为分组为空")

    _assert(get_default_value("four_star_customer_count_daily") == 0, "字段默认值接口异常")
    _assert(get_format_type("repayment_amount_daily") == "amount", "字段格式接口异常")
    _assert(get_aggregation_strategy("visit_count_daily") == "sum", "字段聚合接口异常")

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_field_smoke_"))
    try:
        db_path = tmp_dir / "field_config_smoke.db"
        db = DatabaseManager(str(db_path))
        db.initialize()
        db.initialize()
        conn = db.get_connection()
        try:
            table_names = {
                str(row["name"])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            _assert("field_definitions" in table_names, "缺少 field_definitions 表")
            _assert("field_page_visibility" in table_names, "缺少 field_page_visibility 表")
            _assert("view_templates" in table_names, "缺少 view_templates 表")
            _assert("daily_metric_values" in table_names, "缺少 daily_metric_values 表")

            field_count = int(conn.execute("SELECT COUNT(1) AS c FROM field_definitions").fetchone()["c"])
            visibility_count = int(conn.execute("SELECT COUNT(1) AS c FROM field_page_visibility").fetchone()["c"])
            template_count = int(conn.execute("SELECT COUNT(1) AS c FROM view_templates").fetchone()["c"])
            _assert(field_count >= len(fields), "field_definitions 默认字段未完整初始化")
            _assert(visibility_count > 0, "field_page_visibility 默认配置为空")
            _assert(template_count >= 5, "view_templates 默认模板不足")

            template_keys = {
                str(row["template_key"])
                for row in conn.execute("SELECT template_key FROM view_templates").fetchall()
            }
            for template_key in [
                "entry_default",
                "today_display_default",
                "query_summary_default",
                "png_today_default",
                "analysis_default",
            ]:
                _assert(template_key in template_keys, "默认模板未初始化: {}".format(template_key))

            four_star_row = conn.execute(
                "SELECT * FROM field_definitions WHERE field_key = ?",
                ("four_star_customer_count_daily",),
            ).fetchone()
            _assert(four_star_row is not None, "数据库中缺少四星客户数字段")
            _assert(int(four_star_row["system_field"] or 0) == 1, "系统字段标记异常")
            _assert(str(four_star_row["storage_type"]) == "fixed_column", "固定列存储类型异常")
            _assert(str(four_star_row["storage_column"]) == "four_star_customer_count_daily", "固定列存储列异常")
            field_admin_service = FieldAdminConfigService(db)
            overview = field_admin_service.get_config_overview()
            _assert(overview["enabled_field_count"] > 0, "配置总览字段统计异常")
            health = field_admin_service.run_config_health_check(operator="smoke")
            _assert("summary" in health and "items" in health, "配置健康检查结果异常")
            class _TemplateService:
                @staticmethod
                def get_active_template_version():
                    return "smoke"

            record_service = RecordService(
                record_repo=DailyRecordRepository(db),
                team_repo=TeamRepository(db),
                account_manager_repo=AccountManagerRepository(db),
                cycle_target_repo=CycleTargetRepository(db),
                template_service=_TemplateService(),
            )
            today_defs = record_service.get_today_display_field_definitions()
            query_defs = record_service.get_query_summary_field_definitions()
            today_keys = [str(row.get("field_key", "")) for row in today_defs]
            query_keys = [str(row.get("field_key", "")) for row in query_defs]
            _assert(today_keys == list(get_profile_field_keys(PROFILE_PREVIEW_TABLE)), "today display field order mismatch")
            _assert(query_keys == list(get_profile_field_keys(PROFILE_QUERY_SUMMARY_TABLE)), "query summary field order mismatch")
            _assert("four_star_customer_count_daily" in today_keys, "today display missing four-star field")
            _assert("five_star_customer_count_daily" in today_keys, "today display missing five-star field")
            _assert("four_star_customer_count" in query_keys, "query summary missing four-star field")
            _assert("five_star_customer_count" in query_keys, "query summary missing five-star field")
        finally:
            conn.close()
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)

    print("[smoke] field registry PASS")
    print("[smoke] registered_fields:", len(fields))
    print("[smoke] field_config_tables: fields={}, visibility={}, templates={}".format(
        field_count,
        visibility_count,
        template_count,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
