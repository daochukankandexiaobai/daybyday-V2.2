from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional


FORMULA_TARGET_COMPLETION_RATE = "target_completion_rate"
FORMULA_SIGN_RATE = "sign_rate"
FORMULA_DAILY_SIGN_RATE = "daily_sign_rate"
FORMULA_QUALITY_VISIT_RATE = "quality_visit_rate"
FORMULA_APPROVAL_RATE = "approval_rate"
FORMULA_SALES_CONVERSION_RATE = "sales_conversion_rate"
FORMULA_REPAYMENT_CONVERSION_RATE = "repayment_conversion_rate"
FORMULA_WARRANT_CONVERSION_RATE = "warrant_conversion_rate"


def ratio_or_none(numerator: Any, denominator: Any) -> Optional[float]:
    """Return numerator / denominator, using None for invalid or zero denominators."""
    try:
        num = float(numerator or 0)
        den = float(denominator or 0)
    except (TypeError, ValueError):
        return None
    if den <= 0:
        return None
    return num / den


class FormulaService:
    """Central formula calculator for field-driven aggregation.

    Formula fields must be calculated from already-aggregated raw fields.
    They must not be directly summed, averaged, or otherwise aggregated from
    per-row formula values. For example, signing rate is:

        total signing count / (total visit count - total invalid visit count)

    It is not the average of daily signing rates.
    """

    def __init__(self) -> None:
        self._calculators = {
            FORMULA_TARGET_COMPLETION_RATE: self.target_completion_rate,
            "target_progress": self.target_completion_rate,
            FORMULA_SIGN_RATE: self.sign_rate,
            "signing_rate": self.sign_rate,
            FORMULA_DAILY_SIGN_RATE: self.daily_sign_rate,
            "daily_signing_rate": self.daily_sign_rate,
            FORMULA_QUALITY_VISIT_RATE: self.quality_visit_rate,
            "daily_quality_visit_rate": self.daily_quality_visit_rate,
            FORMULA_APPROVAL_RATE: self.approval_rate,
            "daily_approval_rate": self.daily_approval_rate,
            FORMULA_SALES_CONVERSION_RATE: self.sales_conversion_rate,
            "daily_sales_conversion_rate": self.daily_sales_conversion_rate,
            FORMULA_REPAYMENT_CONVERSION_RATE: self.repayment_conversion_rate,
            FORMULA_WARRANT_CONVERSION_RATE: self.warrant_conversion_rate,
        }

    def calculate(self, formula_id: str, values: Dict[str, Any]) -> Optional[float]:
        calculator = self._calculators.get(str(formula_id or ""))
        if calculator is None:
            return None
        return calculator(values)

    def calculate_many(self, values: Dict[str, Any], formula_ids: Iterable[str]) -> Dict[str, Optional[float]]:
        result = {}
        for formula_id in formula_ids:
            result[formula_id] = self.calculate(formula_id, values)
        return result

    def is_formula_known(self, formula_id: str) -> bool:
        return str(formula_id or "") in self._calculators

    def get_calculators(self) -> Dict[str, Callable[[Dict[str, Any]], Optional[float]]]:
        return dict(self._calculators)

    def target_completion_rate(self, values: Dict[str, Any]) -> Optional[float]:
        repayment = _first_number(
            values,
            (
                "repayment_amount_cumulative",
                "repayment_amount",
                "repayment_amount_daily",
            ),
        )
        target = _first_number(
            values,
            (
                "cycle_repayment_target",
                "team_cycle_target",
                "cycle_target",
                "target_amount",
                "repayment_target",
            ),
        )
        return ratio_or_none(repayment, target)

    def sign_rate(self, values: Dict[str, Any]) -> Optional[float]:
        signing = _first_number(
            values,
            (
                "signing_count_cumulative",
                "signing_count",
                "signing_count_daily",
            ),
        )
        visit = _first_number(
            values,
            (
                "visit_count_cumulative",
                "visit_count",
                "invitation_cumulative",
                "visit_count_daily",
            ),
        )
        invalid_visit = _first_number(
            values,
            (
                "invalid_visit_count_cumulative",
                "invalid_visit_count",
                "invalid_visit_count_daily",
            ),
        )
        return ratio_or_none(signing, visit - invalid_visit)

    def daily_sign_rate(self, values: Dict[str, Any]) -> Optional[float]:
        signing = _first_number(values, ("signing_count_daily", "signing_count"))
        visit = _first_number(values, ("visit_count_daily", "visit_count"))
        invalid_visit = _first_number(values, ("invalid_visit_count_daily", "invalid_visit_count"))
        return ratio_or_none(signing, visit - invalid_visit)

    def quality_visit_rate(self, values: Dict[str, Any]) -> Optional[float]:
        quality_visit = _first_number(
            values,
            (
                "quality_visit_count_cumulative",
                "quality_visit_count",
                "quality_visit_count_daily",
            ),
        )
        visit = _first_number(
            values,
            (
                "visit_count_cumulative",
                "visit_count",
                "invitation_cumulative",
                "visit_count_daily",
            ),
        )
        return ratio_or_none(quality_visit, visit)

    def daily_quality_visit_rate(self, values: Dict[str, Any]) -> Optional[float]:
        quality_visit = _first_number(values, ("quality_visit_count_daily", "quality_visit_count"))
        visit = _first_number(values, ("visit_count_daily", "visit_count"))
        return ratio_or_none(quality_visit, visit)

    def approval_rate(self, values: Dict[str, Any]) -> Optional[float]:
        approval = _first_number(
            values,
            (
                "approval_customer_count_cumulative",
                "approval_customer_count",
                "approval_customer_count_daily",
            ),
        )
        signing = _first_number(
            values,
            (
                "signing_count_cumulative",
                "signing_count",
                "signing_count_daily",
            ),
        )
        return ratio_or_none(approval, signing)

    def daily_approval_rate(self, values: Dict[str, Any]) -> Optional[float]:
        approval = _first_number(values, ("approval_customer_count_daily", "approval_customer_count"))
        signing = _first_number(values, ("signing_count_daily", "signing_count"))
        return ratio_or_none(approval, signing)

    def sales_conversion_rate(self, values: Dict[str, Any]) -> Optional[float]:
        signing = _first_number(
            values,
            (
                "signing_count_cumulative",
                "signing_count",
                "signing_count_daily",
            ),
        )
        visit = _first_number(
            values,
            (
                "visit_count_cumulative",
                "visit_count",
                "invitation_cumulative",
                "visit_count_daily",
            ),
        )
        return ratio_or_none(signing, visit)

    def daily_sales_conversion_rate(self, values: Dict[str, Any]) -> Optional[float]:
        signing = _first_number(values, ("signing_count_daily", "signing_count"))
        visit = _first_number(values, ("visit_count_daily", "visit_count"))
        return ratio_or_none(signing, visit)

    def repayment_conversion_rate(self, values: Dict[str, Any]) -> Optional[float]:
        repayment_customer = _first_number(
            values,
            (
                "repayment_customer_count_cumulative",
                "repayment_customer_count",
                "repayment_customer_count_daily",
            ),
        )
        visit = _first_number(
            values,
            (
                "visit_count_cumulative",
                "visit_count",
                "invitation_cumulative",
                "visit_count_daily",
            ),
        )
        return ratio_or_none(repayment_customer, visit)

    def warrant_conversion_rate(self, values: Dict[str, Any]) -> Optional[float]:
        repayment_customer = _first_number(
            values,
            (
                "repayment_customer_count_cumulative",
                "repayment_customer_count",
                "repayment_customer_count_daily",
            ),
        )
        signing = _first_number(
            values,
            (
                "signing_count_cumulative",
                "signing_count",
                "signing_count_daily",
            ),
        )
        return ratio_or_none(repayment_customer, signing)


def _first_number(values: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    for key in keys:
        if key not in values:
            continue
        value = values.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default
