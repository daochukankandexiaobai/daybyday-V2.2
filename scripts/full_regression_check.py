from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


TEST_FIELD_KEY = "regression_dynamic_count"


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _qt_available():
    try:
        from app.utils.qt_compat import QApplication  # noqa: F401

        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _build_services(db):
    from app.db.repositories import (
        AccountManagerRepository,
        AdminActionLogRepository,
        AdminUserRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        ImportLogRepository,
        SettingsRepository,
        TeamRepository,
        TemplateRepository,
        WeeklyTargetRepository,
    )
    from app.fields.field_value_service import FieldValueService
    from app.services.admin_action_log_service import AdminActionLogService
    from app.services.excel_service import ExcelService
    from app.services.export_service import ExportService
    from app.services.field_admin_config_service import FieldAdminConfigService
    from app.services.import_service import ImportService
    from app.services.record_service import RecordService
    from app.services.settings_service import SettingsService
    from app.services.summary_service import SummaryService
    from app.services.team_service import TeamService
    from app.services.template_service import TemplateService

    settings_repo = SettingsRepository(db)
    team_repo = TeamRepository(db)
    account_manager_repo = AccountManagerRepository(db)
    cycle_target_repo = CycleTargetRepository(db)
    record_repo = DailyRecordRepository(db)
    import_log_repo = ImportLogRepository(db)
    template_repo = TemplateRepository(db)
    admin_action_log_repo = AdminActionLogRepository(db)

    settings_service = SettingsService(settings_repo)
    template_service = TemplateService(template_repo, settings_service)
    team_service = TeamService(team_repo, account_manager_repo, cycle_target_repo, settings_service)
    field_value_service = FieldValueService(db)
    record_service = RecordService(
        record_repo=record_repo,
        team_repo=team_repo,
        account_manager_repo=account_manager_repo,
        cycle_target_repo=cycle_target_repo,
        template_service=template_service,
        field_value_service=field_value_service,
    )
    admin_log_service = AdminActionLogService(admin_action_log_repo)
    field_admin_service = FieldAdminConfigService(db, admin_action_log_service=admin_log_service)
    export_service = ExportService(record_service, team_service, settings_service, template_service)
    import_service = ImportService(
        record_repo=record_repo,
        import_log_repo=import_log_repo,
        settings_service=settings_service,
        template_service=template_service,
        record_service=record_service,
        team_service=team_service,
        team_repo=team_repo,
        account_manager_repo=account_manager_repo,
    )
    summary_service = SummaryService(record_repo, import_log_repo, cycle_target_repo)

    return {
        "settings_repo": settings_repo,
        "team_repo": team_repo,
        "account_manager_repo": account_manager_repo,
        "cycle_target_repo": cycle_target_repo,
        "record_repo": record_repo,
        "weekly_target_repo": WeeklyTargetRepository(db),
        "admin_repo": AdminUserRepository(db),
        "settings_service": settings_service,
        "template_service": template_service,
        "team_service": team_service,
        "field_value_service": field_value_service,
        "record_service": record_service,
        "field_admin_service": field_admin_service,
        "export_service": export_service,
        "import_service": import_service,
        "summary_service": summary_service,
        "excel_service": ExcelService(db),
    }


def _setup_team(services):
    ok, message, team_id = services["team_service"].save_team_config(
        team_id=None,
        region="测试区域",
        team_name="测试团队",
        team_manager_name="测试经理",
        settlement_cycle_code="2026-06期",
        members=[{"account_manager_name": "张三", "target_amount": 1000}],
    )
    _assert(ok and team_id, "team setup failed: {}".format(message))
    members = services["account_manager_repo"].list_by_team(int(team_id))
    _assert(members, "account manager missing after team setup")
    return int(team_id), int(members[0]["id"])


