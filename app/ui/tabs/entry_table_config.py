from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config.field_profiles import PROFILE_ENTRY_INPUT, get_profile_field_keys
from app.config.field_registry import DATA_TYPE_AMOUNT, DATA_TYPE_INT, get_field_spec


@dataclass(frozen=True)
class EntryColumnConfig:
    field_key: str
    field_name: str
    display_name: str
    min_width: int
    preferred_width: int
    editable: bool = True
    primary_entry: bool = False
    data_type: str = "text"
    default: Any = ""


_LABEL_OVERRIDES = {
    "account_manager_name": "客户经理姓名",
}

_DISPLAY_OVERRIDES = {
    "debt_case_submit_count_daily": "债重\n进件数",
    "debt_case_repayment_count_daily": "债重\n回款件数",
    "debt_case_repayment_amount_daily": "债重\n回款金额",
    "large_order_repayment_count_daily": "大单\n回款笔数",
    "large_order_repayment_amount_daily": "大单\n回款金额",
    "four_star_customer_count_daily": "四星\n客户数",
    "five_star_customer_count_daily": "五星\n客户数",
}

_WIDTH_OVERRIDES = {
    "account_manager_name": (132, 156),
    "repayment_amount_daily": (96, 112),
    "loan_amount_daily": (96, 112),
    "intention_daily": (72, 84),
    "wechat_count_daily": (72, 84),
    "visit_count_daily": (72, 84),
    "invalid_visit_count_daily": (84, 96),
    "signing_count_daily": (72, 84),
    "quality_visit_count_daily": (84, 96),
    "approval_customer_count_daily": (92, 106),
    "repayment_customer_count_daily": (92, 106),
    "debt_case_submit_count_daily": (108, 122),
    "debt_case_repayment_count_daily": (116, 132),
    "debt_case_repayment_amount_daily": (126, 146),
    "large_order_repayment_count_daily": (116, 132),
    "large_order_repayment_amount_daily": (126, 146),
    "four_star_customer_count_daily": (88, 100),
    "five_star_customer_count_daily": (88, 100),
    "remark": (144, 196),
}

_ENTRY_ORDER_AFTER_FIELD = "repayment_customer_count_daily"
_REORDERED_ENTRY_FIELD_KEYS = (
    "four_star_customer_count_daily",
    "five_star_customer_count_daily",
)

_PRIMARY_FIELD_KEYS = {
    "repayment_amount_daily",
    "loan_amount_daily",
    "intention_daily",
    "visit_count_daily",
    "signing_count_daily",
    "approval_customer_count_daily",
    "repayment_customer_count_daily",
}


def _compact_entry_label(label: str) -> str:
    if label.startswith("当日"):
        return label[2:]
    return label


def _entry_field_keys() -> list[str]:
    source = list(get_profile_field_keys(PROFILE_ENTRY_INPUT))
    moving = [key for key in _REORDERED_ENTRY_FIELD_KEYS if key in source]
    result = [key for key in source if key not in moving]
    if not moving:
        return result
    try:
        insert_at = result.index(_ENTRY_ORDER_AFTER_FIELD) + 1
    except ValueError:
        insert_at = len(result)
    return result[:insert_at] + moving + result[insert_at:]


def _entry_column_config(field_key: str) -> EntryColumnConfig:
    spec = get_field_spec(field_key)
    label = _LABEL_OVERRIDES.get(field_key, _compact_entry_label(spec.label))
    min_width, preferred_width = _WIDTH_OVERRIDES.get(field_key, (96, 112))
    return EntryColumnConfig(
        field_key=field_key,
        field_name=label,
        display_name=_DISPLAY_OVERRIDES.get(field_key, label),
        min_width=min_width,
        preferred_width=preferred_width,
        editable=bool(spec.editable),
        primary_entry=field_key in _PRIMARY_FIELD_KEYS,
        data_type=spec.data_type,
        default=spec.default,
    )


ENTRY_FIELD_KEYS = _entry_field_keys()
ENTRY_COLUMN_CONFIGS: list[EntryColumnConfig] = [_entry_column_config(key) for key in ENTRY_FIELD_KEYS]

ENTRY_HEADERS = [cfg.field_name for cfg in ENTRY_COLUMN_CONFIGS]
ENTRY_DISPLAY_HEADERS = [cfg.display_name for cfg in ENTRY_COLUMN_CONFIGS]
ENTRY_EDITABLE_COLUMNS = [idx for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS) if cfg.editable]
ENTRY_PRIMARY_COLUMNS = [idx for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS) if cfg.editable and cfg.primary_entry]
ENTRY_INT_COLUMNS = [idx for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS) if cfg.data_type == DATA_TYPE_INT and cfg.editable]
ENTRY_AMOUNT_COLUMNS = [idx for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS) if cfg.data_type == DATA_TYPE_AMOUNT and cfg.editable]
ENTRY_SUMMARY_COLUMNS = [
    idx
    for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS)
    if cfg.data_type in {DATA_TYPE_INT, DATA_TYPE_AMOUNT} and cfg.editable
]
ENTRY_FIELD_KEY_BY_COLUMN = {idx: cfg.field_key for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS)}
ENTRY_COLUMN_BY_FIELD_KEY = {cfg.field_key: idx for idx, cfg in enumerate(ENTRY_COLUMN_CONFIGS)}
