"""Filter 5: contrast between sources, per period, with explicit states and levels."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.catalog import Ficha, KnownVersionDifference
from app.domain import ContrastCheck, ContrastLevel, ContrastStatus, Flag, ParsedValue, Period

Key = tuple[Period, str]


@dataclass(frozen=True)
class ExpectedSource:
    """A contrast source that should exist for some periods (from catalog/sources).

    Coverage is either whole years, or an explicit set of periods (e.g. only
    Decembers, or only the months where a second publication exists).
    """

    name: str
    level: ContrastLevel
    years: frozenset[int] = frozenset()
    periods: frozenset[Period] | None = None

    def covers(self, period: Period) -> bool:
        return period in self.periods if self.periods is not None else period.year in self.years


@dataclass(frozen=True)
class ContrastSource:
    """Values read from an archived contrast file. Annual values exclude provisional years."""

    name: str
    level: ContrastLevel
    values: Mapping[Period, Decimal]  # month periods (monthly) or year periods (annual)
    evidence_sha256: str
    # Filter 4 tolerance with the lower precision of the two publications:
    # 0.5 x 10^(-precision). Zero means exact.
    tolerance: Decimal = Decimal(0)
    # The series being judged is the producer and this source is a channel: on a
    # mismatch the series' value is used anyway, with a mandatory review alert.
    series_prevails: bool = False


@dataclass(frozen=True)
class PeriodContrast:
    status: ContrastStatus
    level: ContrastLevel | None = None
    known_difference: bool = False
    details: tuple[str, ...] = ()
    # The series is the producer's own publication: on a mismatch its value is
    # used anyway, with a mandatory review alert (docs/PROYECTO.md, filter 5).
    producer_prevails: bool = False
    checks: tuple[ContrastCheck, ...] = ()


@dataclass(frozen=True)
class Difference:
    """A mismatch found in a run, in the shape of a known_version_differences entry."""

    period: Period
    level: ContrastLevel
    source: str
    source_value: Decimal
    series_value: Decimal
    registered: bool


ContrastReport = Mapping[Key, PeriodContrast]

FLAGS = {
    ContrastStatus.PASSED: set(),
    ContrastStatus.PENDING: {Flag.CONTRAST_PENDING},
    ContrastStatus.NOT_APPLICABLE: {Flag.NO_SECOND_SOURCE},
    ContrastStatus.UNAVAILABLE: {Flag.CONTRAST_UNAVAILABLE},
    ContrastStatus.FAILED: {Flag.CONTRAST_MISMATCH},
}


def period_contrast(ficha: Ficha, report: ContrastReport | None, key: Key) -> PeriodContrast:
    """The contrast state of one stored value. A contrast never run is PENDING, never PASSED."""
    if not ficha.contrast_with:
        return PeriodContrast(ContrastStatus.NOT_APPLICABLE)
    if report is None:
        return PeriodContrast(ContrastStatus.PENDING, details=("no contrast was run",))
    return report.get(key, PeriodContrast(ContrastStatus.PENDING, details=("period not in the contrast report",)))


def flags_for(contrast: PeriodContrast) -> set[Flag]:
    if contrast.status is ContrastStatus.FAILED and contrast.producer_prevails:
        return {Flag.PRODUCER_VALUE_USED}
    flags = set(FLAGS[contrast.status])
    if contrast.known_difference:
        flags.add(Flag.KNOWN_VERSION_DIFFERENCE)
    return flags


def compare_with_sources(
    values: Sequence[ParsedValue],
    ficha: Ficha,
    expected: Sequence[ExpectedSource],
    loaded: Mapping[str, ContrastSource],
    pending_reasons: Mapping[str, str] | None = None,
) -> tuple[dict[Key, PeriodContrast], list[Difference]]:
    """Contrast each monthly value with every source expected for its year.

    - No source expected for the year -> UNAVAILABLE.
    - An expected source that is not loaded or does not cover the period -> PENDING.
    - A difference is accepted only if registered with both exact values; a new
      difference, a changed one, or a registered one that disappeared -> FAILED.
    """
    pending_reasons = pending_reasons or {}
    registered = {(d.period, d.level, d.source): d for d in ficha.known_version_differences}
    monthly = {(v.period, v.territory): v.value for v in values if v.period.granularity == "month"}
    annual_sums = _annual_sums(monthly)

    report: dict[Key, PeriodContrast] = {}
    differences: list[Difference] = []
    for (period, territory), value in monthly.items():
        sources = [s for s in expected if s.covers(period)]
        if not sources:
            report[(period, territory)] = PeriodContrast(
                ContrastStatus.UNAVAILABLE, details=(f"no contrast source published for {period}",)
            )
            continue
        outcomes, details, known, passed_levels, failed_sources, checks = [], [], False, set(), [], []
        for spec in sources:
            source = loaded.get(spec.name)
            target = period if spec.level is ContrastLevel.MONTHLY else Period(period.year)
            if source is None:
                outcomes.append(ContrastStatus.PENDING)
                details.append(f"{spec.name}: {pending_reasons.get(spec.name, 'not loaded')}")
                checks.append(ContrastCheck(spec.name, spec.level, target, None, None, Decimal(0), "pending"))
                continue
            series_value = value if spec.level is ContrastLevel.MONTHLY else annual_sums.get((period.year, territory))
            if target not in source.values or series_value is None:
                outcomes.append(ContrastStatus.PENDING)
                details.append(f"{spec.name}: does not cover {target}")
                checks.append(
                    ContrastCheck(spec.name, spec.level, target, source.values.get(target), series_value, source.tolerance, "pending")
                )
                continue
            source_value = source.values[target]
            entry = registered.get((target, spec.level, spec.name))
            outcome, is_known = _judge(source_value, series_value, entry, source.tolerance)
            outcomes.append(outcome)
            checks.append(
                ContrastCheck(spec.name, spec.level, target, source_value, series_value, source.tolerance, outcome.value, is_known)
            )
            if outcome is ContrastStatus.FAILED:
                failed_sources.append(source)
            if abs(source_value - series_value) > source.tolerance:
                differences.append(
                    Difference(target, spec.level, spec.name, source_value, series_value, registered=is_known)
                )
                details.append(f"{spec.name}: {target} source {source_value} vs series {series_value}")
            elif entry is not None:
                details.append(f"{spec.name}: registered difference for {target} no longer observed")
            if outcome is ContrastStatus.PASSED:
                passed_levels.add(spec.level)
                known = known or is_known
        status = (
            ContrastStatus.FAILED if ContrastStatus.FAILED in outcomes
            else ContrastStatus.PENDING if ContrastStatus.PENDING in outcomes
            else ContrastStatus.PASSED
        )
        level = None
        if status is ContrastStatus.PASSED:
            level = ContrastLevel.MONTHLY if ContrastLevel.MONTHLY in passed_levels else ContrastLevel.ANNUAL
        prevails = status is ContrastStatus.FAILED and all(s.series_prevails for s in failed_sources)
        report[(period, territory)] = PeriodContrast(status, level, known, tuple(details), prevails, tuple(checks))
    return report, _unique(differences)


def _judge(
    source_value: Decimal, series_value: Decimal, entry: KnownVersionDifference | None, tolerance: Decimal
) -> tuple[ContrastStatus, bool]:
    if abs(source_value - series_value) <= tolerance:
        return (ContrastStatus.PASSED, False) if entry is None else (ContrastStatus.FAILED, False)
    if entry is not None and entry.source_value == source_value and entry.series_value == series_value:
        return ContrastStatus.PASSED, True
    return ContrastStatus.FAILED, False


def _annual_sums(monthly: Mapping[Key, Decimal | None]) -> dict[tuple[int, str], Decimal]:
    """Sum per year, only for complete years with no missing value."""
    by_year: dict[tuple[int, str], list[Decimal | None]] = defaultdict(list)
    months: dict[tuple[int, str], set[int]] = defaultdict(set)
    for (period, territory), value in monthly.items():
        by_year[(period.year, territory)].append(value)
        months[(period.year, territory)].add(period.month)
    return {
        key: sum(vals)
        for key, vals in by_year.items()
        if months[key] == set(range(1, 13)) and None not in vals and len(vals) == 12
    }


def _unique(differences: list[Difference]) -> list[Difference]:
    seen, result = set(), []
    for d in differences:
        key = (d.period, d.level, d.source)
        if key not in seen:
            seen.add(key)
            result.append(d)
    return sorted(result, key=lambda d: (d.period, d.source))
