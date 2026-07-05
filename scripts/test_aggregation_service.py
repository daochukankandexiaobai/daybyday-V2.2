from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _assert_close(actual, expected, message):
    _assert(actual is not None, message + " returned None")
    _assert(abs(float(actual) - float(expected)) < 0.000001, message)


def main():
    from app.fields.aggregation_service import AggregationService
    from app.fields.formula_service import (
        FORMULA_QUALITY_VISIT_RATE,
        FORMULA_SIGN_RATE,
        FORMULA_TARGET_COMPLETION_RATE,
    )

    service = AggregationService()

    values = [1, 2, 3, None, ""]
    _assert_close(service.aggregate(values, "sum"), 6, "sum")
    _assert_close(service.aggregate(values, "avg"), 2, "avg")
    _assert_close(service.aggregate(values, "max"), 3, "max")
    _assert_close(service.aggregate(values, "min"), 1, "min")
    _assert(service.aggregate([None, "a", "b", ""], "latest") == "b", "latest")
    _assert(service.aggregate(values, "count") == 3, "count")
    _assert(service.aggregate(values, "none") is None, "none")
    _assert(service.aggregate(values, "formula") is None, "formula should not aggregate directly")

    rows = [
        {
            "signing_count": 1,
            "visit_count": 5,
            "invalid_visit_count": 1,
            "quality_visit_count": 2,
            "repayment_amount_cumulative": 100,
            "cycle_repayment_target": 1000,
        },
        {
            "signing_count": 2,
            "visit_count": 5,
            "invalid_visit_count": 0,
            "quality_visit_count": 1,
            "repayment_amount_cumulative": 200,
            "cycle_repayment_target": 1000,
        },
    ]
    result = service.aggregate_raw_then_formula(
        rows,
        {
            "signing_count": "sum",
            "visit_count": "sum",
            "invalid_visit_count": "sum",
            "quality_visit_count": "sum",
            "repayment_amount_cumulative": "sum",
            "cycle_repayment_target": "latest",
        },
        {
            "signing_rate": FORMULA_SIGN_RATE,
            "quality_visit_rate": FORMULA_QUALITY_VISIT_RATE,
            "target_progress": FORMULA_TARGET_COMPLETION_RATE,
        },
    )

    _assert_close(result["signing_count"], 3, "aggregated signing count")
    _assert_close(result["visit_count"], 10, "aggregated visit count")
    _assert_close(result["invalid_visit_count"], 1, "aggregated invalid visit count")

    # This must be 3 / (10 - 1), not the average of row-level signing rates.
    _assert_close(result["signing_rate"], 3.0 / 9.0, "formula sign rate after raw aggregation")
    _assert_close(result["quality_visit_rate"], 3.0 / 10.0, "formula quality visit rate")
    _assert_close(result["target_progress"], 300.0 / 1000.0, "formula target progress")

    print("[aggregation] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
