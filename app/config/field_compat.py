from __future__ import annotations

from typing import Dict, List, Set, Tuple

from app.config.field_profiles import ENTRY_LEGACY_FIELD_KEYS
from app.config.field_registry import (
    DATA_TYPE_AMOUNT,
    DATA_TYPE_DATE,
    DATA_TYPE_INT,
    DATA_TYPE_TEXTAREA,
    FieldSpec,
    daily_amount_field_keys,
    daily_int_field_keys,
    get_field_spec,
    template_field_specs,
)


def legacy_daily_int_fields() -> Set[str]:
    """Return the current production integer daily fields, excluding future staged fields."""
    return set(daily_int_field_keys(include_future=False))


def legacy_daily_amount_fields() -> Set[str]:
    """Return the current production amount daily fields, excluding future staged fields."""
    return set(daily_amount_field_keys(include_future=False))


def configured_daily_int_fields() -> Set[str]:
    """Return all configured integer daily fields, including staged future fields."""
    return set(daily_int_field_keys(include_future=True))


def configured_daily_amount_fields() -> Set[str]:
    """Return all configured amount daily fields, including staged future fields."""
    return set(daily_amount_field_keys(include_future=True))


def _template_type(spec: FieldSpec) -> str:
    if spec.data_type == DATA_TYPE_DATE:
        return "date"
    if spec.data_type == DATA_TYPE_INT:
        return "int"
    if spec.data_type == DATA_TYPE_TEXTAREA:
        return "textarea"
    if spec.data_type == DATA_TYPE_AMOUNT:
        # Keep the legacy template contract: amount-like cells are typed as text.
        return "text"
    return "text"


def default_template_fields(*, include_future: bool = False) -> List[Dict]:
    """Build template_fields-compatible dictionaries from the field center.

    include_future defaults to False so callers can opt in without changing the
    current production template shape.
    """
    fields = []
    for spec in template_field_specs(include_future=include_future):
        fields.append(
            {
                "field_key": spec.resolved_template_key,
                "field_label": spec.label,
                "field_type": _template_type(spec),
                "is_required": 1 if spec.template_required else 0,
                "display_order": int(spec.template_order),
            }
        )
    return fields


def legacy_entry_field_keys() -> Tuple[str, ...]:
    """Return the field-key order matching the current EntryTab columns."""
    return ENTRY_LEGACY_FIELD_KEYS


def legacy_entry_labels() -> List[str]:
    labels = []
    for key in ENTRY_LEGACY_FIELD_KEYS:
        if key == "account_manager_name":
            labels.append("客户经理姓名")
            continue
        labels.append(get_field_spec(key).label)
    return labels
