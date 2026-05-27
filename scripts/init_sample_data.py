from __future__ import annotations

"""初始化 V1.1 本地测试数据（双团队、跨周期、含版本更新场景）。"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.database import DatabaseManager
from app.db.repositories import (
    AccountManagerRepository,
    CycleTargetRepository,
    DailyRecordRepository,
    SettingsRepository,
    TeamRepository,
    TemplateRepository,
)
from app.services.record_service import RecordService
from app.services.settings_service import SettingsService
from app.services.team_service import TeamService
from app.services.template_service import TemplateService


def _build_services(db: DatabaseManager):
    settings_repo = SettingsRepository(db)
    team_repo = TeamRepository(db)
    account_manager_repo = AccountManagerRepository(db)
    cycle_target_repo = CycleTargetRepository(db)
    record_repo = DailyRecordRepository(db)
    template_repo = TemplateRepository(db)

    settings_service = SettingsService(settings_repo)
    template_service = TemplateService(template_repo, settings_service)
    team_service = TeamService(team_repo, account_manager_repo, cycle_target_repo, settings_service)
    record_service = RecordService(
        record_repo=record_repo,
        team_repo=team_repo,
        account_manager_repo=account_manager_repo,
        cycle_target_repo=cycle_target_repo,
        template_service=template_service,
    )
    return team_service, record_service


def _member_rows(member_ids: list[int], seed: int) -> list[dict]:
    rows: list[dict] = []
    for idx, manager_id in enumerate(member_ids, start=1):
        x = seed + idx
        rows.append(
            {
                "account_manager_id": manager_id,
                "repayment_amount_daily": 1000.0 + x * 123.45,
                "loan_amount_daily": 3000.0 + x * 150.0,
                "intention_daily": 2 + (x % 5),
                "wechat_count_daily": 5 + (x % 7),
                "visit_count_daily": 3 + (x % 6),
                "invalid_visit_count_daily": x % 2,
                "signing_count_daily": 1 + (x % 3),
                "quality_visit_count_daily": 1 + (x % 4),
                "approval_customer_count_daily": 1 + (x % 3),
                "repayment_customer_count_daily": 1 + (x % 2),
                "debt_case_submit_count_daily": x % 2,
                "debt_case_repayment_count_daily": x % 2,
                "debt_case_repayment_amount_daily": float((x % 3) * 500),
                "large_order_repayment_count_daily": x % 2,
                "large_order_repayment_amount_daily": float((x % 2) * 2000),
                "remark": f"样例{seed}-{idx}",
            }
        )
    return rows


def main() -> None:
    db = DatabaseManager()
    db.initialize()

    team_service, record_service = _build_services(db)

    team_configs = [
        {
            "region": "一战区",
            "team_name": "云帆组",
            "team_manager_name": "张经理",
            "members": [
                {"account_manager_name": "王小明", "target_amount": 120000},
                {"account_manager_name": "李小红", "target_amount": 100000},
                {"account_manager_name": "赵小军", "target_amount": 90000},
            ],
        },
        {
            "region": "二战区",
            "team_name": "远航组",
            "team_manager_name": "刘经理",
            "members": [
                {"account_manager_name": "陈晨", "target_amount": 110000},
                {"account_manager_name": "林雪", "target_amount": 95000},
                {"account_manager_name": "周洋", "target_amount": 88000},
            ],
        },
    ]

    cycle_codes = ["2026-03期", "2026-04期"]
    team_ids: list[int] = []
    for cfg in team_configs:
        team_id = None
        for cycle_code in cycle_codes:
            ok, msg, saved_team_id = team_service.save_team_config(
                team_id=team_id,
                region=cfg["region"],
                team_name=cfg["team_name"],
                team_manager_name=cfg["team_manager_name"],
                settlement_cycle_code=cycle_code,
                members=cfg["members"],
            )
            if not ok or not saved_team_id:
                print(f"基础设置保存失败: {msg}")
                return
            team_id = saved_team_id
        team_ids.append(team_id)

    date_list = ["2026-03-30", "2026-04-02", "2026-04-28", "2026-04-29", "2026-05-02"]
    for team_idx, team_id in enumerate(team_ids, start=1):
        member_rows = team_service.list_members_with_targets(team_id, "2026-03期")
        member_ids = [int(x["account_manager_id"]) for x in member_rows]
        for day_idx, record_date in enumerate(date_list, start=1):
            rows = _member_rows(member_ids, seed=team_idx * 10 + day_idx)
            ok, msg, _ = record_service.save_team_day_sheet(team_id, record_date, rows)
            if not ok:
                print(f"写入失败 team_id={team_id} date={record_date}: {msg}")
                return

    # 版本更新场景：同一团队、同一天、同一客户经理修改回款金额，触发 version +1。
    v_team_id = team_ids[0]
    v_date = "2026-04-02"
    v_rows = _member_rows(
        [int(x["account_manager_id"]) for x in team_service.list_members_with_targets(v_team_id, "2026-03期")],
        seed=99,
    )
    v_rows[0]["repayment_amount_daily"] = 88888.88
    ok, msg, stats = record_service.save_team_day_sheet(v_team_id, v_date, v_rows)
    if not ok:
        print(f"版本更新场景失败: {msg}")
        return

    print("V1.1 示例数据初始化成功")
    print(f"团队数: {len(team_ids)}")
    print(f"覆盖更新条数(应>0): {stats.get('updated', 0)}")


if __name__ == "__main__":
    main()
