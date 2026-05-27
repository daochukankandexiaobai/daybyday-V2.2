from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TeamDailyRowInput:
    """One raw daily row: account manager x record date."""

    account_manager_id: int
    account_manager_name: str
    repayment_amount_daily: float = 0.0
    loan_amount_daily: float = 0.0
    intention_daily: int = 0
    wechat_count_daily: int = 0
    visit_count_daily: int = 0
    invalid_visit_count_daily: int = 0
    signing_count_daily: int = 0
    quality_visit_count_daily: int = 0
    approval_customer_count_daily: int = 0
    repayment_customer_count_daily: int = 0
    debt_case_submit_count_daily: int = 0
    debt_case_repayment_count_daily: int = 0
    debt_case_repayment_amount_daily: float = 0.0
    large_order_repayment_count_daily: int = 0
    large_order_repayment_amount_daily: float = 0.0
    remark: str = ""


@dataclass
class DateRange:
    start_date: str
    end_date: str


@dataclass
class ImportActionResult:
    file_name: str
    file_path: str
    export_id: str
    template_version: str
    result: str
    message: str
    affected_record_count: int


@dataclass
class AggregationRow:
    group_name: str
    record_count: int
    repayment_amount_cumulative: float
    loan_amount_cumulative: float
    invitation_cumulative: int
    signing_count_cumulative: int
    quality_visit_count_cumulative: int
    signing_rate: float | None
    quality_visit_rate: float | None
    approval_rate: float | None
    repayment_conversion_rate: float | None
    target_progress: float | None
    team_cycle_target: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_name": self.group_name,
            "record_count": self.record_count,
            "repayment_amount_cumulative": self.repayment_amount_cumulative,
            "loan_amount_cumulative": self.loan_amount_cumulative,
            "invitation_cumulative": self.invitation_cumulative,
            "signing_count_cumulative": self.signing_count_cumulative,
            "quality_visit_count_cumulative": self.quality_visit_count_cumulative,
            "signing_rate": self.signing_rate,
            "quality_visit_rate": self.quality_visit_rate,
            "approval_rate": self.approval_rate,
            "repayment_conversion_rate": self.repayment_conversion_rate,
            "target_progress": self.target_progress,
            "team_cycle_target": self.team_cycle_target,
        }
