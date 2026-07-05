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
    from app.fields.formula_service import (
        FORMULA_APPROVAL_RATE,
        FORMULA_DAILY_SIGN_RATE,
        FORMULA_QUALITY_VISIT_RATE,
        FORMULA_SALES_CONVERSION_RATE,
        FORMULA_SIGN_RATE,
        FORMULA_TARGET_COMPLETION_RATE,
        FORMULA_WARRANT_CONVERSION_RATE,
        FormulaService,
    )

    service = FormulaService()

    _assert_close(
        service.calculate(
            FORMULA_TARGET_COMPLETION_RATE,
            {"repayment_amount_cumulative": 500, "cycle_repayment_target": 1000},
        ),
        0.5,
        "target completion rate",
    )
    _assert_close(
        service.calculate(
            FORMULA_SIGN_RATE,
            {"signing_count": 6, "visit_count": 20, "invalid_visit_count": 5},
        ),
        6.0 / 15.0,
        "sign rate",
    )
    _assert_close(
        service.calculate(
            FORMULA_DAILY_SIGN_RATE,
            {"signing_count_daily": 3, "visit_count_daily": 8, "invalid_visit_count_daily": 2},
        ),
        0.5,
        "daily sign rate",
    )
    _assert_close(
        service.calculate(
            FORMULA_QUALITY_VISIT_RATE,
            {"quality_visit_count": 4, "visit_count": 20},
        ),
        0.2,
        "quality visit rate",
    )
    _assert_close(
        service.calculate(
            FORMULA_APPROVAL_RATE,
            {"approval_customer_count": 3, "signing_count": 6},
        ),
        0.5,
        "approval rate",
    )
    _assert_close(
        service.calculate(
            FORMULA_SALES_CONVERSION_RATE,
            {"signing_count": 6, "visit_count": 20},
        ),
        0.3,
        "sales conversion rate",
    )
    _assert_close(
        service.calculate(
            FORMULA_WARRANT_CONVERSION_RATE,
            {"repayment_customer_count": 2, "signing_count": 6},
        ),
        2.0 / 6.0,
        "warrant conversion rate",
    )

    _assert(
        service.calculate(FORMULA_SIGN_RATE, {"signing_count": 1, "visit_count": 0}) is None,
        "zero denominator should return None",
    )
    _assert(
        service.calculate(
            FORMULA_SIGN_RATE,
            {"signing_count": 1, "visit_count": 3, "invalid_visit_count": 3},
        )
        is None,
        "zero valid visit denominator should return None",
    )
    _assert(
        service.calculate("", {"signing_count": 1, "visit_count": 3}) is None,
        "missing formula_id should return None",
    )
    _assert(
        service.calculate("unknown_formula", {"signing_count": 1, "visit_count": 3}) is None,
        "unknown formula_id should return None",
    )

    print("[formula] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
