from __future__ import annotations

"""Win7/PySide2 full smoke test using an isolated temporary database."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.database import DatabaseManager
from app.utils.date_utils import settlement_cycle_display_code
from app.utils.field_utils import format_field_value
from app.utils.qt_compat import QApplication, QDate
from main import build_services
from app.ui.main_window import MainWindow


def _create_test_team(services, record_date: str) -> int:
    ok, message, team_id = services["team_service"].save_team_config(
        team_id=None,
        region="冒烟区域",
        team_name="冒烟团队",
        team_manager_name="冒烟经理",
        settlement_cycle_code=settlement_cycle_display_code(record_date=record_date),
        members=[{"account_manager_name": "冒烟客户经理", "target_amount": 1000}],
    )
    assert ok and team_id, "创建测试团队失败: {}".format(message)
    return int(team_id)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    temp_dir = Path(tempfile.mkdtemp(prefix="daybyday_win7_smoke_"))
    try:
        _app = QApplication.instance() or QApplication([])
        db = DatabaseManager(str(temp_dir / "win7_smoke.db"))
        db.initialize()
        services = build_services(db)

        # 1) 主窗口与经理端 Tab 初始化
        window = MainWindow(services=services, db_path=str(db.db_path))
        assert window.tabs.count() >= 5, "经理端标签页初始化失败"

        # 2) 管理员登录校验（临时数据库中的默认账号）
        assert services["auth_service"].login("admin", "admin123"), "默认管理员登录失败"

        # 3) 创建临时团队和日报数据，不读取或写入真实业务数据库。
        today = QDate.currentDate().toString("yyyy-MM-dd")
        team_id = _create_test_team(services, today)
        sheet = services["record_service"].get_team_day_sheet(team_id, today)
        assert sheet.get("ok"), "获取日报表失败"
        rows = [dict(row) for row in sheet.get("rows", [])]
        assert rows, "临时团队缺少客户经理"
        rows[0].update(
            {
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
            }
        )
        ok, message, _stats = services["record_service"].save_team_day_sheet(
            team_id,
            today,
            rows,
            source_type="local",
        )
        assert ok, "日报保存失败: {}".format(message)

        # 4) 今日展示、查询汇总
        preview_rows = services["record_service"].get_preview_rows(team_id, today)
        assert preview_rows, "今日展示数据获取失败"
        query = services["record_service"].get_query_summary_grouped_by_account_manager(
            mode="某日",
            base_date=today,
            team_id=team_id,
        )
        assert query.get("rows") and query.get("summary"), "查询汇总结果结构异常"

        # 5) JSON 导出与导入
        export_dir = temp_dir / "exports"
        ok, message, json_path = services["export_service"].export_json(
            mode="某日",
            team_id=team_id,
            base_date=today,
            custom_start="",
            custom_end="",
            output_dir=str(export_dir),
        )
        assert ok and json_path, "JSON 导出失败: {}".format(message)
        preview = services["import_service"].preview_files([json_path])
        assert preview and preview[0].get("is_valid"), "JSON 导入预览失败"
        import_result = services["import_service"].import_files([json_path], allow_template_mismatch=False)
        assert import_result, "JSON 导入执行失败"

        # 6) Excel 导出
        start_date = query.get("start_date", today)
        end_date = query.get("end_date", today)
        excel_path = export_dir / "win7_smoke_summary.xlsx"
        dataset = services["summary_service"].build_company_dataset(start_date, end_date)
        ok, info = services["excel_service"].export_company_report(
            str(excel_path),
            "Win7兼容冒烟",
            start_date,
            end_date,
            dataset,
        )
        assert ok and excel_path.exists(), "Excel 导出失败: {}".format(info)

        # 7) PNG 四张分图与总图。表头和字段来自当前配置，避免维护测试专用硬编码列。
        field_defs = services["record_service"].get_today_display_field_definitions()
        field_keys = [str(item.get("field_key", "")) for item in field_defs]
        headers = [str(item.get("label", "")) for item in field_defs]
        summary_row = services["record_service"].build_today_display_summary_row(preview_rows, today)
        table_rows = [
            [format_field_value(field_key, row.get(field_key)) for field_key in field_keys]
            for row in preview_rows + [summary_row]
        ]
        team = services["team_service"].get_team(team_id) or {}
        png_result = services["report_image_service"].export_today_preview_bundle(
            output_dir=export_dir,
            record_date=today,
            settlement_cycle_code=sheet.get("cycle_code", ""),
            region=str(team.get("region", "")),
            team_name=str(team.get("team_name", "")),
            team_manager_name=str(team.get("team_manager_name", "")),
            headers=headers,
            rows=table_rows,
            field_keys=field_keys,
        )
        assert Path(str(png_result["total_path"])).exists(), "PNG 总图未生成"

        window.close()
        print("[smoke] PASS")
        print("[smoke] temporary_dir:", temp_dir)
        return 0
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
