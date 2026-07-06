from __future__ import annotations

import sys
from pathlib import Path

from app.utils.qt_compat import QApplication, app_exec

from app.db.database import DatabaseManager
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
from app.fields.config_pack_service import ConfigPackService
from app.services.auth_service import AuthService
from app.services.admin_action_log_service import AdminActionLogService
from app.services.admin_data_service import AdminDataService
from app.services.admin_team_service import AdminTeamService
from app.services.analytics_service import AnalyticsService
from app.services.excel_service import ExcelService
from app.services.export_service import ExportService
from app.services.field_admin_config_service import FieldAdminConfigService
from app.services.import_service import ImportService
from app.services.legacy_migration_service import LegacyMigrationService
from app.services.record_service import RecordService
from app.services.report_image_service import ReportImageService
from app.services.settings_service import SettingsService
from app.services.summary_service import SummaryService
from app.services.team_service import TeamService
from app.services.template_service import TemplateService
from app.services.star_customer_alert_service import StarCustomerAlertService
from app.services.target_alert_service import TargetAlertService
from app.services.target_progress_service import TargetProgressService
from app.services.ui_scale_manager import UIScaleManager
from app.services.view_scale_service import ViewScaleService
from app.services.weekly_target_service import WeeklyTargetService
from app.ui.main_window import MainWindow
from app.utils.error_utils import install_global_exception_handler
from app.utils.log_utils import configure_app_logging, get_logger
from app.utils.runtime_check import collect_runtime_report


def build_services(db_manager: DatabaseManager) -> dict:
    settings_repo = SettingsRepository(db_manager)
    admin_repo = AdminUserRepository(db_manager)
    template_repo = TemplateRepository(db_manager)
    import_log_repo = ImportLogRepository(db_manager)
    admin_action_log_repo = AdminActionLogRepository(db_manager)

    team_repo = TeamRepository(db_manager)
    account_manager_repo = AccountManagerRepository(db_manager)
    cycle_target_repo = CycleTargetRepository(db_manager)
    weekly_target_repo = WeeklyTargetRepository(db_manager)
    record_repo = DailyRecordRepository(db_manager)
    field_value_service = FieldValueService(db_manager)

    settings_service = SettingsService(settings_repo)
    view_scale_service = ViewScaleService(settings_service)
    template_service = TemplateService(template_repo, settings_service)
    team_service = TeamService(team_repo, account_manager_repo, cycle_target_repo, settings_service)
    record_service = RecordService(
        record_repo=record_repo,
        team_repo=team_repo,
        account_manager_repo=account_manager_repo,
        cycle_target_repo=cycle_target_repo,
        template_service=template_service,
        field_value_service=field_value_service,
    )
    analytics_service = AnalyticsService(record_service=record_service)
    weekly_target_service = WeeklyTargetService(
        weekly_target_repo=weekly_target_repo,
        cycle_target_repo=cycle_target_repo,
        team_repo=team_repo,
        account_manager_repo=account_manager_repo,
    )
    target_progress_service = TargetProgressService()
    star_customer_alert_service = StarCustomerAlertService(
        record_repo=record_repo,
        account_manager_repo=account_manager_repo,
        team_repo=team_repo,
    )
    target_alert_service = TargetAlertService(
        record_repo=record_repo,
        weekly_target_service=weekly_target_service,
        target_progress_service=target_progress_service,
    )
    admin_action_log_service = AdminActionLogService(admin_action_log_repo)
    admin_team_service = AdminTeamService(
        team_service=team_service,
        team_repo=team_repo,
        settings_service=settings_service,
        admin_action_log_service=admin_action_log_service,
    )
    admin_data_service = AdminDataService(
        record_repo=record_repo,
        team_repo=team_repo,
        account_manager_repo=account_manager_repo,
        record_service=record_service,
        admin_action_log_service=admin_action_log_service,
    )
    field_admin_config_service = FieldAdminConfigService(
        db_manager,
        admin_action_log_service=admin_action_log_service,
    )
    config_pack_service = ConfigPackService(
        db_manager,
        admin_action_log_service=admin_action_log_service,
        settings_service=settings_service,
    )

    services = {
        "settings_service": settings_service,
        "view_scale_service": view_scale_service,
        "template_service": template_service,
        "team_service": team_service,
        "record_service": record_service,
        "field_value_service": field_value_service,
        "analytics_service": analytics_service,
        "weekly_target_service": weekly_target_service,
        "target_progress_service": target_progress_service,
        "target_alert_service": target_alert_service,
        "star_customer_alert_service": star_customer_alert_service,
        "auth_service": AuthService(admin_repo),
        "export_service": ExportService(
            record_service,
            team_service,
            settings_service,
            template_service,
            target_alert_service=target_alert_service,
            star_customer_alert_service=star_customer_alert_service,
        ),
        "import_service": ImportService(
            record_repo=record_repo,
            import_log_repo=import_log_repo,
            settings_service=settings_service,
            template_service=template_service,
            record_service=record_service,
            team_service=team_service,
            team_repo=team_repo,
            account_manager_repo=account_manager_repo,
        ),
        "legacy_migration_service": LegacyMigrationService(
            db_manager=db_manager,
            template_service=template_service,
            record_service=record_service,
        ),
        "summary_service": SummaryService(
            record_repo,
            import_log_repo,
            cycle_target_repo,
            target_alert_service=target_alert_service,
            star_customer_alert_service=star_customer_alert_service,
        ),
        "excel_service": ExcelService(db_manager),
        "report_image_service": ReportImageService(db_manager),
        "ui_scale_manager": UIScaleManager(view_scale_service),
        "admin_action_log_service": admin_action_log_service,
        "admin_team_service": admin_team_service,
        "admin_data_service": admin_data_service,
        "field_admin_config_service": field_admin_config_service,
        "config_pack_service": config_pack_service,
    }
    return services


def main() -> int:
    configure_app_logging()
    logger = get_logger("main")
    logger.info("应用启动")
    install_global_exception_handler()

    report = collect_runtime_report(Path(__file__).resolve().parent)
    for msg in report.get("warnings", []):
        logger.warning("运行环境提示: %s", msg)
    errors = report.get("errors", [])
    if errors:
        raise RuntimeError("运行环境检查失败: " + "; ".join(errors))

    db_manager = DatabaseManager()
    db_manager.initialize()
    logger.info("数据库初始化完成: %s", db_manager.db_path)

    app = QApplication(sys.argv)
    services = build_services(db_manager)

    window = MainWindow(services=services, db_path=str(db_manager.db_path))
    window.show()
    logger.info("主窗口已显示")

    return app_exec(app)


if __name__ == "__main__":
    raise SystemExit(main())
