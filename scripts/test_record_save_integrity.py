from __future__ import annotations

"""Regression checks for partial entry layouts and persisted daily values."""

import shutil
import sys
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


TEST_DYNAMIC_FIELD = "integrity_dynamic_count"


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _build_services(db):
    from app.db.repositories import (
        AccountManagerRepository,
        CycleTargetRepository,
        DailyRecordRepository,
        SettingsRepository,
        TeamRepository,
        TemplateRepository,
    )
    from app.fields.field_value_service import FieldValueService
    from app.services.field_admin_config_service import FieldAdminConfigService
    from app.services.record_service import RecordService
    from app.services.settings_service import SettingsService
    from app.services.team_service import TeamService
    from app.services.template_service import TemplateService

    settings_repo = SettingsRepository(db)
    team_repo = TeamRepository(db)
    account_manager_repo = AccountManagerRepository(db)
    cycle_target_repo = CycleTargetRepository(db)
    record_repo = DailyRecordRepository(db)
    settings_service = SettingsService(settings_repo)
    template_service = TemplateService(TemplateRepository(db), settings_service)
    field_value_service = FieldValueService(db)
    return {
        "team_service": TeamService(team_repo, account_manager_repo, cycle_target_repo, settings_service),
        "record_service": RecordService(
            record_repo=record_repo,
            team_repo=team_repo,
            account_manager_repo=account_manager_repo,
            cycle_target_repo=cycle_target_repo,
            template_service=template_service,
            field_value_service=field_value_service,
        ),
        "account_manager_repo": account_manager_repo,
        "record_repo": record_repo,
        "field_value_service": field_value_service,
        "field_admin_service": FieldAdminConfigService(db),
    }


def _create_team(services):
    ok, message, team_id = services["team_service"].save_team_config(
        team_id=None,
        region="测试区域",
        team_name="数据保护团队",
        team_manager_name="测试经理",
        settlement_cycle_code="2026-06期",
        members=[{"account_manager_name": "测试客户经理", "target_amount": 1000}],
    )
    _assert(ok and team_id, "创建测试团队失败: {}".format(message))
    member = services["account_manager_repo"].list_by_team(int(team_id))[0]
    return int(team_id), int(member["id"])


def _create_dynamic_field(services):
    ok, message = services["field_admin_service"].create_field(
        {
            "field_key": TEST_DYNAMIC_FIELD,
            "label": "完整性动态字段",
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
    _assert(ok, "创建动态字段失败: {}".format(message))
    ok, message = services["field_admin_service"].save_field_visibility(
        TEST_DYNAMIC_FIELD,
        {"data_entry": 1},
        operator="test",
    )
    _assert(ok, "设置动态字段录入可见性失败: {}".format(message))


def main() -> int:
    from app.db.database import DatabaseManager

    temp_dir = Path(tempfile.mkdtemp(prefix="daybyday_record_integrity_"))
    try:
        db = DatabaseManager(str(temp_dir / "integrity.db"))
        db.initialize()
        services = _build_services(db)
        team_id, manager_id = _create_team(services)
        _create_dynamic_field(services)

        ok, message, stats = services["record_service"].save_team_day_sheet(
            team_id=team_id,
            record_date="2026-06-12",
            rows=[
                {
                    "account_manager_id": manager_id,
                    "wechat_count_daily": 5,
                    "visit_count_daily": 3,
                    "remark": "保留备注",
                    TEST_DYNAMIC_FIELD: 7,
                }
            ],
        )
        _assert(ok and stats.get("inserted") == 1, "首次保存失败: {}".format(message))

        first = services["record_repo"].get_by_unique("2026-06-12", team_id, manager_id)
        _assert(first is not None, "首次保存后找不到日报")
        record_id = int(first["id"])
        _assert(first["wechat_count_daily"] == 5, "首次微信量保存错误")
        _assert(services["field_value_service"].get_value(first, TEST_DYNAMIC_FIELD) == 7, "首次动态字段保存错误")

        # Simulate an administrator hiding both a fixed and a dynamic input field.
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE field_page_visibility SET visible = 0 WHERE page_key = 'data_entry' AND field_key = 'wechat_count_daily'"
            )
            conn.execute(
                "UPDATE field_page_visibility SET visible = 0 WHERE page_key = 'data_entry' AND field_key = 'remark'"
            )
            conn.execute(
                "UPDATE field_page_visibility SET visible = 0 WHERE page_key = 'data_entry' AND field_key = ?",
                (TEST_DYNAMIC_FIELD,),
            )
            conn.commit()

        ok, message, stats = services["record_service"].save_team_day_sheet(
            team_id=team_id,
            record_date="2026-06-12",
            rows=[{"account_manager_id": manager_id, "visit_count_daily": 4}],
        )
        _assert(ok and stats.get("updated") == 1, "隐藏字段后保存失败: {}".format(message))

        after_hidden = services["record_repo"].get_by_unique("2026-06-12", team_id, manager_id)
        _assert(after_hidden is not None, "隐藏字段保存后找不到日报")
        _assert(after_hidden["wechat_count_daily"] == 5, "隐藏固定字段被错误清零")
        _assert(after_hidden["remark"] == "保留备注", "隐藏备注被错误清空")
        _assert(
            services["field_value_service"].get_value(after_hidden, TEST_DYNAMIC_FIELD) == 7,
            "隐藏动态字段被错误清零",
        )
        _assert(after_hidden["visit_count_daily"] == 4, "显式提交字段未更新")

        # Re-enable the fixed field. Explicit zero remains a valid intentional update.
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE field_page_visibility SET visible = 1 WHERE page_key = 'data_entry' AND field_key = 'wechat_count_daily'"
            )
            conn.commit()
        ok, message, _stats = services["record_service"].save_team_day_sheet(
            team_id=team_id,
            record_date="2026-06-12",
            rows=[{"account_manager_id": manager_id, "wechat_count_daily": 0}],
        )
        _assert(ok, "显式清零保存失败: {}".format(message))
        after_zero = services["record_repo"].get_by_id(record_id)
        _assert(after_zero is not None and after_zero["wechat_count_daily"] == 0, "显式 0 未正确保存")
        _assert(after_zero["visit_count_daily"] == 4, "未提交字段在显式清零时被改写")

        print("[record_integrity] PASS")
        return 0
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
