"""Filter 5 per period: explicit states and levels; a contrast never run is pending, never passed."""

from decimal import Decimal

import pytest

from app.catalog import KnownVersionDifference
from app.domain import ContrastLevel, ContrastStatus, ParsedValue, Period
from app.validation.contrast import (
    ContrastSource,
    ExpectedSource,
    PeriodContrast,
    compare_with_sources,
    period_contrast,
)

MONTHLY, ANNUAL = ContrastLevel.MONTHLY, ContrastLevel.ANNUAL
N = "national"


def _series(year: int, value: int = 100) -> list[ParsedValue]:
    return [ParsedValue(Period(year, m), N, Decimal(value)) for m in range(1, 13)]


def _monthly(name: str, year: int, value: int = 100, **overrides) -> ContrastSource:
    values = {Period(year, m): Decimal(value) for m in range(1, 13)}
    values.update({Period.parse(k): Decimal(v) for k, v in overrides.items()})
    return ContrastSource(name, MONTHLY, values, "sha")


def _annual(name: str, year: int, total: int) -> ContrastSource:
    return ContrastSource(name, ANNUAL, {Period(year): Decimal(total)}, "sha")


def _ficha(ficha, differences=()):
    return ficha("homicides_intentional_national").model_copy(
        update={"known_version_differences": list(differences)}
    )


def _status(report, period):
    return report[(Period.parse(period), N)]


# States of a single value


def test_never_run_is_pending(ficha):
    assert period_contrast(_ficha(ficha), None, (Period(2026, 9), N)).status is ContrastStatus.PENDING


def test_missing_period_in_report_is_pending(ficha):
    assert period_contrast(_ficha(ficha), {}, (Period(2026, 9), N)).status is ContrastStatus.PENDING


def test_single_source_series_is_not_applicable(ficha):
    report = {(Period(2026), N): PeriodContrast(ContrastStatus.PASSED)}
    state = period_contrast(ficha("minimum_wage_monthly"), report, (Period(2026), N))
    assert state.status is ContrastStatus.NOT_APPLICABLE


# Comparison against sources


def test_year_without_any_source_is_unavailable(ficha):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    report, _ = compare_with_sources(_series(2012), _ficha(ficha), expected, {})
    assert _status(report, "2012-05").status is ContrastStatus.UNAVAILABLE


def test_expected_source_not_loaded_is_pending(ficha):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    report, _ = compare_with_sources(_series(2024), _ficha(ficha), expected, {}, {"registro": "download failed"})
    state = _status(report, "2024-05")
    assert state.status is ContrastStatus.PENDING
    assert "download failed" in state.details[0]


def test_matching_monthly_source_passes_at_monthly_level(ficha):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    report, diffs = compare_with_sources(_series(2024), _ficha(ficha), expected, {"registro": _monthly("registro", 2024)})
    state = _status(report, "2024-05")
    assert (state.status, state.level) == (ContrastStatus.PASSED, MONTHLY)
    assert diffs == []
    [check] = state.checks  # every comparison is kept for the contrast_check table
    assert (check.source, check.compared_period, check.source_value, check.series_value, check.outcome) == (
        "registro", Period(2024, 5), Decimal(100), Decimal(100), "passed",
    )


def test_annual_only_passes_at_annual_level(ficha):
    expected = [ExpectedSource("anual", ANNUAL, frozenset({2024}))]
    report, _ = compare_with_sources(_series(2024), _ficha(ficha), expected, {"anual": _annual("anual", 2024, 1200)})
    assert _status(report, "2024-05").level is ANNUAL


