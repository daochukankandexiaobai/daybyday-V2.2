from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from app.config.field_groups import (
    ANALYSIS_METRIC_FIELD_KEYS,
    ENTRY_INPUT_FIELD_KEYS,
    EXCEL_RAW_RECORD_FIELD_KEYS,
    PREVIEW_CONVERSION_FIELD_KEYS,
    PREVIEW_CORE_PROGRESS_FIELD_KEYS,
    PREVIEW_PROCESS_BEHAVIOR_FIELD_KEYS,
    PREVIEW_SPECIAL_BUSINESS_FIELD_KEYS,
    QUERY_SUMMARY_FIELD_KEYS,
)


PROFILE_ENTRY_INPUT = "entry_input"
PROFILE_PREVIEW_TABLE = "preview_table"
PROFILE_QUERY_SUMMARY_TABLE = "query_summary_table"
PROFILE_EXCEL_RAW_RECORD = "excel_raw_record"
PROFILE_ANALYSIS_METRICS = "analysis_metrics"
PROFILE_PNG_SECTIONS = "png_sections"


@dataclass(frozen=True)
class FieldProfile:
    key: str
    label: str
    field_keys: Tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class PngSectionProfile:
    key: str
    index: int
    title: str
    file_suffix: str
    field_keys: Tuple[str, ...]


PREVIEW_TABLE_FIELD_KEYS: Tuple[str, ...] = (
    "record_date",
    "account_manager_name",
    "cycle_target",
    "repayment_amount_cumulative",
    "loan_amount_cumulative",
    "repayment_amount_daily",
    "target_progress",
    "loan_amount_daily",
    "intention_daily",
    "wechat_count_daily",
    "visit_count_daily",
    "invitation_cumulative",
    "invalid_visit_count_daily",
    "four_star_customer_count_daily",
    "five_star_customer_count_daily",
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
    "debt_case_submit_count_daily",
    "debt_case_repayment_count_daily",
    "debt_case_repayment_amount_daily",
    "large_order_repayment_count_daily",
    "large_order_repayment_amount_daily",
)

ENTRY_LEGACY_FIELD_KEYS: Tuple[str, ...] = ENTRY_INPUT_FIELD_KEYS


FIELD_PROFILES: Tuple[FieldProfile, ...] = (
    FieldProfile(
        key=PROFILE_ENTRY_INPUT,
        label="数据录入字段",
        field_keys=ENTRY_INPUT_FIELD_KEYS,
        description="当前数据录入页字段顺序，包含四星/五星客户数字段。",
    ),
    FieldProfile(
        key=PROFILE_PREVIEW_TABLE,
        label="今日展示表格",
        field_keys=PREVIEW_TABLE_FIELD_KEYS,
        description="当前今日展示字段顺序，过程行为包含四星/五星客户数字段。",
    ),
    FieldProfile(
        key=PROFILE_QUERY_SUMMARY_TABLE,
        label="查询汇总表格",
        field_keys=QUERY_SUMMARY_FIELD_KEYS,
        description="当前查询汇总一人一行表格字段顺序。",
    ),
    FieldProfile(
        key=PROFILE_EXCEL_RAW_RECORD,
        label="Excel 原始日报记录",
        field_keys=EXCEL_RAW_RECORD_FIELD_KEYS,
        description="Excel 原始日报记录导出字段，包含四星/五星客户数字段。",
    ),
    FieldProfile(
        key=PROFILE_ANALYSIS_METRICS,
        label="数据分析指标",
        field_keys=ANALYSIS_METRIC_FIELD_KEYS,
        description="可用于后续驱动 KPI、趋势、排行指标选择。",
    ),
)

FIELD_PROFILE_MAP: Dict[str, FieldProfile] = {profile.key: profile for profile in FIELD_PROFILES}

PNG_SECTION_PROFILES: Tuple[PngSectionProfile, ...] = (
    PngSectionProfile(
        key="core_progress",
        index=1,
        title="今日展示 - 核心进度",
        file_suffix="核心进度",
        field_keys=PREVIEW_CORE_PROGRESS_FIELD_KEYS,
    ),
    PngSectionProfile(
        key="process_behavior",
        index=2,
        title="今日展示 - 过程行为",
        file_suffix="过程行为",
        field_keys=PREVIEW_PROCESS_BEHAVIOR_FIELD_KEYS,
    ),
    PngSectionProfile(
        key="conversion",
        index=3,
        title="今日展示 - 签约与转化",
        file_suffix="签约转化",
        field_keys=PREVIEW_CONVERSION_FIELD_KEYS,
    ),
    PngSectionProfile(
        key="special_business",
        index=4,
        title="今日展示 - 债重与大单",
        file_suffix="债重大单",
        field_keys=PREVIEW_SPECIAL_BUSINESS_FIELD_KEYS,
    ),
)


def get_field_profile(profile_key: str) -> FieldProfile:
    return FIELD_PROFILE_MAP[profile_key]


def get_profile_field_keys(profile_key: str) -> Tuple[str, ...]:
    return get_field_profile(profile_key).field_keys
