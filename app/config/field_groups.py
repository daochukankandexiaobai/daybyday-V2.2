from __future__ import annotations

from dataclasses import dataclass

from app.config.field_registry import (
    GROUP_CONTEXT,
    GROUP_CONVERSION,
    GROUP_CORE_PROGRESS,
    GROUP_DERIVED,
    GROUP_PROCESS_BEHAVIOR,
    GROUP_REMARK,
    GROUP_SPECIAL_BUSINESS,
)


GROUP_ENTRY_INPUT = "entry_input"
GROUP_PREVIEW_CORE_PROGRESS = "preview_core_progress"
GROUP_PREVIEW_PROCESS_BEHAVIOR = "preview_process_behavior"
GROUP_PREVIEW_CONVERSION = "preview_conversion"
GROUP_PREVIEW_SPECIAL_BUSINESS = "preview_special_business"
GROUP_QUERY_SUMMARY = "query_summary"
GROUP_EXCEL_RAW_RECORD = "excel_raw_record"
GROUP_ANALYSIS_METRICS = "analysis_metrics"
GROUP_PNG_CORE_PROGRESS = "png_core_progress"
GROUP_PNG_PROCESS_BEHAVIOR = "png_process_behavior"
GROUP_PNG_CONVERSION = "png_conversion"
GROUP_PNG_SPECIAL_BUSINESS = "png_special_business"


@dataclass(frozen=True)
class FieldGroup:
    key: str
    label: str
    field_keys: tuple[str, ...]
    description: str = ""


ENTRY_INPUT_FIELD_KEYS: tuple[str, ...] = (
    "account_manager_name",
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
    "remark",
)

PREVIEW_CORE_PROGRESS_FIELD_KEYS: tuple[str, ...] = (
    "record_date",
    "account_manager_name",
    "cycle_target",
    "repayment_amount_cumulative",
    "loan_amount_cumulative",
    "repayment_amount_daily",
    "target_progress",
    "loan_amount_daily",
)

PREVIEW_PROCESS_BEHAVIOR_FIELD_KEYS: tuple[str, ...] = (
    "record_date",
    "account_manager_name",
    "intention_daily",
    "wechat_count_daily",
    "visit_count_daily",
    "invitation_cumulative",
    "invalid_visit_count_daily",
    "four_star_customer_count_daily",
    "five_star_customer_count_daily",
)

PREVIEW_CONVERSION_FIELD_KEYS: tuple[str, ...] = (
    "record_date",
    "account_manager_name",
    "signing_count_daily",
    "signing_count_cumulative",
    "daily_signing_rate",
    "quality_visit_count_daily",
    "daily_quality_visit_rate",
    "quality_visit_count_cumulative",
    "approval_customer_count_daily",
    "daily_approval_rate",
    "repayment_customer_count_daily",
    "daily_sales_conversion_rate",
    "warrant_conversion_rate",
)

PREVIEW_SPECIAL_BUSINESS_FIELD_KEYS: tuple[str, ...] = (
    "record_date",
    "account_manager_name",
    "debt_case_submit_count_daily",
    "debt_case_repayment_count_daily",
    "debt_case_repayment_amount_daily",
    "large_order_repayment_count_daily",
    "large_order_repayment_amount_daily",
)

QUERY_SUMMARY_FIELD_KEYS: tuple[str, ...] = (
    "query_range",
    "account_manager_name",
    "cycle_target",
    "repayment_amount_cumulative",
    "loan_amount_cumulative",
    "repayment_amount",
    "target_progress",
    "loan_amount",
    "intention",
    "wechat_count",
    "visit_count",
    "invitation_cumulative",
    "invalid_visit_count",
    "four_star_customer_count",
    "five_star_customer_count",
    "signing_count",
    "signing_count_cumulative",
    "signing_rate",
    "quality_visit_count",
    "quality_visit_rate",
    "quality_visit_count_cumulative",
    "approval_customer_count",
    "approval_rate",
    "repayment_customer_count",
    "sales_conversion_rate",
    "warrant_conversion_rate",
    "debt_case_submit_count",
    "debt_case_repayment_count",
    "debt_case_repayment_amount",
    "large_order_repayment_count",
    "large_order_repayment_amount",
)

EXCEL_RAW_RECORD_FIELD_KEYS: tuple[str, ...] = (
    "record_id",
    "record_date",
    "region",
    "team_name_snapshot",
    "team_manager_name_snapshot",
    "account_manager_name_snapshot",
    "settlement_cycle_code",
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
    "remark",
    "version",
    "template_version",
    "updated_at",
    "source_type",
)

