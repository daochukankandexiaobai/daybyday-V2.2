from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DATA_TYPE_TEXT = "text"
DATA_TYPE_TEXTAREA = "textarea"
DATA_TYPE_DATE = "date"
DATA_TYPE_INT = "int"
DATA_TYPE_AMOUNT = "amount"
DATA_TYPE_PERCENT = "percent"

FORMAT_TEXT = "text"
FORMAT_DATE = "date"
FORMAT_INT = "int"
FORMAT_AMOUNT = "amount"
FORMAT_PERCENT = "percent"

AGGREGATION_NONE = "none"
AGGREGATION_SUM = "sum"
AGGREGATION_LATEST = "latest"
AGGREGATION_DERIVED = "derived"

GROUP_SYSTEM = "system"
GROUP_CONTEXT = "context"
GROUP_CORE_PROGRESS = "core_progress"
GROUP_PROCESS_BEHAVIOR = "process_behavior"
GROUP_CONVERSION = "conversion"
GROUP_SPECIAL_BUSINESS = "special_business"
GROUP_REMARK = "remark"
GROUP_DERIVED = "derived"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    data_type: str
    default: Any = ""
    editable: bool = False
    aggregatable: bool = False
    analyzable: bool = False
    group: str = GROUP_CONTEXT
    format_type: str = FORMAT_TEXT
    aggregation: str = AGGREGATION_NONE
    db_column: str = ""
    db_ddl: str = ""
    template_field: bool = False
    template_key: str = ""
    template_required: bool = False
    template_order: int = 0
    json_export: bool = False
    excel_export: bool = False
    png_export: bool = False
    include_in_hash: bool = False
    chart_supported: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    is_raw_daily_metric: bool = False
    is_future_field: bool = False
    note: str = ""

    @property
    def resolved_template_key(self) -> str:
        return self.template_key or self.key


def _field(
    key: str,
    label: str,
    data_type: str,
    *,
    default: Any = "",
    editable: bool = False,
    aggregatable: bool = False,
    analyzable: bool = False,
    group: str = GROUP_CONTEXT,
    format_type: str | None = None,
    aggregation: str = AGGREGATION_NONE,
    db_ddl: str = "",
    template_field: bool = False,
    template_key: str = "",
    template_required: bool = False,
    template_order: int = 0,
    json_export: bool = False,
    excel_export: bool = False,
    png_export: bool = False,
    include_in_hash: bool = False,
    chart_supported: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    is_raw_daily_metric: bool = False,
    is_future_field: bool = False,
    note: str = "",
) -> FieldSpec:
    if format_type is None:
        format_type = {
            DATA_TYPE_INT: FORMAT_INT,
            DATA_TYPE_AMOUNT: FORMAT_AMOUNT,
            DATA_TYPE_PERCENT: FORMAT_PERCENT,
            DATA_TYPE_DATE: FORMAT_DATE,
        }.get(data_type, FORMAT_TEXT)

    return FieldSpec(
        key=key,
        label=label,
        data_type=data_type,
        default=default,
        editable=editable,
        aggregatable=aggregatable,
        analyzable=analyzable,
        group=group,
        format_type=format_type,
        aggregation=aggregation,
        db_column=key,
        db_ddl=db_ddl,
        template_field=template_field,
        template_key=template_key,
        template_required=template_required,
        template_order=template_order,
        json_export=json_export,
        excel_export=excel_export,
        png_export=png_export,
        include_in_hash=include_in_hash,
        chart_supported=chart_supported,
        aliases=aliases,
        is_raw_daily_metric=is_raw_daily_metric,
        is_future_field=is_future_field,
        note=note,
    )


