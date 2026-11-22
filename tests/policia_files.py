"""Synthetic Policía workbooks with the layout of the real files (originals are not in git)."""

from __future__ import annotations

import io
import zipfile

import openpyxl

from app.connectors.policia import HOMICIDE_CRIME, HOMICIDE_ROW, MONTHS_ES

MONTH_NAMES = [m.capitalize() for m in MONTHS_ES]


def _save(workbook: openpyxl.Workbook) -> bytes:
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _sheet(title: str):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = title
    return workbook, sheet


def zipped(xlsx: bytes, name: str = "file.xlsx") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, xlsx)
    return buffer.getvalue()


def ultimo_mes(months: list[int], published: str = "20 octubre del 2026", total: int | None = None) -> bytes:
    workbook, sheet = _sheet("Cuadro 1")
    sheet.cell(3, 15, "ÍNDICE")
    sheet.cell(11, 1, "Delitos")
    sheet.cell(11, 2, "Total general delitos")
    sheet.cell(11, 3, "Mes")
    for i, name in enumerate(MONTH_NAMES):
        sheet.cell(12, 3 + i, name)
    sheet.cell(13, 1, "Total general")
    padded = months + [0] * (12 - len(months))
    for row, label in ((15, HOMICIDE_ROW), (16, "010321 - Homicidio por tránsito vehicular")):
        sheet.cell(row, 1, label)
        sheet.cell(row, 2, sum(padded) if total is None else total)
        for i, value in enumerate(padded):
            sheet.cell(row, 3 + i, value)
    sheet.cell(35, 1, "Fuente: POLICÍA NACIONAL")
    sheet.cell(36, 1, "p: cifra provisional ")
    sheet.cell(37, 1, f"Fecha de publicación: {published}")
    return _save(workbook)


def anual(totals: dict[int, int], provisional: int | None, published: str = "20 de octubre del 2026p") -> bytes:
    workbook, sheet = _sheet("Cuadro 1")
    sheet.cell(7, 1, "DELITO")
    sheet.cell(7, 2, "Año")
    sheet.cell(8, 2, "Total")
    years = list(range(2020, 2031))
    for i, year in enumerate(years):
        sheet.cell(8, 3 + i, f"{year}p" if year == provisional else year)
    sheet.cell(11, 1, HOMICIDE_ROW)
    sheet.cell(11, 2, sum(totals.values()))
    for i, year in enumerate(years):
        if year in totals:
            sheet.cell(11, 3 + i, totals[year])
    sheet.cell(25, 1, f"Fecha de publicación: {published}")
    return zipped(_save(workbook), "C.S_DELICTIVO_MENSUAL_ANUAL.xlsx")


def registro(year: int, homicides_by_month: dict[int, int], layout: str = "iccs", other_rows: int = 2) -> bytes:
    """layout: 'iccs' (2020-2025), 'no_iccs' (2023), 'isso' (2026 until Oct 2026) or 'isso_nov2026'
    (2026 since Nov 2026: DELITOS and a second MES column with the month name)."""
    workbook, sheet = _sheet("Hoja1" if not layout.startswith("isso") else str(year))
    sheet.cell(2, 1, "POLICÍA NACIONAL \nDIRECCIÓN DE INVESTIGACIÓN CRIMINAL E INTERPOL")
    date_name = "FECHA ISSO" if layout == "isso" else "FECHA HECHO"
    nov2026 = layout == "isso_nov2026"
    if nov2026:
        date_name = "FECHA ISSO"
    crime_name = "DELITO" if layout == "isso" else "DELITOS"
    header = ["ARMAS MEDIOS", "DEPARTAMENTO", "MUNICIPIO", date_name, "GENERO", "CODIGO DANE", crime_name, "MES", "CANTIDAD"]
    if layout != "no_iccs":
        header.append("ICCS")
    if nov2026:
        header.append("MES")
    sheet.append([])
    for _ in range(9):
        sheet.append([])
    sheet.append(header)

    def record(month: int, crime: str, iccs: str, quantity: int = 1):
        row = ["ARMA DE FUEGO", "ANTIOQUIA", "Medellín", f"{year}/{month:02d}/01", "MASCULINO", "05001", crime, f"{month:02d}", quantity]
        if layout != "no_iccs":
            row.append(iccs)
        if nov2026:
            row.append(MONTHS_ES[month - 1])
        sheet.append(row)

    for month, count in homicides_by_month.items():
        for _ in range(count):
            record(month, HOMICIDE_CRIME, "0101")
    for _ in range(other_rows):
        record(1, "(10321) Homicidio por tránsito vehicular (Homicidios en accidentes de tránsito)", "10321")
    if not nov2026:  # since Nov 2026 the 2026 file has no footer
        sheet.append([])
        sheet.append(["Fuente: POLICÍA NACIONAL"])
        sheet.append([f"Fecha de entrega: 20 de agosto de {year + 1 if year < 2026 else 2026}"])
    return _save(workbook) if layout != "no_iccs" else zipped(_save(workbook))


def legacy(year: int, homicides_by_month: dict[int, int], printed_total: int | None = None, date_format: str = "date") -> bytes:
    import datetime as dt

    workbook, sheet = _sheet("Sheet1")
    for text in (
        "MINISTERIO DE DEFENSA NACIONAL",
        "POLICÍA NACIONAL",
        "DIRECCIÓN DE INVESTIGACIÓN CRIMINAL E INTERPOL",
        "GRUPO DE INFORMACIÓN DE CRIMINALIDAD",
        "HOMICIDIO INTENCIONAL",
        f"PERÍODO DEL 01 DE ENERO AL 31 DE DICIEMBRE DEL {year}",
    ):
        sheet.append([text])
    sheet.append([])
    sheet.append([])
    sheet.append([])
    sheet.append(["ARMAS MEDIOS", "DEPARTAMENTO", "MUNICIPIO", "FECHA HECHO", "GENERO", "*AGRUPA EDAD PERSONA*", "CODIGO DANE", "CANTIDAD"])
    for month, count in homicides_by_month.items():
        day = dt.datetime(year, month, 3)
        value = day if date_format == "date" else day.strftime("%Y%m%d")
        sheet.append(["ARMA DE FUEGO", "ANTIOQUIA", "Bello", value, "MASCULINO", "ADULTOS", "05088000", count])
    total = sum(homicides_by_month.values()) if printed_total is None else printed_total
    sheet.append(["TOTAL", total])
    sheet.append(["FUENTE: DIJIN-POLICÍA NACIONAL. DATOS EXTRAIDOS EL DIA 12 DE ABRIL 2025."])
    return _save(workbook)
