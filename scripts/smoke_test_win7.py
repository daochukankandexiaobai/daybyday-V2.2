from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.database import DatabaseManager
from app.utils.format_utils import format_int as fmt_int, format_money as fmt_money, format_percent as fmt_pct
from app.utils.qt_compat import QApplication, QDate
from main import build_services
from app.ui.main_window import MainWindow


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    _app = QApplication.instance() or QApplication([])

    db = DatabaseManager()
    db.initialize()
    services = build_services(db)

    # 1) 主窗口与全部经理端 Tab 初始化
    window = MainWindow(services=services, db_path=str(db.db_path))
    assert window.tabs.count() >= 5, "经理端标签页初始化失败"

    # 2) 管理员登录校验（默认账号）
    assert services["auth_service"].login("admin", "admin123"), "默认管理员登录失败"

    # 3) 团队基础数据
    team_id = services["team_service"].get_current_team_id()
    assert team_id > 0, "未找到当前团队"

    # 4) 确保今日数据可保存（若无记录则按当前名单保存一版零值）
    today = QDate.currentDate().toString("yyyy-MM-dd")
    sheet = services["record_service"].get_team_day_sheet(team_id, today)
    assert sheet.get("ok"), "获取日报表失败"
    rows = sheet.get("rows", [])
    save_rows = []
    for row in rows:
        save_rows.append(
            {
                "account_manager_id": int(row.get("account_manager_id", 0)),
                "account_manager_name": str(row.get("account_manager_name", "")),
                "repayment_amount_daily": float(row.get("repayment_amount_daily", 0) or 0),
                "loan_amount_daily": float(row.get("loan_amount_daily", 0) or 0),
                "intention_daily": int(row.get("intention_daily", 0) or 0),
                "wechat_count_daily": int(row.get("wechat_count_daily", 0) or 0),
                "visit_count_daily": int(row.get("visit_count_daily", 0) or 0),
                "invalid_visit_count_daily": int(row.get("invalid_visit_count_daily", 0) or 0),
                "signing_count_daily": int(row.get("signing_count_daily", 0) or 0),
                "quality_visit_count_daily": int(row.get("quality_visit_count_daily", 0) or 0),
                "approval_customer_count_daily": int(row.get("approval_customer_count_daily", 0) or 0),
                "repayment_customer_count_daily": int(row.get("repayment_customer_count_daily", 0) or 0),
                "debt_case_submit_count_daily": int(row.get("debt_case_submit_count_daily", 0) or 0),
                "debt_case_repayment_count_daily": int(row.get("debt_case_repayment_count_daily", 0) or 0),
                "debt_case_repayment_amount_daily": float(row.get("debt_case_repayment_amount_daily", 0) or 0),
                "large_order_repayment_count_daily": int(row.get("large_order_repayment_count_daily", 0) or 0),
                "large_order_repayment_amount_daily": float(row.get("large_order_repayment_amount_daily", 0) or 0),
                "remark": str(row.get("remark", "")),
            }
        )

    ok, _, _ = services["record_service"].save_team_day_sheet(team_id, today, save_rows, source_type="local")
    assert ok, "日报保存失败"

    # 5) 今日展示可加载
    preview_rows = services["record_service"].get_preview_rows(team_id, today)
    assert isinstance(preview_rows, list), "今日展示数据获取失败"

    # 6) 查询汇总聚合可用
    query = services["record_service"].get_query_summary_grouped_by_account_manager(
        mode="某日",
        base_date=today,
        team_id=team_id,
    )
    assert "rows" in query and "summary" in query, "查询汇总结果结构异常"

    # 7) JSON 导出 -> 导入
    export_dir = BASE_DIR / "tmp_exports" / "win7_smoke"
    ok, msg, json_path = services["export_service"].export_json(
        mode="某日",
        team_id=team_id,
        base_date=today,
        custom_start="",
        custom_end="",
        output_dir=str(export_dir),
    )
    assert ok and json_path, "JSON 导出失败: {}".format(msg)

    preview = services["import_service"].preview_files([json_path])
    assert preview and preview[0].get("is_valid"), "JSON 导入预览失败"

    import_result = services["import_service"].import_files([json_path], allow_template_mismatch=False)
    assert import_result, "JSON 导入执行失败"

    # 8) Excel 导出
    start_date = query.get("start_date", today)
    end_date = query.get("end_date", today)
    excel_path = export_dir / "win7_smoke_summary.xlsx"
    payload = services["summary_service"].build_company_dataset(start_date, end_date)
    ok, info = services["excel_service"].export_company_report(
        str(excel_path),
        "Win7兼容冒烟",
        start_date,
        end_date,
        payload,
    )
    assert ok, "Excel 导出失败: {}".format(info)

    # 9) PNG 分图 + 总图
    team = services["team_service"].get_team(team_id) or {}
    headers = [
        "日期", "客户经理", "结算周期目标", "累计回款金额", "累计放款金额", "当日回款金额", "目标完成进度", "当日放款金额",
        "当日意向", "当日微信量", "当日上门量", "累计邀约", "当日无效上门", "当日签约量", "累计签约量", "当日签约率",
        "当日优质上门", "当日优质上门率", "累计优质上门量", "当日批复客户数", "当日批复率", "当日回款客户数", "当日销售转化率",
        "权证转化率", "当日债重进件数", "当日债重回款件数", "当日债重回款金额", "当日大单回款笔数", "当日大单回款金额",
    ]

    table_rows = []
    for row in preview_rows:
        table_rows.append([
            row.get("record_date", ""),
            row.get("account_manager_name", ""),
            fmt_money(row.get("cycle_target")),
            fmt_money(row.get("repayment_amount_cumulative")),
            fmt_money(row.get("loan_amount_cumulative")),
            fmt_money(row.get("repayment_amount_daily")),
            fmt_pct(row.get("target_progress")),
            fmt_money(row.get("loan_amount_daily")),
            fmt_int(row.get("intention_daily")),
            fmt_int(row.get("wechat_count_daily")),
            fmt_int(row.get("visit_count_daily")),
            fmt_int(row.get("invitation_cumulative")),
            fmt_int(row.get("invalid_visit_count_daily")),
            fmt_int(row.get("signing_count_daily")),
            fmt_int(row.get("signing_count_cumulative")),
            fmt_pct(row.get("daily_signing_rate")),
            fmt_int(row.get("quality_visit_count_daily")),
            fmt_pct(row.get("daily_quality_visit_rate")),
            fmt_int(row.get("quality_visit_count_cumulative")),
            fmt_int(row.get("approval_customer_count_daily")),
            fmt_pct(row.get("daily_approval_rate")),
            fmt_int(row.get("repayment_customer_count_daily")),
            fmt_pct(row.get("daily_sales_conversion_rate")),
            fmt_pct(row.get("warrant_conversion_rate")),
            fmt_int(row.get("debt_case_submit_count_daily")),
            fmt_int(row.get("debt_case_repayment_count_daily")),
            fmt_money(row.get("debt_case_repayment_amount_daily")),
            fmt_int(row.get("large_order_repayment_count_daily")),
            fmt_money(row.get("large_order_repayment_amount_daily")),
        ])

    png_result = services["report_image_service"].export_today_preview_bundle(
        output_dir=export_dir,
        record_date=today,
        settlement_cycle_code=sheet.get("cycle_code", ""),
        region=str(team.get("region", "")),
        team_name=str(team.get("team_name", "")),
        team_manager_name=str(team.get("team_manager_name", "")),
        headers=headers,
        rows=table_rows,
    )
    assert Path(str(png_result["total_path"])) .exists(), "PNG 总图未生成"

    print("[smoke] PASS")
    print("[smoke] json:", json_path)
    print("[smoke] excel:", excel_path)
    print("[smoke] png_total:", png_result["total_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
