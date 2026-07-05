from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.fields.formula_service import FormulaService


AGGREGATION_SUM = "sum"
AGGREGATION_AVG = "avg"
AGGREGATION_MAX = "max"
AGGREGATION_MIN = "min"
AGGREGATION_LATEST = "latest"
AGGREGATION_COUNT = "count"
AGGREGATION_NONE = "none"
AGGREGATION_FORMULA = "formula"
AGGREGATION_DERIVED = "derived"


class AggregationService:
    """Central field aggregation helper.

    Formula fields are deliberately not summed or averaged here. Use
    aggregate_raw_then_formula() so raw fields are aggregated first, then
    formula fields are calculated from those totals.
    """

    def __init__(self, formula_service: Optional[FormulaService] = None) -> None:
        self.formula_service = formula_service or FormulaService()

    def aggregate(self, values: Iterable[Any], aggregation: str) -> Any:
        aggregation_key = normalize_aggregation(aggregation)
        value_list = list(values)

        if aggregation_key == AGGREGATION_NONE:
            return None
        if aggregation_key in (AGGREGATION_FORMULA, AGGREGATION_DERIVED):
            return None
        if aggregation_key == AGGREGATION_COUNT:
            return len([value for value in value_list if not _is_empty(value)])
        if aggregation_key == AGGREGATION_LATEST:
            return _latest_non_empty(value_list)

        numeric_values = _numeric_values(value_list)
        if not numeric_values:
            return None
        if aggregation_key == AGGREGATION_SUM:
            return sum(numeric_values)
        if aggregation_key == AGGREGATION_AVG:
            return sum(numeric_values) / len(numeric_values)
        if aggregation_key == AGGREGATION_MAX:
            return max(numeric_values)
        if aggregation_key == AGGREGATION_MIN:
            return min(numeric_values)

        raise ValueError("Unsupported aggregation: {}".format(aggregation))

    def aggregate_field(self, rows: Iterable[Mapping[str, Any]], field_key: str, aggregation: str) -> Any:
        return self.aggregate((row.get(field_key) for row in rows), aggregation)

    def aggregate_fields(
        self,
        rows: Iterable[Mapping[str, Any]],
        field_rules: Mapping[str, str],
    ) -> Dict[str, Any]:
        row_list = list(rows)
        result = {}
        for field_key, aggregation in field_rules.items():
            result[field_key] = self.aggregate_field(row_list, field_key, aggregation)
        return result

    def aggregate_raw_then_formula(
        self,
        rows: Iterable[Mapping[str, Any]],
        raw_rules: Mapping[str, str],
        formula_map: Mapping[str, str],
    ) -> Dict[str, Any]:
        """Aggregate raw fields, then calculate formula fields from totals.

        This is the intended path for rate fields such as signing_rate. It keeps
        formulas aligned with current rules: totals first, formula second.
        """
        result = self.aggregate_fields(rows, raw_rules)
        for output_field_key, formula_id in formula_map.items():
            result[output_field_key] = self.formula_service.calculate(formula_id, result)
        return result

    def aggregate_with_field_definitions(
        self,
        rows: Iterable[Mapping[str, Any]],
        field_definitions: Iterable[Any],
        formula_map: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        raw_rules = {}
        formula_rules = dict(formula_map or {})
        for field_def in field_definitions:
            field_key = _get_attr_or_key(field_def, "field_key") or _get_attr_or_key(field_def, "key")
            if not field_key:
                continue
            aggregation = _get_attr_or_key(field_def, "aggregation") or AGGREGATION_NONE
            normalized = normalize_aggregation(str(aggregation))
            formula_id = _get_attr_or_key(field_def, "formula_id")
            if normalized in (AGGREGATION_FORMULA, AGGREGATION_DERIVED):
                if formula_id:
                    formula_rules[str(field_key)] = str(formula_id)
                continue
            raw_rules[str(field_key)] = normalized
        return self.aggregate_raw_then_formula(rows, raw_rules, formula_rules)


def normalize_aggregation(aggregation: str) -> str:
    value = str(aggregation or AGGREGATION_NONE).strip().lower()
    aliases = {
        "average": AGGREGATION_AVG,
        "mean": AGGREGATION_AVG,
        "last": AGGREGATION_LATEST,
        "derived": AGGREGATION_DERIVED,
    }
    return aliases.get(value, value)


def _numeric_values(values: Iterable[Any]) -> List[float]:
    numbers = []
    for value in values:
        if _is_empty(value):
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _latest_non_empty(values: Iterable[Any]) -> Any:
    latest = None
    for value in values:
        if _is_empty(value):
            continue
        latest = value
    return latest


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _get_attr_or_key(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