def _configure_dynamic_field(services):
    from app.fields.registry import (
        PAGE_ANALYSIS,
        PAGE_DATA_ENTRY,
        PAGE_EXCEL_EXPORT,
        PAGE_JSON_EXPORT,
        PAGE_PNG_TODAY,
        PAGE_QUERY_SUMMARY,
        PAGE_TODAY_DISPLAY,
    )

    service = services["field_admin_service"]
    ok, message = service.create_field(
        {
            "field_key": TEST_FIELD_KEY,
            "label": "回归动态数",
            "data_type": "int",
            "category": "raw_daily",
            "group_key": "process_behavior",
            "default_value": "0",
            "aggregation": "sum",
            "enabled": 1,
            "editable": 1,
        },
        operator="regression",
    )
    _assert(ok, message)
    ok, message = service.save_field_visibility(
        TEST_FIELD_KEY,
        {
            PAGE_DATA_ENTRY: 1,
            PAGE_TODAY_DISPLAY: 1,
            PAGE_QUERY_SUMMARY: 1,
            PAGE_ANALYSIS: 1,
            PAGE_PNG_TODAY: 1,
            PAGE_EXCEL_EXPORT: 1,
            PAGE_JSON_EXPORT: 1,
        },
        operator="regression",
    )
    _assert(ok, message)


def _save_daily_record(services, team_id, manager_id):
    ok, message, stats = services["record_service"].save_team_day_sheet(
        team_id=team_id,
        record_date="2026-06-01",
        rows=[
            {
                "account_manager_id": manager_id,
                "repayment_amount_daily": 100.0,
                "loan_amount_daily": 80.0,
                "visit_count_daily": 5,
                "invalid_visit_count_daily": 1,
                "signing_count_daily": 2,
                "quality_visit_count_daily": 2,
                "approval_customer_count_daily": 1,
                "repayment_customer_count_daily": 1,
                "four_star_customer_count_daily": 2,
                "five_star_customer_count_daily": 3,
                TEST_FIELD_KEY: 9,
            }
        ],
    )
    _assert(ok and stats.get("inserted") == 1, "daily save failed: {}".format(message))


def _check_display_and_query(services, team_id):
    preview_rows = services["record_service"].get_preview_rows(team_id, "2026-06-01")
    _assert(preview_rows and preview_rows[0].get(TEST_FIELD_KEY) == 9, "today display cannot read dynamic field")

    result = services["record_service"].get_query_summary_grouped_by_account_manager(
        mode="自定义",
        base_date="2026-06-01",
        team_id=None,
        team_ids=[team_id],
        custom_start="2026-06-01",
        custom_end="2026-06-01",
    )
    _assert(result["rows"] and result["rows"][0].get(TEST_FIELD_KEY) == 9, "query summary cannot aggregate dynamic field")


def _check_exports(services, team_id, tmp_dir):
    json_dir = tmp_dir / "json"
    ok, message, json_path = services["export_service"].export_json(
        mode="自定义",
        team_id=team_id,
        base_date="2026-06-01",
        custom_start="2026-06-01",
        custom_end="2026-06-01",
        output_dir=str(json_dir),
    )
    _assert(ok and json_path and Path(json_path).exists(), "JSON export failed: {}".format(message))
    results = services["import_service"].import_files([json_path], allow_template_mismatch=True)
    _assert(results, "JSON import produced no result")

    dataset = services["summary_service"].build_company_dataset("2026-06-01", "2026-06-01")
    excel_path = tmp_dir / "regression.xlsx"
    ok, message = services["excel_service"].export_company_report(
        str(excel_path),
        "测试公司",
        "2026-06-01",
        "2026-06-01",
        dataset,
    )
    _assert(ok and excel_path.exists(), "Excel export failed: {}".format(message))


