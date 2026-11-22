"""Filter 3: expected gaps are listed explicitly; any other missing month alerts."""

from decimal import Decimal

import pytest

from app.catalog import load_ficha_by_code
from app.domain import Flag, ParsedValue, Period
from app.validation.plausibility import check_plausibility

NEW_FICHAS = (
    "dane_ipc_annual_national",
    "dane_geih_unemployment_rate_national",
    "inflation_monthly_national",
    "inflation_ytd_national",
)


@pytest.mark.parametrize("code", NEW_FICHAS)
def test_new_fichas_load(code):
    assert load_ficha_by_code(code).code == code


def _ytd_values(missing=()):
    periods = [Period(y, 12) for y in range(2003, 2023)]
    periods += [Period(2023, m) for m in range(2, 13)] + [Period(2024, m) for m in range(2, 13) if m != 8]
    periods += [Period(2025, m) for m in range(2, 13)] + [Period(2026, m) for m in range(2, 10)]
    return [ParsedValue(p, "national", Decimal("1")) for p in periods if p not in missing]


def _gap_periods(values, ficha):
    flags = check_plausibility(values, ficha, new_indices=[], history={})
    return [v.period for v, f in zip(values, flags) if Flag.GAP_BEFORE in f]


def test_ytd_expected_gaps_do_not_alert():
    assert _gap_periods(_ytd_values(), load_ficha_by_code("inflation_ytd_national")) == []


@pytest.mark.parametrize(
    ("missing", "flagged"),
    [
        (Period(2023, 5), Period(2023, 6)),
        (Period(2026, 3), Period(2026, 4)),
        (Period(2015, 12), Period(2016, 12)),  # the next value present carries the flag
    ],
)
def test_ytd_unexpected_gap_alerts(missing, flagged):
    values = _ytd_values(missing={missing})
    assert _gap_periods(values, load_ficha_by_code("inflation_ytd_national")) == [flagged]


def test_series_without_expected_gaps_still_alerts():
    ficha = load_ficha_by_code("inflation_monthly_national")
    values = [ParsedValue(Period(2026, m), "national", Decimal("0.3")) for m in (1, 2, 4)]
    assert _gap_periods(values, ficha) == [Period(2026, 4)]


def test_no_gaps_false_without_list_does_not_check():
    ficha = load_ficha_by_code("homicides_intentional_national")
    rules = ficha.plausibility.model_copy(update={"no_gaps": False, "expected_gaps": []})
    values = [ParsedValue(Period(2026, m), "national", Decimal("900")) for m in (1, 4)]
    assert _gap_periods(values, ficha.model_copy(update={"plausibility": rules})) == []
