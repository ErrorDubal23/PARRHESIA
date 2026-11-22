"""Filter 4: |value - reference| <= 0.5 x 10^(-precision), with no rounding rule."""

from decimal import Decimal

import pytest

from app.catalog import ReferenceValue
from app.domain import ParsedValue, Period
from app.validation.references import check_references


def _ficha_with(ficha, value: str, precision: int):
    ref = ReferenceValue(period="2026-08", value=value, precision=precision, published_by="DANE", document="test")
    return ficha("unemployment_rate_national").model_copy(update={"reference_values": [ref]})


@pytest.mark.parametrize(
    ("actual", "passes"),
    [
        ("9.36", True),  # the real case: SUAMECA 9.36 vs DANE 9.4
        ("9.35", True),  # exactly at the tolerance
        ("9.45", True),
        ("9.30", False),
        ("9.34", False),
        ("9.46", False),
    ],
)
def test_precision_one(ficha, actual, passes):
    values = [ParsedValue(Period(2026, 8), "national", Decimal(actual))]
    [check] = check_references(values, _ficha_with(ficha, "9.4", 1))
    assert check.passed is passes


@pytest.mark.parametrize(("actual", "passes"), [("1750905", True), ("1750905.5", True), ("1750906", False)])
def test_precision_zero(ficha, actual, passes):
    values = [ParsedValue(Period(2026, 8), "national", Decimal(actual))]
    [check] = check_references(values, _ficha_with(ficha, "1750905", 0))
    assert check.passed is passes


def test_missing_period_fails(ficha):
    values = [ParsedValue(Period(2026, 7), "national", Decimal("8.1"))]
    [check] = check_references(values, _ficha_with(ficha, "9.4", 1))
    assert not check.passed


def test_missing_value_fails(ficha):
    values = [ParsedValue(Period(2026, 8), "national", None)]
    [check] = check_references(values, _ficha_with(ficha, "9.4", 1))
    assert not check.passed
