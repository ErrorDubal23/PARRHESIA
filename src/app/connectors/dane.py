"""Readers for DANE publications: IPC variations annex (.xls until Sep 2026, .xlsx since Oct 2026), GEIH annex (.xlsx) and IPC bulletins (.pdf).

Every value is kept as an exact decimal, never as a float:
- .xlsx: the number as written in the cell's XML;
- .xls (binary format): the shortest decimal that reproduces the stored double;
- .pdf: the number as written in the text.
Every reader checks the layout it relies on and raises ShapeError on any change.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import xlrd
from pdfminer.high_level import extract_text

from app.connectors.base import ShapeError
from app.connectors.policia import MONTHS_ES, spanish_date
from app.domain import Period

MONTHS_TITLE = tuple(m.capitalize() for m in MONTHS_ES)
GEIH_MONTHS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
GEIH_SHEET = "Total nacional"
GEIH_SECTION = "Total Nacional"  # distinct from "Total Cabeceras" (second section)
GEIH_SECTION_POSITION = 1
GEIH_ROW = "Tasa de Desocupación (TD)"


@dataclass(frozen=True)
class VariationsAnnex:
    updated_on: date
    cut: Period  # "AÑO 2026, MES 9"
    monthly: dict[Period, Decimal]
    ytd: dict[Period, Decimal]  # December of every complete year, and the cut month


@dataclass(frozen=True)
class GeihAnnex:
    updated_on: date
    unemployment: dict[Period, Decimal]


@dataclass(frozen=True)
class Bulletin:
    period: Period
    annual: Decimal
    monthly: Decimal
    ytd: Decimal | None  # absent in January and December bulletins, and in 2024-08


# IPC variations annex (.xls until Sep 2026; .xlsx since Oct 2026, same layout)


def read_variations(content: bytes) -> VariationsAnnex:
    if not content:
        raise ShapeError("empty file")
    rows = _variations_xlsx_rows(content) if content[:4] == b"PK\x03\x04" else _variations_xls_rows(content)

    title = [r for r in rows if isinstance(r[0], str) and r[0].startswith("Variaciones porcentuales")]
    if len(title) != 1:
        raise ShapeError("missing 'Variaciones porcentuales' title")
    cut_rows = [m for r in rows if isinstance(r[0], str) for m in [re.fullmatch(r"AÑO (\d{4}), MES (\d{1,2})", r[0].strip())] if m]
    if len(cut_rows) != 1:
        raise ShapeError("missing 'AÑO <year>, MES <month>' line")
    cut = Period(int(cut_rows[0].group(1)), int(cut_rows[0].group(2)))

    header_index = _one(rows, lambda r: r[0] == "Mes", "'Mes' header")
    years = [_year(v) for v in rows[header_index][1:]]
    if years != list(range(years[0], years[0] + len(years))) or years[-1] != cut.year:
        raise ShapeError(f"year columns are not consecutive up to {cut.year}: {years}")
    month_rows = rows[header_index + 1 : header_index + 13]
    if [r[0] for r in month_rows] != list(MONTHS_TITLE):
        raise ShapeError(f"month rows changed: {[r[0] for r in month_rows]}")
    ytd_row = rows[header_index + 13]
    if ytd_row[0] != "En año corrido":
        raise ShapeError(f"expected 'En año corrido' after the months, found {ytd_row[0]!r}")

    monthly: dict[Period, Decimal] = {}
    for col, year in enumerate(years, start=1):
        last_month = 12 if year < cut.year else cut.month
        for month, row in enumerate(month_rows, start=1):
            cell = row[col]
            if month <= last_month:
                monthly[Period(year, month)] = _xls_decimal(cell, f"{year}-{month:02d}")
            elif cell != "":
                raise ShapeError(f"value after the cut-off {cut}: {year}-{month:02d}")
    ytd = {
        (Period(year, 12) if year < cut.year else cut): _xls_decimal(ytd_row[col], f"año corrido {year}")
        for col, year in enumerate(years, start=1)
    }
    updated = [r[0] for r in rows if isinstance(r[0], str) and r[0].strip().startswith("Actualizado el")]
    if len(updated) != 1:
        raise ShapeError("missing 'Actualizado el' line")
    return VariationsAnnex(spanish_date(updated[0]), cut, monthly, ytd)


def _variations_xls_rows(content: bytes) -> list[list]:
    try:
        book = xlrd.open_workbook(file_contents=content)
    except Exception as exc:  # xlrd raises several unrelated types on broken files
        raise ShapeError(f"not a readable .xls: {exc}") from exc
    if book.sheet_names() != ["VarNal"]:
        raise ShapeError(f"expected one sheet VarNal, found {book.sheet_names()}")
    sheet = book.sheet_by_index(0)
    return [sheet.row_values(r) for r in range(sheet.nrows)]


def _variations_xlsx_rows(content: bytes) -> list[list]:
    """The .xlsx annex in the shape xlrd gives the .xls: numbers as floats, empty cells as "".

    The DANE's .xlsx stores each number as the double written with 17 digits ("1.1100000000000001"),
    so the rule is the same as for the .xls: the shortest decimal that reproduces that double (1.11).
    """
    if _xlsx_sheet_names(content) != ["VarNal"]:
        raise ShapeError(f"expected one sheet VarNal, found {_xlsx_sheet_names(content)}")
    rows = _xlsx_rows(content, "VarNal", numbers_as_float=True)
    width = 1 + max((c for r in rows for c in r), default=0)
    return [[r.get(c, "") for c in range(width)] for r in rows]


def _year(value: object) -> int:
    if isinstance(value, float) and value.is_integer() and 1900 < value < 2100:
        return int(value)
    raise ShapeError(f"unexpected year header {value!r}")


def _xls_decimal(value: object, where: str) -> Decimal:
    if not isinstance(value, float):
        raise ShapeError(f"{where}: not a number: {value!r}")
    return Decimal(repr(value))  # shortest decimal reproducing the stored double


# GEIH annex (.xlsx), read from the XML so numbers keep their written digits

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def read_geih(content: bytes) -> GeihAnnex:
    rows = _xlsx_rows(content, GEIH_SHEET)
    # The sheet has one section per domain ("Total Nacional", then "Total
    # Cabeceras"), each with its title, header and the same row labels. The
    # series is national: read only the "Total Nacional" section.
    # A section is a heading followed by its "Serie mensual 2001 - <year>" title.
    sections = [
        i for i in range(len(rows) - 1)
        if rows[i].get(0, "").strip() and rows[i + 1].get(0, "").startswith("Serie mensual 2001 - ")
    ]
    names = [rows[i][0].strip() for i in sections]
    if names.count(GEIH_SECTION) != 1:
        raise ShapeError(f"expected one {GEIH_SECTION!r} section, found sections {names}")
    if names.index(GEIH_SECTION) + 1 != GEIH_SECTION_POSITION:
        raise ShapeError(f"{GEIH_SECTION!r} is section {names.index(GEIH_SECTION) + 1}, expected {GEIH_SECTION_POSITION}: {names}")
    start = sections[names.index(GEIH_SECTION)]
    later = [i for i in sections if i > start]
    end = later[0] if later else len(rows)
    section = range(start, end)
    header = _one_in(rows, section, lambda r: r.get(0, "").strip() == "Concepto", "'Concepto' header")
    target = _one_in(rows, section, lambda r: r.get(0, "").strip() == GEIH_ROW, GEIH_ROW)
    years_row, months_row = rows[header], rows[header + 1]

    values: dict[Period, Decimal] = {}
    year = None
    expected_month = 0
    for col in sorted(c for c in months_row if c > 0):
        if col in years_row:
            year = int(Decimal(years_row[col]))
        label = months_row[col].strip().rstrip("*")
        if year is None or label != GEIH_MONTHS[expected_month % 12]:
            raise ShapeError(f"unexpected month header {months_row[col]!r} in column {col}")
        if label == "Dic" and col + 1 in months_row and col + 1 not in years_row:
            raise ShapeError(f"missing year header after column {col}")
        expected_month += 1
        raw = rows[target].get(col)
        if raw is None or raw == "":
            continue
        try:
            values[Period(year, GEIH_MONTHS.index(label) + 1)] = Decimal(raw)
        except InvalidOperation as exc:
            raise ShapeError(f"{year}-{label}: not a number: {raw!r}") from exc

    periods = sorted(values)
    if not periods or periods[0] != Period(2001, 1):
        raise ShapeError("series does not start in 2001-01")
    for before, after in zip(periods, periods[1:]):
        if before.next() != after:
            raise ShapeError(f"missing value between {before} and {after}")
    updated = [v for r in rows for v in r.values() if isinstance(v, str) and v.strip().startswith("Actualizado el")]
    if len(updated) != 1:
        raise ShapeError("missing 'Actualizado el' line")
    return GeihAnnex(spanish_date(updated[0]), values)


def _xlsx_sheet_names(content: bytes) -> list[str]:
    try:
        workbook = ET.fromstring(zipfile.ZipFile(io.BytesIO(content)).read("xl/workbook.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ShapeError(f"not a readable .xlsx: {exc}") from exc
    return [s.get("name") for s in workbook.iterfind("m:sheets/m:sheet", _NS)]


def _xlsx_rows(content: bytes, sheet_name: str, *, numbers_as_float: bool = False) -> list[dict[int, str]]:
    """Rows of one sheet as {column index: text}, numbers as written in the XML (or as floats, if asked)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ShapeError(f"not a readable .xlsx: {exc}") from exc
    sheets = {s.get("name"): s.get(_REL) for s in workbook.iterfind("m:sheets/m:sheet", _NS)}
    if sheet_name not in sheets:
        raise ShapeError(f"missing sheet {sheet_name!r}")
    targets = {r.get("Id"): r.get("Target") for r in rels}
    target = targets[sheets[sheet_name]].lstrip("/")
    path = target if target.startswith("xl/") else f"xl/{target}"
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).iterfind("m:si", _NS):
            shared.append("".join(t.text or "" for t in item.iter(f"{{{_NS['m']}}}t")))

    rows: dict[int, dict[int, str]] = {}
    for row in ET.fromstring(archive.read(path)).iterfind("m:sheetData/m:row", _NS):
        cells: dict[int, str] = {}
        for cell in row.iterfind("m:c", _NS):
            col = _column_index(cell.get("r"))
            kind = cell.get("t")
            if kind == "inlineStr":
                cells[col] = "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t"))
                continue
            v = cell.find("m:v", _NS)
            if v is None or v.text is None:
                continue
            if kind == "s":
                cells[col] = shared[int(v.text)]
            elif numbers_as_float and kind in (None, "n"):
                try:
                    cells[col] = float(v.text)
                except ValueError as exc:
                    raise ShapeError(f"{cell.get('r')}: not a number: {v.text!r}") from exc
            else:
                cells[col] = v.text
        rows[int(row.get("r"))] = cells
    last = max(rows, default=0)
    return [rows.get(i, {}) for i in range(1, last + 1)]


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group(0)
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


