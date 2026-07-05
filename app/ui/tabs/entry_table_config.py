from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config.field_profiles import PROFILE_ENTRY_INPUT, get_profile_field_keys
from app.config.field_registry import DATA_TYPE_AMOUNT, DATA_TYPE_INT, get_field_spec


ENTRY_PAGE_KEYS = ("entry", "data_entry")
ENTRY_AMOUNT_DATA_TYPES = {DATA_TYPE_AMOUNT, "money", "decimal", "percent"}
ENTRY_INT_DATA_TYPES = {DATA_TYPE_INT, "int"}


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
    required: bool = False
    storage_type: str = ""
    storage_column: str = ""


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


def _stable_entry_field_keys(source_keys: Iterable[str]) -> List[str]:
    source = list(source_keys)
    moving = [key for key in _REORDERED_ENTRY_FIELD_KEYS if key in source]
    result = [key for key in source if key not in moving]
    if not moving:
        return result
    try:
        insert_at = result.index(_ENTRY_ORDER_AFTER_FIELD) + 1
    except ValueError:
        insert_at = len(result)
    return result[:insert_at] + moving + result[insert_at:]


def _default_for_data_type(data_type: str, value: Any) -> Any:
    if value is None or str(value).strip() == "":
        if data_type in ENTRY_INT_DATA_TYPES:
            return 0
        if data_type in ENTRY_AMOUNT_DATA_TYPES:
            return 0.0
        return ""
    if data_type in ENTRY_INT_DATA_TYPES:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if data_type in ENTRY_AMOUNT_DATA_TYPES:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return str(value)


def _entry_column_config_from_dict(row: Dict[str, Any]) -> EntryColumnConfig:
    field_key = str(row.get("field_key", "")).strip()
    data_type = str(row.get("data_type", "text") or "text")
    raw_label = str(row.get("label", field_key) or field_key)
    label = _LABEL_OVERRIDES.get(field_key, _compact_entry_label(raw_label))
    min_width, preferred_width = _WIDTH_OVERRIDES.get(field_key, (96, 112))
    return EntryColumnConfig(
        field_key=field_key,
        field_name=label,
        display_name=_DISPLAY_OVERRIDES.get(field_key, label),
        min_width=min_width,
        preferred_width=preferred_width,
        editable=bool(int(row.get("editable", 1) or 0)),
        primary_entry=field_key in _PRIMARY_FIELD_KEYS,
        data_type=data_type,
        default=_default_for_data_type(data_type, row.get("default_value")),
        required=bool(int(row.get("required", 0) or 0)),
        storage_type=str(row.get("storage_type", "") or ""),
        storage_column=str(row.get("storage_column", "") or ""),
    )


def _entry_column_config_from_registry(field_key: str) -> EntryColumnConfig:
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
        required=bool(spec.required),
        storage_type=spec.storage_type,
        storage_column=spec.storage_column,
    )


def build_entry_columns_from_config(field_definitions: Optional[Iterable[Dict[str, Any]]] = None) -> List[EntryColumnConfig]:
    configs: List[EntryColumnConfig] = [
        EntryColumnConfig(
            field_key="account_manager_name",
            field_name="客户经理姓名",
            display_name="客户经理姓名",
            min_width=132,
            preferred_width=156,
            editable=False,
            primary_entry=False,
            data_type="text",
            default="",
        )
    ]

    if field_definitions is None:
        source_keys = _stable_entry_field_keys(get_profile_field_keys(PROFILE_ENTRY_INPUT))
        configs.extend(_entry_column_config_from_registry(key) for key in source_keys if key != "account_manager_name")
        return configs

    rows_by_key: Dict[str, Dict[str, Any]] = {}
    ordered_keys: List[str] = []
    for row in field_definitions:
        field_key = str(row.get("field_key", "")).strip()
        if not field_key or field_key == "account_manager_name":
            continue
        if str(row.get("category", "") or "") != "raw_daily":
            continue
        if int(row.get("enabled", 1) or 0) != 1:
            continue
        if int(row.get("editable", 0) or 0) != 1:
            continue
        if field_key not in rows_by_key:
            ordered_keys.append(field_key)
        rows_by_key[field_key] = dict(row)

    for field_key in _stable_entry_field_keys(ordered_keys):
        configs.append(_entry_column_config_from_dict(rows_by_key[field_key]))
    return configs


def build_entry_table_metadata(configs: Iterable[EntryColumnConfig]) -> Dict[str, Any]:
    column_configs = list(configs)
    field_keys = [cfg.field_key for cfg in column_configs]
    editable_columns = [idx for idx, cfg in enumerate(column_configs) if cfg.editable]
    int_columns = [
        idx for idx, cfg in enumerate(column_configs)
        if cfg.data_type in ENTRY_INT_DATA_TYPES and cfg.editable
    ]
    amount_columns = [
        idx for idx, cfg in enumerate(column_configs)
        if cfg.data_type in ENTRY_AMOUNT_DATA_TYPES and cfg.editable
    ]
    summary_columns = [
        idx
        for idx, cfg in enumerate(column_configs)
        if cfg.data_type in ENTRY_INT_DATA_TYPES | ENTRY_AMOUNT_DATA_TYPES and cfg.editable
    ]
    return {
        "column_configs": column_configs,
        "field_keys": field_keys,
        "headers": [cfg.field_name for cfg in column_configs],
        "display_headers": [cfg.display_name for cfg in column_configs],
        "editable_columns": editable_columns,
        "primary_columns": [
            idx for idx, cfg in enumerate(column_configs) if cfg.editable and cfg.primary_entry
        ],
        "int_columns": int_columns,
        "amount_columns": amount_columns,
        "summary_columns": summary_columns,
        "field_key_by_column": {idx: cfg.field_key for idx, cfg in enumerate(column_configs)},
        "column_by_field_key": {cfg.field_key: idx for idx, cfg in enumerate(column_configs)},
    }


ENTRY_COLUMN_CONFIGS = build_entry_columns_from_config()
_ENTRY_METADATA = build_entry_table_metadata(ENTRY_COLUMN_CONFIGS)

ENTRY_FIELD_KEYS = _ENTRY_METADATA["field_keys"]
ENTRY_HEADERS = _ENTRY_METADATA["headers"]
ENTRY_DISPLAY_HEADERS = _ENTRY_METADATA["display_headers"]
ENTRY_EDITABLE_COLUMNS = _ENTRY_METADATA["editable_columns"]
ENTRY_PRIMARY_COLUMNS = _ENTRY_METADATA["primary_columns"]
ENTRY_INT_COLUMNS = _ENTRY_METADATA["int_columns"]
ENTRY_AMOUNT_COLUMNS = _ENTRY_METADATA["amount_columns"]
ENTRY_SUMMARY_COLUMNS = _ENTRY_METADATA["summary_columns"]
ENTRY_FIELD_KEY_BY_COLUMN = _ENTRY_METADATA["field_key_by_column"]
ENTRY_COLUMN_BY_FIELD_KEY = _ENTRY_METADATA["column_by_field_key"]
