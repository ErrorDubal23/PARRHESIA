"""Readers for Policía Nacional (DIJIN, SIEDCO) publications used as filter 5 contrast for homicides.

These are publications of the same system (SIEDCO) as the datos.gov.co dataset:
the contrast checks consistency between publications, it is not an independent
verification (the independent source is Medicina Legal).

Every reader checks the layout it relies on and raises ShapeError on any change.
Nothing is inferred: when a value cannot be established from the file itself,
the reader says so and the contrast stays pending.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

import openpyxl

from app.connectors.base import ShapeError
from app.domain import Period

HOMICIDE_ROW = "0101 - Homicidio intencional"
HOMICIDE_ICCS = "0101"
HOMICIDE_CRIME = "(0101) Homicidio intencional"
MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
# "extraída del SIEDCO el día 16 posterior al mes de corte" (policia.gov.co/estadistica-delictiva)
EXTRACTION_DAY = 16

_SPANISH_DATE = re.compile(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class UltimoMes:
    published_on: date
    total: int
    months: tuple[int, ...]  # 12 values as printed; unpublished months appear as 0


@dataclass(frozen=True)
class Anual:
    published_on: date
    totals: dict[int, int]
    provisional_years: frozenset[int]


@dataclass(frozen=True)
class MonthlyTotals:
    year: int
    values: dict[Period, int]
    note: str | None  # date line as printed, e.g. "Fecha de entrega: 20 de agosto de 2026"; None if the layout has no footer


@dataclass(frozen=True)
class Resolved:
    """Monthly values established from a file, or the reason they could not be."""

    values: dict[Period, int]
    pending_reason: str | None = None


def read_cuadros_ultimo_mes(content: bytes) -> UltimoMes:
    rows = _rows(content, "Cuadro 1")
    header = _find_row(rows, lambda r: [_norm(v) for v in r[2:14]] == list(MONTHS_ES), "month header")
    homicide = _find_row(rows, lambda r: r[0] == HOMICIDE_ROW, HOMICIDE_ROW)
    if header >= homicide:
        raise ShapeError("homicide row is above the month header")
    values = rows[homicide][1:14]
    if not all(_is_int(v) for v in values):
        raise ShapeError(f"non-integer values in homicide row: {values}")
    total, months = values[0], tuple(values[1:])
    return UltimoMes(published_on=_publication_date(rows), total=total, months=months)


def read_cuadros_anual(content: bytes) -> Anual:
    rows = _rows(_single_xlsx(content), "Cuadro 1")
    header_index = _find_row(rows, lambda r: r[1] == "Total" and _year_cell(r[2]) is not None, "year header")
    header = rows[header_index]
    years: dict[int, tuple[int, bool]] = {}
    for col, cell in enumerate(header[2:], start=2):
        parsed = _year_cell(cell)
        if parsed is None:
            if cell is not None:
                raise ShapeError(f"unexpected year header {cell!r}")
            continue
        years[col] = parsed
    homicide = rows[_find_row(rows, lambda r: r[0] == HOMICIDE_ROW, HOMICIDE_ROW)]
    totals, provisional = {}, set()
    for col, (year, is_provisional) in years.items():
        value = homicide[col] if col < len(homicide) else None
        if value is None or value == 0:
            continue  # future years are printed empty or as 0
        if not _is_int(value):
            raise ShapeError(f"non-integer annual total for {year}: {value!r}")
        totals[year] = value
        if is_provisional:
            provisional.add(year)
    if _is_int(homicide[1]) and homicide[1] != sum(totals.values()):
        raise ShapeError(f"annual totals do not add up to the printed total {homicide[1]}")
    return Anual(published_on=_publication_date(rows), totals=totals, provisional_years=frozenset(provisional))


def resolve_ultimo_mes(ultimo: UltimoMes, anual: Anual) -> Resolved:
    """Monthly values of the current year, without inferring the year.

    The year is the provisional year of the annual file whose total equals the
    último-mes total. The cut-off month follows the official day-16 rule.
    """
    if ultimo.published_on != anual.published_on:
        return Resolved({}, f"publication dates differ: {ultimo.published_on} vs {anual.published_on}")
    candidates = [y for y in anual.provisional_years if anual.totals[y] == ultimo.total]
    if len(candidates) != 1:
        return Resolved({}, f"último-mes total {ultimo.total} matches provisional years {sorted(candidates)}")
    year = candidates[0]
    if ultimo.published_on.day < EXTRACTION_DAY:
        return Resolved({}, f"published on day {ultimo.published_on.day}, before the day-{EXTRACTION_DAY} extraction")
    cut = Period(ultimo.published_on.year, ultimo.published_on.month).previous()
    if cut.year != year:
        return Resolved({}, f"cut-off month {cut} is not in year {year}")
    published, unpublished = ultimo.months[: cut.month], ultimo.months[cut.month :]
    if any(unpublished):
        return Resolved({}, f"months after the cut-off {cut} are not zero: {unpublished}")
    if sum(published) != ultimo.total:
        return Resolved({}, f"months up to {cut} add up to {sum(published)}, not {ultimo.total}")
    return Resolved({Period(year, m): v for m, v in enumerate(published, start=1)})


@dataclass(frozen=True)
class RegistroLayout:
    date: str
    crime: str
    iccs: str | None
    footer: bool = True  # "Fecha de entrega" line after the records


# Layouts seen on 25 Oct 2026. Any other header stops the read (filter 2).
REGISTRO_LAYOUTS = (
    RegistroLayout(date="FECHA HECHO", crime="DELITOS", iccs="ICCS"),  # 2020-2022, 2024, 2025
    RegistroLayout(date="FECHA HECHO", crime="DELITOS", iccs=None),  # 2023
    RegistroLayout(date="FECHA ISSO", crime="DELITO", iccs="ICCS"),  # 2026 (until Oct 2026)
    # 2026 since Nov 2026: DELITOS again, and a second MES column with the month name ("enero").
    # It also has no footer: the delivery date is not in the file (it was only kept as a note).
    RegistroLayout(date="FECHA ISSO", crime="DELITOS", iccs="ICCS", footer=False),
)


def _registro_layout(header: tuple) -> RegistroLayout | None:
    present = {v for v in header if isinstance(v, str)}
    for layout in REGISTRO_LAYOUTS:
        wanted = {layout.date, layout.crime, "MES", "CANTIDAD"} | ({layout.iccs} if layout.iccs else set())
        other_iccs = layout.iccs is None and "ICCS" in present
        if wanted <= present and not other_iccs:
            return layout
    return None


def read_registro(content: bytes, year: int) -> MonthlyTotals:
    """Record-level file of one year (2020 onwards): intentional homicide by month.

    A record is an intentional homicide when its crime label is HOMICIDE_CRIME;
    when the file has an ICCS column, it must say 0101 for exactly those records.
    """
    rows = _rows(_single_xlsx(content), None)
    header_index = _find_row(rows, lambda r: _registro_layout(r) is not None, "record header")
    layout = _registro_layout(rows[header_index])
    header = rows[header_index]
    col = {name: header.index(name) for name in (layout.date, layout.crime, "MES", "CANTIDAD")}
    iccs_col = header.index(layout.iccs) if layout.iccs else None
    # Since Nov 2026 the 2026 file has two MES columns: the number ("01") and the name ("enero"). Nothing is
    # chosen blindly: the first must be the number, and every record must agree in both.
    mes_cols = [i for i, name in enumerate(header) if name == "MES"]
    if len(mes_cols) > 2:
        raise ShapeError(f"{len(mes_cols)} MES columns")
    mes_name_col = mes_cols[1] if len(mes_cols) == 2 else None
    counts: Counter[Period] = Counter()
    trailing = []
    for row in rows[header_index + 1 :]:
        if row[col[layout.date]] is None:
            trailing.append(row)
            continue
        if trailing:
            raise ShapeError("data rows after the footer")
        is_homicide = row[col[layout.crime]] == HOMICIDE_CRIME
        if iccs_col is not None and (row[iccs_col] == HOMICIDE_ICCS) != is_homicide:
            raise ShapeError(f"ICCS {row[iccs_col]!r} disagrees with crime {row[col[layout.crime]]!r}")
        if not is_homicide:
            continue
        day = _record_date(row[col[layout.date]])
        if day.year != year:
            raise ShapeError(f"record dated {day} in the {year} file")
        if row[col["MES"]] != f"{day.month:02d}":
            raise ShapeError(f"MES {row[col['MES']]!r} does not match {layout.date} {day}")
        if mes_name_col is not None and str(row[mes_name_col]).strip().lower() != MONTHS_ES[day.month - 1]:
            raise ShapeError(f"second MES {row[mes_name_col]!r} does not match {layout.date} {day}")
        quantity = row[col["CANTIDAD"]]
        if not _is_int(quantity) or quantity <= 0:
            raise ShapeError(f"invalid CANTIDAD {quantity!r}")
        counts[Period(year, day.month)] += quantity
    has_footer = any(v not in (None, "") for r in trailing for v in r)
    note = _footer_line(trailing, "Fecha de entrega") if layout.footer or has_footer else None
    return MonthlyTotals(year=year, values=dict(counts), note=note)


def read_legacy(content: bytes, year: int) -> MonthlyTotals:
    """Legacy one-year intentional homicide file (estadistica-delictiva-old)."""
    rows = _rows(content, None)
    title = [str(v) for r in rows[:12] for v in r if isinstance(v, str)]
    if "HOMICIDIO INTENCIONAL" not in title:
        raise ShapeError("not an intentional homicide file")
    period_line = f"PERÍODO DEL 01 DE ENERO AL 31 DE DICIEMBRE DEL {year}"
    if period_line not in title:
        raise ShapeError(f"missing period line {period_line!r}")
    header_index = _find_row(rows, lambda r: "FECHA HECHO" in r and "CANTIDAD" in r, "record header")
    date_col, qty_col = rows[header_index].index("FECHA HECHO"), rows[header_index].index("CANTIDAD")
    counts: Counter[Period] = Counter()
    printed_total = None
    footer = []
    for row in rows[header_index + 1 :]:
        if row[date_col] is None:
            if row[0] == "TOTAL":
                printed_total = row[1] if _is_int(row[1]) else next((v for v in row[1:] if _is_int(v)), None)
            footer.append(row)
            continue
        day = _record_date(row[date_col])
        if day.year != year:
            raise ShapeError(f"record dated {day} in the {year} file")
        quantity = row[qty_col]
        if not _is_int(quantity) or quantity <= 0:
            raise ShapeError(f"invalid CANTIDAD {quantity!r}")
        counts[Period(year, day.month)] += quantity
    if printed_total is None or printed_total != sum(counts.values()):
        raise ShapeError(f"records add up to {sum(counts.values())}, printed TOTAL is {printed_total}")
    note = _footer_line(footer, "FUENTE")
    return MonthlyTotals(year=year, values=dict(counts), note=note)


# Helpers


def _single_xlsx(content: bytes) -> bytes:
    """Some files are published as a .zip holding one .xlsx; an .xlsx is itself a zip."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if "[Content_Types].xml" in names:
            return content
        workbooks = [n for n in names if n.lower().endswith(".xlsx")]
        if len(workbooks) != 1 or len(names) != 1:
            raise ShapeError(f"expected one .xlsx in the zip, found {names}")
        return archive.read(workbooks[0])