CONTEXT_FIELD_SPECS: tuple[FieldSpec, ...] = (
    _field("record_id", "记录ID", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True, excel_export=True),
    _field(
        "record_date",
        "日期",
        DATA_TYPE_DATE,
        group=GROUP_CONTEXT,
        db_ddl="TEXT",
        template_field=True,
        template_required=True,
        template_order=1,
        json_export=True,
        excel_export=True,
        include_in_hash=True,
    ),
    _field(
        "region",
        "区域",
        DATA_TYPE_TEXT,
        group=GROUP_CONTEXT,
        db_ddl="TEXT",
        template_field=True,
        template_required=True,
        template_order=2,
        json_export=True,
        excel_export=True,
    ),
    _field("team_id", "团队ID", DATA_TYPE_INT, default=0, group=GROUP_CONTEXT, json_export=True, excel_export=True),
    _field(
        "team_name_snapshot",
        "团队",
        DATA_TYPE_TEXT,
        group=GROUP_CONTEXT,
        db_ddl="TEXT DEFAULT ''",
        template_field=True,
        template_key="team_name",
        template_required=True,
        template_order=3,
        json_export=True,
        excel_export=True,
        include_in_hash=True,
        aliases=("team_name", "team"),
    ),
    _field(
        "team_manager_name_snapshot",
        "团队经理姓名",
        DATA_TYPE_TEXT,
        group=GROUP_CONTEXT,
        db_ddl="TEXT DEFAULT ''",
        template_field=True,
        template_key="team_manager_name",
        template_required=True,
        template_order=4,
        json_export=True,
        excel_export=True,
        include_in_hash=True,
        aliases=("team_manager_name", "manager"),
    ),
    _field(
        "account_manager_id",
        "客户经理ID",
        DATA_TYPE_INT,
        default=0,
        group=GROUP_CONTEXT,
        json_export=True,
        excel_export=True,
    ),
    _field(
        "account_manager_name_snapshot",
        "客户经理姓名",
        DATA_TYPE_TEXT,
        group=GROUP_CONTEXT,
        db_ddl="TEXT DEFAULT ''",
        template_field=True,
        template_key="account_manager_name",
        template_required=True,
        template_order=5,
        json_export=True,
        excel_export=True,
        include_in_hash=True,
        aliases=("account_manager_name", "manager_name"),
    ),
    _field(
        "settlement_cycle_code",
        "结算周期",
        DATA_TYPE_TEXT,
        group=GROUP_CONTEXT,
        db_ddl="TEXT DEFAULT ''",
        json_export=True,
        excel_export=True,
    ),
)


DAILY_METRIC_FIELD_SPECS: tuple[FieldSpec, ...] = (
    _field(
        "repayment_amount_daily",
        "当日回款金额",
        DATA_TYPE_AMOUNT,
        default=0.0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_CORE_PROGRESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="REAL DEFAULT 0",
        template_field=True,
        template_order=6,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        aliases=("repayment_amount",),
    ),
    _field(
        "loan_amount_daily",
        "当日放款金额",
        DATA_TYPE_AMOUNT,
        default=0.0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_CORE_PROGRESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="REAL DEFAULT 0",
        template_field=True,
        template_order=7,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        aliases=("loan_amount",),
    ),
    _field(
        "intention_daily",
        "当日意向",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=8,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
        aliases=("new_customers", "intentions"),
    ),
    _field(
        "wechat_count_daily",
        "当日微信量",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=9,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
        aliases=("appointments", "wechat_count"),
    ),
    _field(
        "visit_count_daily",
        "当日上门量",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=10,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        aliases=("visits",),
    ),
    _field(
        "invalid_visit_count_daily",
        "当日无效上门",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=11,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
        aliases=("invalid_visits",),
    ),
    _field(
        "signing_count_daily",
        "当日签约量",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_CONVERSION,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=12,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        aliases=("signings",),
    ),
    _field(
        "quality_visit_count_daily",
        "当日优质上门",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=13,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
        aliases=("quality_visits",),
    ),
    _field(
        "approval_customer_count_daily",
        "当日批复客户数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_CONVERSION,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=14,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
        aliases=("approval_count", "approvals"),
    ),
    _field(
        "repayment_customer_count_daily",
        "当日回款客户数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_CONVERSION,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=15,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        aliases=("repayments", "repayment_customers"),
    ),
    _field(
        "debt_case_submit_count_daily",
        "当日债重进件数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_SPECIAL_BUSINESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=16,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
    ),
    _field(
        "debt_case_repayment_count_daily",
        "当日债重回款件数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_SPECIAL_BUSINESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=17,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
    ),
    _field(
        "debt_case_repayment_amount_daily",
        "当日债重回款金额",
        DATA_TYPE_AMOUNT,
        default=0.0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_SPECIAL_BUSINESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="REAL DEFAULT 0",
        template_field=True,
        template_order=18,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
    ),
    _field(
        "large_order_repayment_count_daily",
        "当日大单回款笔数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_SPECIAL_BUSINESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=19,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
    ),
    _field(
        "large_order_repayment_amount_daily",
        "当日大单回款金额",
        DATA_TYPE_AMOUNT,
        default=0.0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_SPECIAL_BUSINESS,
        aggregation=AGGREGATION_SUM,
        db_ddl="REAL DEFAULT 0",
        template_field=True,
        template_order=20,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        is_raw_daily_metric=True,
    ),
    _field(
        "four_star_customer_count_daily",
        "当日四星客户数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=21,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        is_future_field=False,
        note="第 2 批接入数据库迁移、日报录入、保存、校验和 hash 链路。",
    ),
    _field(
        "five_star_customer_count_daily",
        "当日五星客户数",
        DATA_TYPE_INT,
        default=0,
        editable=True,
        aggregatable=True,
        analyzable=True,
        group=GROUP_PROCESS_BEHAVIOR,
        aggregation=AGGREGATION_SUM,
        db_ddl="INTEGER DEFAULT 0",
        template_field=True,
        template_order=22,
        json_export=True,
        excel_export=True,
        png_export=True,
        include_in_hash=True,
        chart_supported=("trend",),
        is_raw_daily_metric=True,
        is_future_field=False,
        note="第 2 批接入数据库迁移、日报录入、保存、校验和 hash 链路。",
    ),
)


