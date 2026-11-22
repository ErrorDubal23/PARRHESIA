"""DANE readers: variations annex and bulletins on real fixtures, GEIH annex on a synthetic file."""

from datetime import date
from decimal import Decimal

import pytest

from app.connectors import dane
from app.connectors.base import ShapeError
from app.domain import Period
from tests import dane_files as files


# Variations annex (.xls, real file of September 2026)


@pytest.fixture(scope="module")
def variations():
    return dane.read_variations(files.VARIATIONS_SEP_2026.read_bytes())


def test_variations_cut_and_update_date(variations):
    assert variations.cut == Period(2026, 9)
    assert variations.updated_on == date(2026, 10, 7)


def test_variations_monthly_values_are_exact_decimals(variations):
    assert len(variations.monthly) == 285  # 2003-01 .. 2026-09
    assert variations.monthly[Period(2026, 8)] == Decimal("0.39")
    assert str(variations.monthly[Period(2026, 8)]) == "0.39"
    assert all(isinstance(v, Decimal) for v in variations.monthly.values())


def test_variations_year_to_date_is_december_and_cut_month(variations):
    assert variations.ytd[Period(2026, 9)] == Decimal("5.74")
    assert variations.ytd[Period(2022, 12)] == Decimal("13.12")
    assert set(variations.ytd) == {Period(y, 12) for y in range(2003, 2026)} | {Period(2026, 9)}


def test_variations_xlsx_since_october_2026_reads_the_same_layout():
    """Desde octubre de 2026 el DANE publica el anexo en .xlsx; los números vienen como el doble escrito
    con 17 cifras (1.1100000000000001) y se leen con la misma regla que el .xls: el decimal más corto."""
    octubre = dane.read_variations(files.VARIATIONS_OCT_2026.read_bytes())
    septiembre = dane.read_variations(files.VARIATIONS_SEP_2026.read_bytes())
    assert octubre.cut == Period(2026, 10) and octubre.updated_on == date(2026, 11, 9)
    assert len(octubre.monthly) == 286 and all(isinstance(v, Decimal) for v in octubre.monthly.values())
    assert str(octubre.monthly[Period(2003, 2)]) == "1.11"
    # Lo ya publicado no cambia de un mes al otro (mismos valores hasta septiembre de 2026).
    assert {p: v for p, v in octubre.monthly.items() if p <= Period(2026, 9)} == septiembre.monthly
    assert {p: v for p, v in octubre.ytd.items() if p.year < 2026} == {p: v for p, v in septiembre.ytd.items() if p.year < 2026}
    assert set(octubre.ytd) == {Period(y, 12) for y in range(2003, 2026)} | {Period(2026, 10)}


@pytest.mark.parametrize("content", [b"", b"not an xls", b"PK\x03\x04 not a zip", files.BULLETIN_SEP_2026.read_bytes()[:2000]])
def test_variations_unreadable_file_stops(content):
    with pytest.raises(ShapeError):
        dane.read_variations(content)


# Bulletins (.pdf, real files)


def test_bulletin_with_year_to_date():
    b = dane.read_bulletin(files.BULLETIN_SEP_2026.read_bytes())
    assert (b.period, b.annual, b.monthly, b.ytd) == (Period(2026, 9), Decimal("6.29"), Decimal("0.37"), Decimal("5.74"))


@pytest.mark.parametrize(
    ("path", "period", "annual", "monthly"),
    [
        (files.BULLETIN_JAN_2024, Period(2024, 1), "8.35", "0.92"),  # January: no year-to-date section
        (files.BULLETIN_AUG_2024, Period(2024, 8), "6.12", "0.00"),  # year-to-date written without the total
    ],
)
def test_bulletins_without_year_to_date(path, period, annual, monthly):
    b = dane.read_bulletin(path.read_bytes())
    assert (b.period, b.annual, b.monthly, b.ytd) == (period, Decimal(annual), Decimal(monthly), None)


def test_unreadable_bulletin_stops():
    with pytest.raises(ShapeError):
        dane.read_bulletin(b"%PDF-1.4 broken")


# GEIH annex (.xlsx, synthetic with the real layout)


def test_geih_keeps_every_digit_and_reads_the_national_section():
    values = files.full_series((2026, 8))
    values[(2026, 8)] = "9.3636797215898682"
    annex = dane.read_geih(files.geih_annex(values))
    assert annex.unemployment[Period(2026, 8)] == Decimal("9.3636797215898682")
    assert str(annex.unemployment[Period(2026, 8)]) == "9.3636797215898682"  # not the float 9.363679721589868
    assert len(annex.unemployment) == 308
    assert annex.updated_on == date(2026, 9, 30)


def test_geih_starred_months_are_read():
    labels = list(files.GEIH_MONTHS)
    labels[2] = "Mar*"
    annex = dane.read_geih(files.geih_annex(files.full_series((2026, 8)), month_labels=labels))
    assert Period(2020, 3) in annex.unemployment


def test_geih_reads_the_national_section_not_cabeceras():
    national = files.full_series((2026, 8), value="9.1")
    cabeceras = files.full_series((2026, 8), value="11.9")
    annex = dane.read_geih(files.geih_annex(national, cabeceras))
    assert set(annex.unemployment.values()) == {Decimal("9.1")}


@pytest.mark.parametrize(
    "sections",
    [
        pytest.param(("Total Cabeceras", "Total Nacional"), id="national moved to second place"),
        pytest.param(("Total Nacional", "Total Nacional"), id="national twice"),
        pytest.param(("Total Cabeceras", "Total Urbano"), id="national missing"),
        pytest.param(("Nacional", "Total Cabeceras"), id="national renamed"),
    ],
)
def test_geih_section_missing_or_moved_stops(sections):
    with pytest.raises(ShapeError):
        dane.read_geih(files.geih_annex(files.full_series((2026, 8)), sections=sections))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: files.geih_annex(files.full_series((2026, 8)), month_labels=["Ene"] * 12), id="month header"),
        pytest.param(lambda: files.geih_annex({k: v for k, v in files.full_series((2026, 8)).items() if k != (2010, 5)}), id="gap"),
        pytest.param(lambda: files.geih_annex(files.full_series((2026, 8)), updated="Sin fecha"), id="no update date"),
        pytest.param(lambda: files.xlsx("Otra hoja", {1: {0: "x"}}), id="sheet missing"),
    ],
)
def test_geih_layout_changes_stop(build):
    with pytest.raises(ShapeError):
        dane.read_geih(build())
