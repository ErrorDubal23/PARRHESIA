"""DANE test files: small real fixtures (public data, under 1 MB) and a synthetic GEIH annex.

The real GEIH annex is 3.7 MB, so it is rebuilt here as a minimal .xlsx whose
numbers are written as text in the XML, like the real file, to check that every
digit is kept.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

FIXTURES = Path(__file__).parent / "fixtures" / "dane"
VARIATIONS_SEP_2026 = FIXTURES / "anex-IPC-Variacion-sep2026.xls"
BULLETIN_SEP_2026 = FIXTURES / "bol-IPC-sep2026.pdf"
BULLETIN_JAN_2024 = FIXTURES / "bol-IPC-ene2024.pdf"
BULLETIN_AUG_2024 = FIXTURES / "bol-IPC-ago2024.pdf"

GEIH_MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _col(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def xlsx(sheet_name: str, rows: dict[int, dict[int, str | float | int]]) -> bytes:
    """A minimal .xlsx: strings inline, numbers written exactly as given (str keeps all digits)."""
    sheet_rows = []
    for r in sorted(rows):
        cells = []
        for c, value in sorted(rows[r].items()):
            ref = f"{_col(c)}{r}"
            if isinstance(value, str) and not _is_number(value):
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{main}" xmlns:r="{rel}">'
            f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{main}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def geih_annex(
    national: dict[tuple[int, int], str],
    cabeceras: dict[tuple[int, int], str] | None = None,
    last_year: int = 2026,
    month_labels: list[str] | None = None,
    updated: str = "Actualizado el 30 de septiembre de 2026",
    sections: tuple[str, str] = ("Total Nacional", "Total Cabeceras"),
) -> bytes:
    """GEIH 'Total nacional' sheet with the real layout: two sections, years and months headers.

    The first section gets the national values, the second the cabeceras values.
    """
    labels = month_labels or GEIH_MONTHS
    rows: dict[int, dict[int, str | float | int]] = {5: {0: "Gran Encuesta Integrada de Hogares - GEIH"}}

    def section(start: int, title: str, values: dict[tuple[int, int], str]):
        rows[start] = {0: title}
        rows[start + 1] = {0: f"Serie mensual 2001 - {last_year}"}
        years = {0: "Concepto"}
        months = {}
        td = {0: "Tasa de Desocupación (TD)"}
        col = 1
        for year in range(2001, last_year + 1):
            years[col] = year
            for m in range(12):
                months[col] = labels[m]
                if (year, m + 1) in values:
                    td[col] = values[(year, m + 1)]
                col += 1
        rows[start + 2] = years
        rows[start + 3] = months
        rows[start + 4] = {0: "Tasa Global de Participación (TGP)", 1: 69}
        rows[start + 5] = td

    section(10, sections[0], national)
    section(32, sections[1], cabeceras or {k: "1.5" for k in national})
    rows[60] = {0: updated}
    return xlsx("Total nacional", rows)


def full_series(last: tuple[int, int], value: str = "10.123456789012345678") -> dict[tuple[int, int], str]:
    return {(y, m): value for y in range(2001, last[0] + 1) for m in range(1, 13) if (y, m) <= last}
VARIATIONS_OCT_2026 = FIXTURES / "anex-IPC-Variacion-oct2026.xlsx"  # desde oct 2026 el anexo es .xlsx