REMARK_FIELD_SPECS: tuple[FieldSpec, ...] = (
    _field(
        "remark",
        "备注",
        DATA_TYPE_TEXTAREA,
        default="",
        editable=True,
        group=GROUP_REMARK,
        db_ddl="TEXT",
        template_field=True,
        template_order=23,
        json_export=True,
        excel_export=True,
        include_in_hash=True,
    ),
)


SYSTEM_FIELD_SPECS: tuple[FieldSpec, ...] = (
    _field("version", "版本", DATA_TYPE_INT, default=1, group=GROUP_SYSTEM, json_export=True, excel_export=True),
    _field("created_at", "创建时间", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True),
    _field("updated_at", "更新时间", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True, excel_export=True),
    _field("template_version", "模板版本", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True, excel_export=True),
    _field("record_hash", "记录哈希", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True),
    _field("source_type", "来源", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True, excel_export=True),
    _field("source_file", "来源文件", DATA_TYPE_TEXT, group=GROUP_SYSTEM, json_export=True),
)


DISPLAY_FIELD_SPECS: tuple[FieldSpec, ...] = (
    _field("query_range", "查询区间", DATA_TYPE_TEXT, group=GROUP_DERIVED, format_type=FORMAT_TEXT, aggregation=AGGREGATION_NONE),
    _field("team_name", "团队", DATA_TYPE_TEXT, group=GROUP_CONTEXT, format_type=FORMAT_TEXT, aggregation=AGGREGATION_NONE),
    _field("account_manager_name", "客户经理", DATA_TYPE_TEXT, group=GROUP_CONTEXT, format_type=FORMAT_TEXT, aggregation=AGGREGATION_NONE),
    _field("cycle_target", "结算周期目标", DATA_TYPE_AMOUNT, default=0.0, group=GROUP_DERIVED, aggregation=AGGREGATION_LATEST),
    _field("team_cycle_target", "结算周期目标", DATA_TYPE_AMOUNT, default=0.0, group=GROUP_DERIVED, aggregation=AGGREGATION_LATEST),
    _field(
        "repayment_amount_cumulative",
        "累计回款金额",
        DATA_TYPE_AMOUNT,
        default=0.0,
        group=GROUP_DERIVED,
        aggregatable=True,
        analyzable=True,
        aggregation=AGGREGATION_DERIVED,
        png_export=True,
    ),
    _field(
        "loan_amount_cumulative",
        "累计放款金额",
        DATA_TYPE_AMOUNT,
        default=0.0,
        group=GROUP_DERIVED,
        aggregatable=True,
        analyzable=True,
        aggregation=AGGREGATION_DERIVED,
        png_export=True,
    ),
    _field("repayment_amount", "回款金额", DATA_TYPE_AMOUNT, default=0.0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("loan_amount", "放款金额", DATA_TYPE_AMOUNT, default=0.0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("intention", "意向", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("wechat_count", "微信量", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("visit_count", "上门量", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("invitation_cumulative", "累计邀约", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("invalid_visit_count", "无效上门", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("four_star_customer_count", "四星客户数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("five_star_customer_count", "五星客户数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("signing_count", "签约量", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("signing_count_cumulative", "累计签约量", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("quality_visit_count", "优质上门量", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field(
        "quality_visit_count_cumulative",
        "累计优质上门量",
        DATA_TYPE_INT,
        default=0,
        group=GROUP_DERIVED,
        aggregation=AGGREGATION_DERIVED,
    ),
    _field("approval_customer_count", "批复客户数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("repayment_customer_count", "回款客户数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("debt_case_submit_count", "债重进件数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("debt_case_repayment_count", "债重回款件数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("debt_case_repayment_amount", "债重回款金额", DATA_TYPE_AMOUNT, default=0.0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("large_order_repayment_count", "大单回款笔数", DATA_TYPE_INT, default=0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("large_order_repayment_amount", "大单回款金额", DATA_TYPE_AMOUNT, default=0.0, group=GROUP_DERIVED, aggregation=AGGREGATION_SUM),
    _field("target_progress", "目标完成进度", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED, analyzable=True),
    _field("daily_signing_rate", "当日签约率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("daily_quality_visit_rate", "当日优质上门率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("daily_approval_rate", "当日批复率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("daily_sales_conversion_rate", "当日销售转化率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("signing_rate", "签约率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED, analyzable=True),
    _field("quality_visit_rate", "优质上门率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED, analyzable=True),
    _field("approval_rate", "批复率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED, analyzable=True),
    _field("repayment_conversion_rate", "回款转化率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED),
    _field("sales_conversion_rate", "销售转化率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED, analyzable=True),
    _field("warrant_conversion_rate", "权证转化率", DATA_TYPE_PERCENT, group=GROUP_DERIVED, aggregation=AGGREGATION_DERIVED, analyzable=True),
)


FIELD_SPECS: tuple[FieldSpec, ...] = (
    CONTEXT_FIELD_SPECS
    + DAILY_METRIC_FIELD_SPECS
    + REMARK_FIELD_SPECS
    + SYSTEM_FIELD_SPECS
    + DISPLAY_FIELD_SPECS
)

FIELD_REGISTRY: dict[str, FieldSpec] = {spec.key: spec for spec in FIELD_SPECS}


def get_field_spec(key: str) -> FieldSpec:
    return FIELD_REGISTRY[key]


def has_field(key: str) -> bool:
    return key in FIELD_REGISTRY


def iter_field_specs(*, include_future: bool = True, include_display: bool = True) -> tuple[FieldSpec, ...]:
    result = []
    display_keys = {spec.key for spec in DISPLAY_FIELD_SPECS}
    for spec in FIELD_SPECS:
        if spec.is_future_field and not include_future:
            continue
        if spec.key in display_keys and not include_display:
            continue
        result.append(spec)
    return tuple(result)


def daily_metric_field_specs(*, include_future: bool = True) -> tuple[FieldSpec, ...]:
    return tuple(
        spec
        for spec in DAILY_METRIC_FIELD_SPECS
        if include_future or not spec.is_future_field
    )


def daily_int_field_keys(*, include_future: bool = True) -> tuple[str, ...]:
    return tuple(
        spec.key
        for spec in daily_metric_field_specs(include_future=include_future)
        if spec.data_type == DATA_TYPE_INT
    )


def daily_amount_field_keys(*, include_future: bool = True) -> tuple[str, ...]:
    return tuple(
        spec.key
        for spec in daily_metric_field_specs(include_future=include_future)
        if spec.data_type == DATA_TYPE_AMOUNT
    )


def daily_metric_field_keys(*, include_future: bool = True) -> tuple[str, ...]:
    return tuple(spec.key for spec in daily_metric_field_specs(include_future=include_future))


def template_field_specs(*, include_future: bool = True) -> tuple[FieldSpec, ...]:
    specs = [
        spec
        for spec in CONTEXT_FIELD_SPECS + DAILY_METRIC_FIELD_SPECS + REMARK_FIELD_SPECS
        if spec.template_field and (include_future or not spec.is_future_field)
    ]
    return tuple(sorted(specs, key=lambda item: item.template_order))


def export_field_keys(target: str, *, include_future: bool = True) -> tuple[str, ...]:
    attr_map = {
        "json": "json_export",
        "excel": "excel_export",
        "png": "png_export",
    }
    attr = attr_map.get(target)
    if attr is None:
        raise ValueError(f"未知导出目标: {target}")
    return tuple(
        spec.key
        for spec in iter_field_specs(include_future=include_future)
        if bool(getattr(spec, attr))
    )