def _check_png_if_possible(services, team_id, tmp_dir):
    qt_ok, reason = _qt_available()
    if not qt_ok:
        print("[full_regression] PNG/gui skipped: {}".format(reason))
        return
    try:
        from app.services.report_image_service import ReportImageService
    except Exception as exc:  # noqa: BLE001
        print("[full_regression] PNG skipped: {}".format(exc))
        return

    field_defs = services["record_service"].get_today_display_field_definitions()
    headers = [str(row.get("label", "")) for row in field_defs]
    field_keys = [str(row.get("field_key", "")) for row in field_defs]
    rows = services["record_service"].get_preview_rows(team_id, "2026-06-01")
    summary = services["record_service"].build_today_display_summary_row(rows, "2026-06-01")
    table_rows = [[str(row.get(field_key, "")) for field_key in field_keys] for row in rows + [summary]]
    result = ReportImageService(services["record_repo"].db).export_today_preview_bundle(
        output_dir=str(tmp_dir / "png"),
        record_date="2026-06-01",
        settlement_cycle_code="2026-06期",
        region="测试区域",
        team_name="测试团队",
        team_manager_name="测试经理",
        headers=headers,
        rows=table_rows,
        field_keys=field_keys,
    )
    _assert(Path(result["total_path"]).exists(), "PNG total image missing")


def _check_analysis(services):
    from app.services.analytics_service import AnalyticsService

    analytics = AnalyticsService(services["record_service"])
    options = dict((key, label) for label, key in analytics.get_analysis_metric_options("trend"))
    _assert(TEST_FIELD_KEY in options, "analysis metrics cannot read dynamic field")


def _check_config_fallback(services):
    from app.fields.registry import PAGE_TODAY_DISPLAY

    with services["record_repo"].db.get_connection() as conn:
        conn.execute(
            """
            UPDATE view_templates
            SET config_json = '{bad json'
            WHERE template_key = 'today_display_default'
            """
        )
        conn.execute(
            """
            DELETE FROM field_page_visibility
            WHERE page_key = ?
            """,
            (PAGE_TODAY_DISPLAY,),
        )
        conn.commit()
    rows = services["record_service"].get_today_display_field_definitions()
    _assert(rows, "broken template should fall back to default fields")


def _check_config_backup_restore(services, tmp_dir):
    backup_path = tmp_dir / "field_config_backup.json"
    ok, message = services["field_admin_service"].export_field_config_to_json(str(backup_path), operator="regression")
    _assert(ok and backup_path.exists(), "config export failed: {}".format(message))
    ok, message = services["field_admin_service"].import_field_config_from_json(str(backup_path), operator="regression")
    _assert(ok, "config import failed: {}".format(message))
    ok, message = services["field_admin_service"].reset_field_config_to_default(operator="regression")
    _assert(ok, "config reset failed: {}".format(message))


def main():
    from app.db.database import DatabaseManager

    tmp_dir = Path(tempfile.mkdtemp(prefix="daybyday_full_regression_"))
    try:
        db = DatabaseManager(str(tmp_dir / "regression.db"))
        db.initialize()
        services = _build_services(db)

        with db.get_connection() as conn:
            for table in ("field_definitions", "field_page_visibility", "view_templates", "daily_metric_values"):
                row = conn.execute(
                    "SELECT COUNT(1) AS c FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                _assert(int(row["c"] or 0) == 1, "{} table missing".format(table))
            default_field = conn.execute(
                "SELECT field_key FROM field_definitions WHERE field_key = 'repayment_amount_daily'"
            ).fetchone()
            _assert(default_field is not None, "default field missing")

        team_id, manager_id = _setup_team(services)
        _configure_dynamic_field(services)
        _save_daily_record(services, team_id, manager_id)
        _check_display_and_query(services, team_id)
        _check_exports(services, team_id, tmp_dir)
        _check_png_if_possible(services, team_id, tmp_dir)
        _check_analysis(services)
        _check_config_backup_restore(services, tmp_dir)
        _check_config_fallback(services)

        qt_ok, reason = _qt_available()
        if qt_ok:
            print("[full_regression] GUI import PASS")
        else:
            print("[full_regression] GUI import skipped: {}".format(reason))

        print("[full_regression] PASS")
        return 0
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