# IPC bulletins (.pdf)

_MONTHS = "|".join(MONTHS_ES)
_RATE = re.compile(
    rf"(?:En|en) (?:el mes de )?({_MONTHS}) de (\d{{4}}),? el IPC registró una variación de (-?\d+,\d+) ?% "
    rf"en comparación con ({_MONTHS}) de (\d{{4}})",
    re.IGNORECASE,
)
_YTD = re.compile(rf"[Ee]n lo corrido del año,? \(enero ?- ?({_MONTHS})\),?[^.]*?promedio nacional \((-?\d+,\d+) ?%\)")


def read_bulletin(content: bytes) -> Bulletin:
    try:
        text = re.sub(r"\s+", " ", extract_text(io.BytesIO(content)))
    except Exception as exc:  # pdfminer raises several unrelated types on broken files
        raise ShapeError(f"not a readable PDF: {exc}") from exc
    annual, monthly = set(), set()
    for m in _RATE.finditer(text):
        period = Period(int(m.group(2)), MONTHS_ES.index(m.group(1).lower()) + 1)
        compared = Period(int(m.group(5)), MONTHS_ES.index(m.group(4).lower()) + 1)
        value = Decimal(m.group(3).replace(",", "."))
        if compared == period.year_ago():
            annual.add((period, value))
        elif compared == period.previous():
            monthly.add((period, value))
        else:
            raise ShapeError(f"variation for {period} compared with {compared}")
    if len(annual) != 1 or len(monthly) != 1:
        raise ShapeError(f"expected one annual and one monthly variation, found {sorted(annual)} / {sorted(monthly)}")
    [(period, annual_value)] = annual
    [(monthly_period, monthly_value)] = monthly
    if monthly_period != period:
        raise ShapeError(f"annual variation for {period} but monthly for {monthly_period}")
    ytd_values = {Decimal(v.replace(",", ".")) for month, v in _YTD.findall(text) if month.lower() == MONTHS_ES[period.month - 1]}
    if len(ytd_values) > 1:
        raise ShapeError(f"conflicting year-to-date values {sorted(ytd_values)}")
    return Bulletin(period, annual_value, monthly_value, ytd_values.pop() if ytd_values else None)


def _one(rows, predicate, what: str) -> int:
    return _one_in(rows, range(len(rows)), predicate, what)


def _one_in(rows, indices: range, predicate, what: str) -> int:
    matches = [i for i in indices if predicate(rows[i])]
    if len(matches) != 1:
        raise ShapeError(f"expected one {what} row, found {len(matches)}")
    return matches[0]
