"""Readers for Policía contrast files, on synthetic workbooks with the real layouts."""

import io
from datetime import date

import openpyxl
import pytest

from app.connectors import policia
from app.connectors.base import ShapeError
from app.domain import Period
from tests import policia_files as files

SEPT_2026 = [1207, 1093, 1188, 1166, 1227, 1141, 1255, 1190, 967]  # real values, 20 Oct 2026
ANNUAL_2026 = {2020: 12009, 2021: 13685, 2022: 13536, 2023: 13555, 2024: 13496, 2025: 14037, 2026: 10434}


def _resolve(months=SEPT_2026, published="20 octubre del 2026", annual_published="20 de octubre del 2026p", totals=None, total=None):
    ultimo = policia.read_cuadros_ultimo_mes(files.ultimo_mes(months, published, total))
    anual = policia.read_cuadros_anual(files.anual(totals or ANNUAL_2026, 2026, annual_published))
    return policia.resolve_ultimo_mes(ultimo, anual)


# Cuadros de salida


def test_ultimo_mes_reads_total_months_and_date():
    ultimo = policia.read_cuadros_ultimo_mes(files.ultimo_mes(SEPT_2026))
    assert ultimo.total == 10434
    assert ultimo.months[:9] == tuple(SEPT_2026) and ultimo.months[9:] == (0, 0, 0)
    assert ultimo.published_on == date(2026, 10, 20)


def test_anual_reads_totals_and_provisional_year():
    anual = policia.read_cuadros_anual(files.anual(ANNUAL_2026, 2026))
    assert anual.totals == ANNUAL_2026
    assert anual.provisional_years == {2026}
    assert anual.published_on == date(2026, 10, 20)


def test_ultimo_mes_year_comes_from_the_annual_total():
    resolved = _resolve()
    assert resolved.pending_reason is None
    assert resolved.values[Period(2026, 9)] == 967
    assert Period(2026, 10) not in resolved.values  # unpublished months (printed as 0) are not read


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"annual_published": "19 de octubre del 2026p"}, "publication dates differ"),
        ({"totals": {**ANNUAL_2026, 2026: 10435}}, "matches provisional years []"),
        ({"published": "15 octubre del 2026", "annual_published": "15 de octubre del 2026p"}, "before the day-16"),
        ({"months": SEPT_2026 + [5], "total": 10434}, "not zero"),
        ({"total": 10433, "totals": {**ANNUAL_2026, 2026: 10433}}, "add up to"),
    ],
)
def test_ultimo_mes_stays_pending_when_the_year_or_cut_is_not_established(kwargs, reason):
    resolved = _resolve(**kwargs)
    assert resolved.values == {}
    assert reason in resolved.pending_reason


def _edit(content: bytes, sheet: str, cell: str, value) -> bytes:
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    workbook[sheet][cell] = value
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("cell", "value"),
    [("K12", "Setiembre"), ("A15", "0101 - Homicidio"), ("A37", "Publicado: 20 octubre del 2026")],
)
def test_ultimo_mes_layout_change_stops(cell, value):
    content = _edit(files.ultimo_mes(SEPT_2026), "Cuadro 1", cell, value)
    with pytest.raises(ShapeError):
        policia.read_cuadros_ultimo_mes(content)


# Record-level files


@pytest.mark.parametrize("layout", ["iccs", "no_iccs", "isso", "isso_nov2026"])
def test_registro_layouts(layout):
    totals = policia.read_registro(files.registro(2024, {1: 3, 10: 2}, layout=layout), 2024)
    assert totals.values == {Period(2024, 1): 3, Period(2024, 10): 2}
    if layout == "isso_nov2026":
        assert totals.note is None  # el archivo de noviembre de 2026 no trae pie
    else:
        assert totals.note.startswith("Fecha de entrega")


def test_registro_two_mes_columns_must_agree():
    """Formato de noviembre de 2026: la segunda columna MES ("enero") debe decir el mismo mes que la fecha."""
    content = files.registro(2024, {1: 1}, layout="isso_nov2026")
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    sheet = workbook.active
    fila = next(r for r in range(1, sheet.max_row + 1) if sheet.cell(r, 1).value == "ARMAS MEDIOS")
    sheet.cell(fila + 1, sheet.max_column, "febrero")   # primer registro, segunda columna MES
    out = io.BytesIO()
    workbook.save(out)
    with pytest.raises(ShapeError, match="second MES"):
        policia.read_registro(out.getvalue(), 2024)


def test_registro_rejects_records_of_another_year():
    content = files.registro(2024, {1: 1})
    with pytest.raises(ShapeError, match="in the 2023 file"):
        policia.read_registro(content, 2023)


# Legacy files


@pytest.mark.parametrize("date_format", ["date", "yyyymmdd"])
def test_legacy_reads_months_and_checks_printed_total(date_format):
    totals = policia.read_legacy(files.legacy(2015, {1: 1000, 2: 900}, date_format=date_format), 2015)
    assert totals.values == {Period(2015, 1): 1000, Period(2015, 2): 900}
    assert "12 DE ABRIL 2025" in totals.note


def test_legacy_total_mismatch_stops():
    with pytest.raises(ShapeError, match="printed TOTAL"):
        policia.read_legacy(files.legacy(2015, {1: 1000}, printed_total=999), 2015)


def test_legacy_wrong_year_stops():
    with pytest.raises(ShapeError, match="period line"):
        policia.read_legacy(files.legacy(2015, {1: 1000}), 2016)
