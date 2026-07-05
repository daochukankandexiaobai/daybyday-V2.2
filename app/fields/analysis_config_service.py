from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config.field_profiles import PROFILE_ANALYSIS_METRICS, get_profile_field_keys
from app.config.field_registry import (
    CATEGORY_CUMULATIVE,
    CATEGORY_DISPLAY,
    CATEGORY_FORMULA,
    CATEGORY_RAW_DAILY,
    DATA_TYPE_AMOUNT,
    DATA_TYPE_INT,
    DATA_TYPE_PERCENT,
    get_field,
    get_field_spec,
)
from app.fields.display_config_service import DisplayFieldConfigService, field_spec_to_display_row
from app.fields.registry import PAGE_ANALYSIS


ANALYSIS_TYPE_TREND = "trend"
ANALYSIS_TYPE_RANKING = "ranking"
ANALYSIS_TYPE_CONVERSION = "conversion"
ANALYSIS_TYPE_ALL = "all"
ANALYSIS_TYPE_NONE = "none"

NUMERIC_ANALYSIS_TYPES = {
    DATA_TYPE_INT,
    DATA_TYPE_AMOUNT,
    DATA_TYPE_PERCENT,
    "money",
    "decimal",
    "number",
    "real",
    "float",
}

ANALYSIS_CATEGORIES = {
    CATEGORY_RAW_DAILY,
    CATEGORY_CUMULATIVE,
    CATEGORY_FORMULA,
    # Existing query-summary metrics such as repayment_amount are display
    # fields in the current registry. Keep them analyzable for compatibility.
    CATEGORY_DISPLAY,
}

RANKING_FIELD_ORDER = (
    "repayment_amount",
    "signing_count",
    "visit_count",
    "quality_visit_count",
    "four_star_customer_count",
    "five_star_customer_count",
    "sales_conversion_rate",
    "warrant_conversion_rate",
)

RANKING_FIELD_KEYS = set(RANKING_FIELD_ORDER)

CONVERSION_FIELD_KEYS = {
    "signing_rate",
    "quality_visit_rate",
    "approval_rate",
    "repayment_conversion_rate",
    "sales_conversion_rate",
    "warrant_conversion_rate",
}

SUMMARY_KEY_BY_DAILY_KEY = {
    "repayment_amount_daily": "repayment_amount",
    "loan_amount_daily": "loan_amount",
    "visit_count_daily": "visit_count",
    "invalid_visit_count_daily": "invalid_visit_count",
    "signing_count_daily": "signing_count",
    "quality_visit_count_daily": "quality_visit_count",
    "approval_customer_count_daily": "approval_customer_count",
    "repayment_customer_count_daily": "repayment_customer_count",
    "four_star_customer_count_daily": "four_star_customer_count",
    "five_star_customer_count_daily": "five_star_customer_count",
}


