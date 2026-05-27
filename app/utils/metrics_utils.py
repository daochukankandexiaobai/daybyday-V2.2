from __future__ import annotations

from typing import Any


def ratio_or_none(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def aggregate_daily_rows(
    rows: list[dict[str, Any]],
    team_target: float = 0.0,
    include_progress: bool = True,
) -> dict[str, Any]:
    """统一汇总口径。

    说明：
    - 累计邀约 = 累计上门
    - 签约率 = 累计签约 / (累计上门 - 累计无效上门)
    - 优质上门率 = 累计优质上门 / 累计上门
    - 批复率 = 当日批复客户数累计 / 当日签约量累计（基于日报原始值重算）
    - 回款转化率 = 当日回款客户数累计 / 当日上门量累计（基于日报原始值重算）
    - 分母为0返回 None（UI/Excel 显示为空）
    """

    repayment_amount_cumulative = sum(float(r.get("repayment_amount_daily", 0) or 0) for r in rows)
    loan_amount_cumulative = sum(float(r.get("loan_amount_daily", 0) or 0) for r in rows)
    visit_count_cumulative = sum(int(r.get("visit_count_daily", 0) or 0) for r in rows)
    invalid_visit_count_cumulative = sum(int(r.get("invalid_visit_count_daily", 0) or 0) for r in rows)
    signing_count_cumulative = sum(int(r.get("signing_count_daily", 0) or 0) for r in rows)
    quality_visit_count_cumulative = sum(int(r.get("quality_visit_count_daily", 0) or 0) for r in rows)
    approval_customer_count_cumulative = sum(int(r.get("approval_customer_count_daily", 0) or 0) for r in rows)
    repayment_customer_count_cumulative = sum(int(r.get("repayment_customer_count_daily", 0) or 0) for r in rows)
    four_star_customer_count = sum(int(r.get("four_star_customer_count_daily", 0) or 0) for r in rows)
    five_star_customer_count = sum(int(r.get("five_star_customer_count_daily", 0) or 0) for r in rows)

    valid_visit = visit_count_cumulative - invalid_visit_count_cumulative
    signing_rate = ratio_or_none(signing_count_cumulative, valid_visit)
    quality_visit_rate = ratio_or_none(quality_visit_count_cumulative, visit_count_cumulative)
    approval_rate = ratio_or_none(approval_customer_count_cumulative, signing_count_cumulative)
    repayment_conversion_rate = ratio_or_none(repayment_customer_count_cumulative, visit_count_cumulative)

    target_progress = ratio_or_none(repayment_amount_cumulative, team_target) if include_progress else None

    return {
        "record_count": len(rows),
        "repayment_amount_cumulative": repayment_amount_cumulative,
        "loan_amount_cumulative": loan_amount_cumulative,
        "invitation_cumulative": visit_count_cumulative,
        "visit_count_cumulative": visit_count_cumulative,
        "invalid_visit_count_cumulative": invalid_visit_count_cumulative,
        "four_star_customer_count": four_star_customer_count,
        "five_star_customer_count": five_star_customer_count,
        "signing_count_cumulative": signing_count_cumulative,
        "quality_visit_count_cumulative": quality_visit_count_cumulative,
        "approval_customer_count_cumulative": approval_customer_count_cumulative,
        "repayment_customer_count_cumulative": repayment_customer_count_cumulative,
        "signing_rate": signing_rate,
        "quality_visit_rate": quality_visit_rate,
        "approval_rate": approval_rate,
        "repayment_conversion_rate": repayment_conversion_rate,
        "target_progress": target_progress,
        "team_cycle_target": float(team_target),
    }