ANALYSIS_METRIC_FIELD_KEYS: tuple[str, ...] = (
    "repayment_amount_daily",
    "loan_amount_daily",
    "visit_count_daily",
    "signing_count_daily",
    "repayment_customer_count_daily",
    "four_star_customer_count_daily",
    "five_star_customer_count_daily",
    "repayment_amount",
    "loan_amount",
    "visit_count",
    "signing_count",
    "quality_visit_count",
    "repayment_customer_count",
    "signing_rate",
    "quality_visit_rate",
    "sales_conversion_rate",
    "warrant_conversion_rate",
    "target_progress",
)


FIELD_GROUPS: tuple[FieldGroup, ...] = (
    FieldGroup(GROUP_CONTEXT, "上下文字段", ("record_date", "region", "team_name_snapshot", "team_manager_name_snapshot", "account_manager_name_snapshot")),
    FieldGroup(GROUP_CORE_PROGRESS, "核心进度", ("repayment_amount_daily", "loan_amount_daily")),
    FieldGroup(
        GROUP_PROCESS_BEHAVIOR,
        "过程行为",
        (
            "intention_daily",
            "wechat_count_daily",
            "visit_count_daily",
            "invalid_visit_count_daily",
            "quality_visit_count_daily",
            "four_star_customer_count_daily",
            "five_star_customer_count_daily",
        ),
    ),
    FieldGroup(
        GROUP_CONVERSION,
        "签约与转化",
        ("signing_count_daily", "approval_customer_count_daily", "repayment_customer_count_daily"),
    ),
    FieldGroup(
        GROUP_SPECIAL_BUSINESS,
        "债重与大单",
        (
            "debt_case_submit_count_daily",
            "debt_case_repayment_count_daily",
            "debt_case_repayment_amount_daily",
            "large_order_repayment_count_daily",
            "large_order_repayment_amount_daily",
        ),
    ),
    FieldGroup(GROUP_REMARK, "备注", ("remark",)),
    FieldGroup(GROUP_DERIVED, "派生指标", ("target_progress", "signing_rate", "quality_visit_rate", "approval_rate")),
    FieldGroup(GROUP_ENTRY_INPUT, "数据录入字段", ENTRY_INPUT_FIELD_KEYS),
    FieldGroup(GROUP_PREVIEW_CORE_PROGRESS, "今日展示 - 核心进度", PREVIEW_CORE_PROGRESS_FIELD_KEYS),
    FieldGroup(GROUP_PREVIEW_PROCESS_BEHAVIOR, "今日展示 - 过程行为", PREVIEW_PROCESS_BEHAVIOR_FIELD_KEYS),
    FieldGroup(GROUP_PREVIEW_CONVERSION, "今日展示 - 签约与转化", PREVIEW_CONVERSION_FIELD_KEYS),
    FieldGroup(GROUP_PREVIEW_SPECIAL_BUSINESS, "今日展示 - 债重与大单", PREVIEW_SPECIAL_BUSINESS_FIELD_KEYS),
    FieldGroup(GROUP_QUERY_SUMMARY, "查询汇总字段", QUERY_SUMMARY_FIELD_KEYS),
    FieldGroup(GROUP_EXCEL_RAW_RECORD, "Excel 原始日报记录", EXCEL_RAW_RECORD_FIELD_KEYS),
    FieldGroup(GROUP_ANALYSIS_METRICS, "数据分析可选指标", ANALYSIS_METRIC_FIELD_KEYS),
    FieldGroup(GROUP_PNG_CORE_PROGRESS, "PNG 分图 - 核心进度", PREVIEW_CORE_PROGRESS_FIELD_KEYS),
    FieldGroup(GROUP_PNG_PROCESS_BEHAVIOR, "PNG 分图 - 过程行为", PREVIEW_PROCESS_BEHAVIOR_FIELD_KEYS),
    FieldGroup(GROUP_PNG_CONVERSION, "PNG 分图 - 签约与转化", PREVIEW_CONVERSION_FIELD_KEYS),
    FieldGroup(GROUP_PNG_SPECIAL_BUSINESS, "PNG 分图 - 债重与大单", PREVIEW_SPECIAL_BUSINESS_FIELD_KEYS),
)

FIELD_GROUP_MAP: dict[str, FieldGroup] = {group.key: group for group in FIELD_GROUPS}


def get_field_group(group_key: str) -> FieldGroup:
    return FIELD_GROUP_MAP[group_key]


def get_group_field_keys(group_key: str) -> tuple[str, ...]:
    return get_field_group(group_key).field_keys