class AnalysisConfigService:
    """Read analyzable metrics from field config with registry fallback."""

    def __init__(self, db_manager: Optional[Any] = None) -> None:
        self.db_manager = db_manager
        self.display_config_service = DisplayFieldConfigService(db_manager) if db_manager is not None else None

    def get_analysis_fields(self) -> List[Dict[str, Any]]:
        rows = self._load_configured_rows()
        rows = self._append_missing_default_rows(rows)
        result = []
        for row in rows:
            enriched = self._enrich_row(row)
            if self._is_analyzable_row(enriched):
                result.append(enriched)
        return result

    def get_fields_for_analysis_type(self, analysis_type: str) -> List[Dict[str, Any]]:
        normalized = str(analysis_type or ANALYSIS_TYPE_ALL).strip().lower()
        if normalized == ANALYSIS_TYPE_ALL:
            return [row for row in self.get_analysis_fields() if ANALYSIS_TYPE_NONE not in row.get("analysis_types", ())]

        fields = []
        for row in self.get_analysis_fields():
            types = set(row.get("analysis_types", ()))
            if ANALYSIS_TYPE_ALL in types or normalized in types:
                fields.append(row)
        if normalized == ANALYSIS_TYPE_RANKING:
            return self._sort_ranking_fields(fields)
        return fields

    def get_metric_options(self, analysis_type: str) -> List[Tuple[str, str]]:
        return [
            (self.label_for_field(str(row.get("field_key", ""))), str(row.get("field_key", "")))
            for row in self.get_fields_for_analysis_type(analysis_type)
            if str(row.get("field_key", "")).strip()
        ]

    def label_for_field(self, field_key: str) -> str:
        for row in self.get_analysis_fields():
            if str(row.get("field_key", "")) == field_key:
                return str(row.get("label") or field_key)
        spec = get_field(field_key)
        return spec.label if spec is not None else field_key

    def row_for_field(self, field_key: str) -> Dict[str, Any]:
        for row in self.get_analysis_fields():
            if str(row.get("field_key", "")) == field_key:
                return row
        spec = get_field(field_key)
        return self._enrich_row(field_spec_to_display_row(spec, display_order=0)) if spec is not None else {}

    def is_percent_field(self, field_key: str) -> bool:
        row = self.row_for_field(field_key)
        return str(row.get("data_type", "")).lower() == DATA_TYPE_PERCENT

    @staticmethod
    def summary_key_for_metric(field_key: str) -> str:
        return SUMMARY_KEY_BY_DAILY_KEY.get(field_key, field_key)

    @staticmethod
    def _sort_ranking_fields(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        order = {field_key: index for index, field_key in enumerate(RANKING_FIELD_ORDER)}
        return sorted(
            fields,
            key=lambda row: (
                order.get(str(row.get("field_key", "")), len(order)),
                int(row.get("display_order", 0) or 0),
            ),
        )

    def _load_configured_rows(self) -> List[Dict[str, Any]]:
        if self.display_config_service is not None:
            return self.display_config_service.get_page_fields_with_fallback_keys(
                page_key=PAGE_ANALYSIS,
                fallback_field_keys=self._default_metric_keys(),
                template_key="analysis_default",
            )
        return self._rows_from_field_keys(self._default_metric_keys())

    def _append_missing_default_rows(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = [dict(row) for row in rows]
        known_keys = {str(row.get("field_key", "")) for row in result}
        hidden_or_visible_keys = self._visibility_keys()

        for field_key in self._default_metric_keys():
            if field_key in known_keys or field_key in hidden_or_visible_keys:
                continue
            spec = get_field(field_key)
            if spec is None:
                continue
            result.append(field_spec_to_display_row(spec, display_order=len(result) + 1))
            known_keys.add(field_key)
        return result

    def _visibility_keys(self) -> set:
        if self.db_manager is None:
            return set()
        try:
            with self.db_manager.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT field_key
                    FROM field_page_visibility
                    WHERE page_key = ?
                    """,
                    (PAGE_ANALYSIS,),
                ).fetchall()
            return {str(row["field_key"]) for row in rows}
        except Exception:  # noqa: BLE001
            return set()

    def _enrich_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(row)
        field_key = str(enriched.get("field_key", ""))
        spec = get_field(field_key)
        if spec is not None:
            enriched.setdefault("label", spec.label)
            enriched.setdefault("data_type", spec.data_type)
            enriched.setdefault("category", spec.category)
            enriched.setdefault("group_key", spec.group_key)
            enriched.setdefault("aggregation", spec.aggregation)
            enriched.setdefault("formula_id", spec.formula_id)
            enriched.setdefault("storage_type", spec.storage_type)
            enriched.setdefault("storage_column", spec.storage_column)
            if not str(enriched.get("formula_id", "")).strip():
                enriched["formula_id"] = spec.formula_id
        enriched["analysis_types"] = self._analysis_types_for_row(enriched)
        return enriched

    def _analysis_types_for_row(self, row: Dict[str, Any]) -> Tuple[str, ...]:
        field_key = str(row.get("field_key", ""))
        spec = get_field(field_key)
        types = set()
        if spec is not None:
            types.update(str(item).strip().lower() for item in spec.chart_supported if str(item).strip())

        template_types = self._analysis_types_from_template(field_key)
        types.update(template_types)

        if field_key in RANKING_FIELD_KEYS:
            types.add(ANALYSIS_TYPE_RANKING)
        if field_key in CONVERSION_FIELD_KEYS:
            types.add(ANALYSIS_TYPE_CONVERSION)

        category = str(row.get("category", ""))
        data_type = str(row.get("data_type", "")).lower()
        if field_key.endswith("_daily") and data_type in NUMERIC_ANALYSIS_TYPES:
            types.add(ANALYSIS_TYPE_TREND)
        if category == CATEGORY_RAW_DAILY and data_type in NUMERIC_ANALYSIS_TYPES:
            types.add(ANALYSIS_TYPE_TREND)
        if category == CATEGORY_FORMULA or data_type == DATA_TYPE_PERCENT:
            if field_key in CONVERSION_FIELD_KEYS:
                types.add(ANALYSIS_TYPE_CONVERSION)

        if not types:
            types.add(ANALYSIS_TYPE_NONE)
        return tuple(sorted(types))

    def _analysis_types_from_template(self, field_key: str) -> Tuple[str, ...]:
        if self.db_manager is None:
            return ()
        try:
            with self.db_manager.get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT config_json
                    FROM view_templates
                    WHERE template_key = 'analysis_default'
                      AND enabled = 1
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    return ()
                payload = json.loads(str(row["config_json"] or "{}"))
        except Exception:  # noqa: BLE001
            return ()

        analysis_types = payload.get("analysis_types", {})
        if not isinstance(analysis_types, dict):
            return ()
        raw = analysis_types.get(field_key, [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return ()
        return tuple(str(item).strip().lower() for item in raw if str(item).strip())

    @staticmethod
    def _is_analyzable_row(row: Dict[str, Any]) -> bool:
        if int(row.get("enabled", 1) or 0) != 1:
            return False
        data_type = str(row.get("data_type", "")).lower()
        if data_type not in NUMERIC_ANALYSIS_TYPES:
            return False
        category = str(row.get("category", ""))
        if category not in ANALYSIS_CATEGORIES:
            return False
        return ANALYSIS_TYPE_NONE not in set(row.get("analysis_types", ()))

    @staticmethod
    def _default_metric_keys() -> Tuple[str, ...]:
        return tuple(get_profile_field_keys(PROFILE_ANALYSIS_METRICS))

    @staticmethod
    def _rows_from_field_keys(field_keys: Iterable[str]) -> List[Dict[str, Any]]:
        rows = []
        for index, field_key in enumerate(field_keys, start=1):
            spec = get_field_spec(str(field_key))
            rows.append(field_spec_to_display_row(spec, display_order=index))
        return rows
