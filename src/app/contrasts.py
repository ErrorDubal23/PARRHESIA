"""Filter 5 runners for the inflation and unemployment series (SUAMECA and DANE).

Rules (docs/PROYECTO.md, filter 5):
- SUAMECA and the DANE are contrasted in both directions. If they match, both
  observations are approved. If not, the SUAMECA value goes to quarantine and
  the DANE value is used with a mandatory review alert.
- Tolerance: 0.5 x 10^(-lower precision). SUAMECA publishes 2 decimals, so 0.005.
- Monthly inflation and year-to-date inflation are contrasted with the IPC
  bulletins from 2023 on (coherence within the DANE); before 2023, unavailable.
  A year-to-date month published in only one place is unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from app.catalog import Ficha
from app.connectors.dane_archive import BULLETINS_FROM, DanePublications
from app.domain import ContrastLevel, ParsedValue, Period
from app.validation.contrast import ContrastReport, ContrastSource, Difference, ExpectedSource, compare_with_sources

TWO_DECIMALS = Decimal("0.005")
MONTHLY = ContrastLevel.MONTHLY

Values = Mapping[Period, Decimal]


@dataclass
class Runner:
    """A ContrastRunner for the pipeline that keeps the differences it found."""

    ficha: Ficha
    pairs: list[tuple[ExpectedSource, ContrastSource]]
    differences: list[Difference] = field(default_factory=list)

    def __call__(self, values: Sequence[ParsedValue]) -> ContrastReport:
        expected = [e for e, _ in self.pairs]
        loaded = {c.name: c for _, c in self.pairs}
        report, self.differences = compare_with_sources(values, self.ficha, expected, loaded)
        return report


def _pair(name: str, values: Values, *, periods=None, years=None, tolerance=TWO_DECIMALS, series_prevails=False):
    expected = ExpectedSource(
        name, MONTHLY, years=frozenset(years or ()), periods=None if periods is None else frozenset(periods)
    )
    return expected, ContrastSource(name, MONTHLY, dict(values), "", tolerance, series_prevails)


def suameca_inflation(ficha: Ficha, dane_annual: Values) -> Runner:
    return Runner(ficha, [_pair("dane_ipc_annual_national", dane_annual, periods=dane_annual)])


def suameca_unemployment(ficha: Ficha, dane_geih: Values) -> Runner:
    return Runner(ficha, [_pair("dane_geih_unemployment_rate_national", dane_geih, periods=dane_geih)])


def dane_annual(ficha: Ficha, pubs: DanePublications, suameca: Values) -> Runner:
    annex_december = {p: v for p, v in pubs.variations.ytd.items() if p.month == 12 and p in pubs.bulletins}
    return Runner(
        ficha,
        [
            _pair("inflation_annual_national", suameca, periods=suameca, series_prevails=True),
            # Two DANE publications of the same December must agree (no producer rule here).
            _pair("dane_ipc_variations_annex", annex_december, periods=annex_december, tolerance=Decimal(0)),
        ],
    )


def dane_geih(ficha: Ficha, suameca: Values) -> Runner:
    return Runner(ficha, [_pair("unemployment_rate_national", suameca, periods=suameca, series_prevails=True)])


def inflation_monthly(ficha: Ficha, pubs: DanePublications) -> Runner:
    bulletins = {p: b.monthly for p, b in pubs.bulletins.items()}
    years = range(BULLETINS_FROM.year, pubs.variations.cut.year + 1)
    return Runner(ficha, [_pair("dane_ipc_bulletins", bulletins, years=years, tolerance=Decimal(0))])


def inflation_ytd(ficha: Ficha, pubs: DanePublications) -> Runner:
    # The series takes the annex value where both publish; the contrast is the bulletin.
    bulletins = {p: b.ytd for p, b in pubs.bulletins.items() if b.ytd is not None}
    both = set(bulletins) & set(pubs.variations.ytd)
    return Runner(ficha, [_pair("dane_ipc_bulletins", bulletins, periods=both, tolerance=Decimal(0))])
