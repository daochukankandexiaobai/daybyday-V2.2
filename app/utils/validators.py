from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.config.field_rules import CONFIGURED_DAILY_AMOUNT_FIELD_KEYS, CONFIGURED_DAILY_INT_FIELD_KEYS


REQUIRED_EXPORT_KEYS = {"metadata", "export_info", "settlement_cycle_info", "records"}

DAILY_INT_FIELDS = set(CONFIGURED_DAILY_INT_FIELD_KEYS)
DAILY_AMOUNT_FIELDS = set(CONFIGURED_DAILY_AMOUNT_FIELD_KEYS)

# 这两个字段从第 2 批开始进入本地录入和数据库。旧版 JSON 数据包没有它们，
# 导入校验允许缺省，normalize_record 会补 0，避免破坏历史导入。
OPTIONAL_IMPORT_DAILY_FIELDS = {
    "four_star_customer_count_daily",
    "five_star_customer_count_daily",
}


def safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        num = int(value)
        return max(0, num)
    except (ValueError, TypeError):
        return 0


def safe_decimal(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        num = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if num < 0:
            return 0.0
        return float(num)
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _required_record_keys() -> set[str]:
    return {
        "record_id",
        "record_date",
        "region",
        "team_id",
        "team_name_snapshot",
        "team_manager_name_snapshot",
        "account_manager_id",
        "account_manager_name_snapshot",
        "settlement_cycle_code",
        "version",
        "updated_at",
        "record_hash",
    } | (DAILY_INT_FIELDS - OPTIONAL_IMPORT_DAILY_FIELDS) | DAILY_AMOUNT_FIELDS


def validate_export_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "JSON 顶层结构必须是对象"

    missing = REQUIRED_EXPORT_KEYS - set(payload.keys())
    if missing:
        return False, f"缺少字段: {', '.join(sorted(missing))}"

    metadata = payload.get("metadata")
    export_info = payload.get("export_info")
    cycle_info = payload.get("settlement_cycle_info")
    records = payload.get("records")

    if not isinstance(metadata, dict):
        return False, "metadata 必须为对象"
    if "template_version" not in metadata:
        return False, "metadata 缺少 template_version"

    if not isinstance(export_info, dict):
        return False, "export_info 必须为对象"
    if "export_id" not in export_info:
        return False, "export_info 缺少 export_id"

    if not isinstance(cycle_info, dict):
        return False, "settlement_cycle_info 必须为对象"
    if not str(cycle_info.get("cycle_code", "")).strip():
        return False, "settlement_cycle_info 缺少 cycle_code"

    if not isinstance(records, list):
        return False, "records 必须为数组"
    if len(records) == 0:
        return False, "records 不能为空"

    required_keys = _required_record_keys()
    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            return False, f"records[{idx}] 不是对象"
        miss = required_keys - set(record.keys())
        if miss:
            return False, f"records[{idx}] 缺少字段: {', '.join(sorted(miss))}"

    return True, "ok"


def validate_non_negative_int_input(text: str) -> tuple[bool, int, str]:
    raw = (text or "").strip()
    if raw == "":
        return True, 0, ""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return False, 0, "必须是非负整数"
    if value < 0:
        return False, 0, "必须是非负整数"
    return True, value, ""


def validate_non_negative_decimal_input(text: str, max_decimals: int = 2) -> tuple[bool, float, str]:
    raw = (text or "").strip()
    if raw == "":
        return True, 0.0, ""
    try:
        dec = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return False, 0.0, "必须是非负数字"
    if dec < 0:
        return False, 0.0, "必须是非负数字"

    normalized = format(dec, "f")
    if "." in normalized:
        decimals = normalized.rstrip("0").split(".")[1]
        if len(decimals) > max_decimals:
            return False, 0.0, f"最多保留 {max_decimals} 位小数"

    fixed = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return True, float(fixed), ""


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "record_id": str(record.get("record_id", "")).strip(),
        "record_date": str(record.get("record_date") or record.get("date") or "").strip(),
        "region": str(record.get("region", "")).strip(),
        "team_id": safe_int(record.get("team_id")),
        "team_name_snapshot": str(record.get("team_name_snapshot") or record.get("team") or "").strip(),
        "team_manager_name_snapshot": str(
            record.get("team_manager_name_snapshot")
            or record.get("team_manager_name")
            or ""
        ).strip(),
        "account_manager_id": safe_int(record.get("account_manager_id")),
        "account_manager_name_snapshot": str(
            record.get("account_manager_name_snapshot")
            or record.get("account_manager_name")
            or record.get("manager_name")
            or ""
        ).strip(),
        "settlement_cycle_code": str(record.get("settlement_cycle_code", "")).strip(),
        "remark": str(record.get("remark", "")),
        "version": max(1, safe_int(record.get("version", 1))),
        "created_at": str(record.get("created_at", "")).strip(),
        "updated_at": str(record.get("updated_at", "")).strip(),
        "template_version": str(record.get("template_version", "")).strip(),
        "record_hash": str(record.get("record_hash", "")).strip(),
        "source_type": str(record.get("source_type", "imported")).strip() or "imported",
        "source_file": record.get("source_file"),
    }

    for key in DAILY_INT_FIELDS:
        normalized[key] = safe_int(record.get(key))
    for key in DAILY_AMOUNT_FIELDS:
        normalized[key] = safe_decimal(record.get(key))

    return normalized