def test_both_must_pass_and_level_is_monthly(ficha):
    expected = [
        ExpectedSource("anual", ANNUAL, frozenset({2024})),
        ExpectedSource("registro", MONTHLY, frozenset({2024})),
    ]
    loaded = {"anual": _annual("anual", 2024, 1200), "registro": _monthly("registro", 2024)}
    report, _ = compare_with_sources(_series(2024), _ficha(ficha), expected, loaded)
    state = _status(report, "2024-05")
    assert (state.status, state.level) == (ContrastStatus.PASSED, MONTHLY)
    assert {(c.source, c.level, c.compared_period) for c in state.checks} == {
        ("anual", ANNUAL, Period(2024)), ("registro", MONTHLY, Period(2024, 5)),
    }

    loaded["anual"] = _annual("anual", 2024, 1201)
    report, _ = compare_with_sources(_series(2024), _ficha(ficha), expected, loaded)
    assert _status(report, "2024-05").status is ContrastStatus.FAILED  # annual mismatch fails every month


def test_annual_check_needs_a_complete_year(ficha):
    expected = [ExpectedSource("anual", ANNUAL, frozenset({2026}))]
    partial = _series(2026)[:9]
    report, _ = compare_with_sources(partial, _ficha(ficha), expected, {"anual": _annual("anual", 2026, 900)})
    assert _status(report, "2026-05").status is ContrastStatus.PENDING


def test_new_difference_fails_and_is_listed(ficha):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    loaded = {"registro": _monthly("registro", 2024, **{"2024-10": 99})}
    report, diffs = compare_with_sources(_series(2024), _ficha(ficha), expected, loaded)
    assert _status(report, "2024-10").status is ContrastStatus.FAILED
    assert _status(report, "2024-09").status is ContrastStatus.PASSED
    [d] = diffs
    assert (d.period, d.source, d.source_value, d.series_value, d.registered) == (
        Period(2024, 10), "registro", Decimal(99), Decimal(100), False,
    )


def _registered(source_value, series_value=100):
    return KnownVersionDifference(
        period="2024-10", level="monthly", source="registro",
        source_value=Decimal(source_value), series_value=Decimal(series_value),
    )


def test_registered_difference_passes_and_is_marked(ficha):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    loaded = {"registro": _monthly("registro", 2024, **{"2024-10": 99})}
    report, diffs = compare_with_sources(_series(2024), _ficha(ficha, [_registered(99)]), expected, loaded)
    state = _status(report, "2024-10")
    assert state.status is ContrastStatus.PASSED and state.known_difference
    assert diffs[0].registered


@pytest.mark.parametrize(
    ("source_value", "series_value"),
    [(98, 100), (99, 101)],  # the source changed / the series changed
)
def test_changed_registered_difference_fails(ficha, source_value, series_value):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    series = [v if v.period != Period(2024, 10) else ParsedValue(v.period, N, Decimal(series_value)) for v in _series(2024)]
    loaded = {"registro": _monthly("registro", 2024, **{"2024-10": source_value})}
    report, _ = compare_with_sources(series, _ficha(ficha, [_registered(99)]), expected, loaded)
    assert _status(report, "2024-10").status is ContrastStatus.FAILED


def test_registered_difference_that_disappeared_fails(ficha):
    expected = [ExpectedSource("registro", MONTHLY, frozenset({2024}))]
    report, _ = compare_with_sources(
        _series(2024), _ficha(ficha, [_registered(99)]), expected, {"registro": _monthly("registro", 2024)}
    )
    assert _status(report, "2024-10").status is ContrastStatus.FAILED


def test_month_not_covered_by_source_is_pending(ficha):
    expected = [ExpectedSource("ultimo_mes", MONTHLY, frozenset({2026}))]
    source = ContrastSource("ultimo_mes", MONTHLY, {Period(2026, m): Decimal(100) for m in range(1, 10)}, "sha")
    series = _series(2026)[:10]  # datos.gov.co already has October
    report, _ = compare_with_sources(series, _ficha(ficha), expected, {"ultimo_mes": source})
    assert _status(report, "2026-09").status is ContrastStatus.PASSED
    assert _status(report, "2026-10").status is ContrastStatus.PENDING