def _rows(content: bytes, sheet: str | None) -> list[tuple]:
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ShapeError(f"not a readable workbook: {exc}") from exc
    try:
        if sheet is None:
            if len(workbook.sheetnames) != 1:
                raise ShapeError(f"expected one sheet, found {workbook.sheetnames}")
            sheet = workbook.sheetnames[0]
        if sheet not in workbook.sheetnames:
            raise ShapeError(f"missing sheet {sheet!r}")
        width = 16
        return [tuple(row) + (None,) * (width - len(row)) for row in workbook[sheet].iter_rows(values_only=True)]
    finally:
        workbook.close()


def _find_row(rows: list[tuple], predicate, what: str) -> int:
    matches = [i for i, r in enumerate(rows) if predicate(r)]
    if len(matches) != 1:
        raise ShapeError(f"expected one {what} row, found {len(matches)}")
    return matches[0]


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return text.strip().lower()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _year_cell(value: object) -> tuple[int, bool] | None:
    if _is_int(value) and 1900 < value < 2100:
        return value, False
    if isinstance(value, str) and re.fullmatch(r"\d{4}p", value.strip()):
        return int(value.strip()[:4]), True
    return None


def _publication_date(rows: list[tuple]) -> date:
    lines = [v for r in rows for v in r if isinstance(v, str) and v.strip().startswith("Fecha de publicación")]
    if len(lines) != 1:
        raise ShapeError(f"expected one 'Fecha de publicación' line, found {len(lines)}")
    return spanish_date(lines[0])


def spanish_date(text: str) -> date:
    match = _SPANISH_DATE.search(text)
    if not match or _norm(match.group(2)) not in MONTHS_ES:
        raise ShapeError(f"unreadable date in {text!r}")
    return date(int(match.group(3)), MONTHS_ES.index(_norm(match.group(2))) + 1, int(match.group(1)))


def _record_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for pattern in ("%Y/%m/%d", "%Y%m%d", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), pattern).date()
            except ValueError:
                pass
    raise ShapeError(f"unreadable FECHA HECHO {value!r}")


def _footer_line(rows: list[tuple], prefix: str) -> str:
    lines = [v.strip() for r in rows for v in r if isinstance(v, str) and v.strip().upper().startswith(prefix.upper())]
    if len(lines) != 1:
        raise ShapeError(f"expected one footer line starting with {prefix!r}, found {len(lines)}")
    return re.sub(r"\s+", " ", lines[0])
