from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config.field_registry import (
    DATA_TYPE_AMOUNT,
    DATA_TYPE_INT,
    DATA_TYPE_PERCENT,
    DATA_TYPE_TEXT,
    DATA_TYPE_TEXTAREA,
    FieldDefinition,
    STORAGE_COMPUTED,
    STORAGE_DISPLAY_ONLY,
    STORAGE_DYNAMIC_METRIC,
    STORAGE_FIXED_COLUMN,
    get_field,
)
from app.db.database import DatabaseManager


DECIMAL_DATA_TYPES = {DATA_TYPE_AMOUNT, DATA_TYPE_PERCENT, "money", "decimal"}
TEXT_DATA_TYPES = {DATA_TYPE_TEXT, DATA_TYPE_TEXTAREA, "date"}


def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


class FieldValueService:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_value(self, record: Dict[str, Any], field_key: str) -> Any:
        field_def = self._get_field_def(field_key)
        storage_type = self._storage_type(field_def)
        storage_column = self._storage_column(field_def, field_key)

        if storage_type == STORAGE_FIXED_COLUMN:
            if storage_column in record:
                return self.normalize_value(field_def, record.get(storage_column))
            return self.normalize_value(field_def, None)

        if storage_type == STORAGE_DYNAMIC_METRIC:
            record_id = self._record_primary_id(record)
            if record_id <= 0:
                return self.normalize_value(field_def, None)
            value = self._read_dynamic_value(record_id, field_key)
            return self.normalize_value(field_def, value)

        return record.get(field_key, self.normalize_value(field_def, None))

    def set_value(self, record_id: int, field_key: str, value: Any) -> None:
        normalized_record_id = int(record_id or 0)
        if normalized_record_id <= 0:
            raise ValueError("record_id 必须为正整数")

        field_def = self._get_field_def(field_key)
        normalized = self.normalize_value(field_def, value)
        storage_type = self._storage_type(field_def)
        storage_column = self._storage_column(field_def, field_key)

        if storage_type == STORAGE_FIXED_COLUMN:
            if not self._is_daily_record_column(storage_column):
                raise ValueError("固定列不存在: {}".format(storage_column))
            with self.db.get_connection() as conn:
                conn.execute(
                    "UPDATE daily_records SET {} = ?, updated_at = ? WHERE id = ?".format(
                        self._quote_identifier(storage_column)
                    ),
                    (normalized, _now_str(), normalized_record_id),
                )
                conn.commit()
            return

        if storage_type == STORAGE_DYNAMIC_METRIC:
            self._upsert_dynamic_value(normalized_record_id, field_key, field_def, normalized)
            return

        if storage_type in {STORAGE_COMPUTED, STORAGE_DISPLAY_ONLY}:
            raise ValueError("字段不可写入: {}".format(field_key))
        raise ValueError("未知字段存储类型: {}".format(storage_type))

    def get_values(self, record_id: int, field_keys: Iterable[str]) -> Dict[str, Any]:
        record = self.read_record_with_dynamic_values(record_id)
        return {field_key: self.get_value(record, field_key) for field_key in field_keys}

    def set_values(self, record_id: int, values_dict: Dict[str, Any]) -> None:
        for field_key, value in values_dict.items():
            self.set_value(record_id, field_key, value)

    def read_record_with_dynamic_values(self, record_id: int) -> Dict[str, Any]:
        normalized_record_id = int(record_id or 0)
        if normalized_record_id <= 0:
            return {}

        with self.db.get_connection() as conn:
            record_row = conn.execute(
                "SELECT * FROM daily_records WHERE id = ?",
                (normalized_record_id,),
            ).fetchone()
            if record_row is None:
                return {}
            record = dict(record_row)
            dynamic_rows = conn.execute(
                """
                SELECT field_key, value_number, value_text
                FROM daily_metric_values
                WHERE record_id = ?
                """,
                (normalized_record_id,),
            ).fetchall()

        for row in dynamic_rows:
            field_key = str(row["field_key"])
            field_def = self._get_field_def(field_key)
            raw_value = row["value_text"] if row["value_text"] is not None else row["value_number"]
            record[field_key] = self.normalize_value(field_def, raw_value)
        return record

    def normalize_value(self, field_def: Any, value: Any) -> Any:
        ok, message = self.validate_value(field_def, value)
        if not ok:
            raise ValueError(message)

        data_type = self._data_type(field_def)
        if value is None or str(value).strip() == "":
            value = self._default_value(field_def)

        if data_type == DATA_TYPE_INT:
            return int(float(value or 0))
        if data_type in DECIMAL_DATA_TYPES:
            return float(value or 0)
        if data_type in TEXT_DATA_TYPES:
            return str(value or "")
        return value

    def validate_value(self, field_def: Any, value: Any) -> Tuple[bool, str]:
        data_type = self._data_type(field_def)
        label = self._label(field_def)
        if value is None or str(value).strip() == "":
            return True, ""

        if data_type == DATA_TYPE_INT:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return False, "{}必须是整数".format(label)
            if not number.is_integer():
                return False, "{}必须是整数".format(label)
            if number < 0:
                return False, "{}不能为负数".format(label)
            return True, ""

        if data_type in DECIMAL_DATA_TYPES:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return False, "{}必须是数字".format(label)
            if number < 0:
                return False, "{}不能为负数".format(label)
            return True, ""

        return True, ""

    def _get_field_def(self, field_key: str) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM field_definitions WHERE field_key = ?",
                (field_key,),
            ).fetchone()
            if row is not None:
                return dict(row)

        spec = get_field(field_key)
        if spec is None:
            raise KeyError("未知字段: {}".format(field_key))
        return self._field_spec_to_dict(spec)

    @staticmethod
    def _field_spec_to_dict(spec: FieldDefinition) -> Dict[str, Any]:
        return {
            "field_key": spec.field_key,
            "label": spec.label,
            "data_type": spec.data_type,
            "default_value": str(spec.default_value if spec.default_value is not None else ""),
            "storage_type": spec.storage_type,
            "storage_column": spec.storage_column,
        }

    @staticmethod
    def _data_type(field_def: Any) -> str:
        if isinstance(field_def, dict):
            return str(field_def.get("data_type") or DATA_TYPE_TEXT)
        return str(getattr(field_def, "data_type", DATA_TYPE_TEXT))

    @staticmethod
    def _label(field_def: Any) -> str:
        if isinstance(field_def, dict):
            return str(field_def.get("label") or field_def.get("field_key") or "字段")
        return str(getattr(field_def, "label", "字段"))

    @staticmethod
    def _default_value(field_def: Any) -> Any:
        if isinstance(field_def, dict):
            return field_def.get("default_value")
        return getattr(field_def, "default_value", "")

    @staticmethod
    def _storage_type(field_def: Any) -> str:
        if isinstance(field_def, dict):
            return str(field_def.get("storage_type") or STORAGE_DISPLAY_ONLY)
        return str(getattr(field_def, "storage_type", STORAGE_DISPLAY_ONLY))

    @staticmethod
    def _storage_column(field_def: Any, field_key: str) -> str:
        if isinstance(field_def, dict):
            return str(field_def.get("storage_column") or field_key)
        return str(getattr(field_def, "storage_column", "") or field_key)

    def _read_dynamic_value(self, record_id: int, field_key: str) -> Any:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT value_number, value_text
                FROM daily_metric_values
                WHERE record_id = ? AND field_key = ?
                """,
                (record_id, field_key),
            ).fetchone()
            if row is None:
                return None
            if row["value_text"] is not None:
                return row["value_text"]
            return row["value_number"]

    def _upsert_dynamic_value(self, record_id: int, field_key: str, field_def: Any, value: Any) -> None:
        data_type = self._data_type(field_def)
        if data_type in {DATA_TYPE_INT} | DECIMAL_DATA_TYPES:
            value_number = float(value or 0)
            value_text = None
        else:
            value_number = None
            value_text = str(value or "")

        now = _now_str()
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_metric_values (
                    record_id, field_key, value_number, value_text, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id, field_key) DO UPDATE SET
                    value_number = excluded.value_number,
                    value_text = excluded.value_text,
                    updated_at = excluded.updated_at
                """,
                (record_id, field_key, value_number, value_text, now, now),
            )
            conn.commit()

    def _is_daily_record_column(self, column_name: str) -> bool:
        with self.db.get_connection() as conn:
            rows = conn.execute("PRAGMA table_info(daily_records)").fetchall()
            columns = {str(row["name"]) for row in rows}
        return column_name in columns

    @staticmethod
    def _record_primary_id(record: Dict[str, Any]) -> int:
        raw_id = record.get("id")
        try:
            return int(raw_id or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + str(identifier).replace('"', '""') + '"'
