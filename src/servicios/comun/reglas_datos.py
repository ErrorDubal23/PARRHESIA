"""Reglas sobre los datos oficiales que comparten varios servicios (una sola definición)."""

from __future__ import annotations

import re
from datetime import date

# Indicadores cuyos datos son provisionales hasta el 1 de abril del año siguiente (interpretación
# propia de la publicación de la Policía Nacional: los datos se consolidan en el primer trimestre).
PROVISIONALES = frozenset({"homicides", "theft", "extortion", "kidnapping"})


def es_provisional(indicador: str, periodo: str, hoy: date | None = None) -> bool:
    """True si el dato de ese periodo todavía puede cambiar."""
    hoy = hoy or date.today()
    return indicador in PROVISIONALES and hoy < date(int(periodo[:4]) + 1, 4, 1)


def hace_un_anio(periodo: str) -> str:
    """El mismo periodo un año antes: "2026-08" → "2025-08"; "2026" → "2025"."""
    return f"{int(periodo[:4]) - 1}{periodo[4:]}"


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def fecha_fuente(texto: str | None) -> str | None:
    """La fecha de actualización tal como la declara cada fuente ("2026-10-07", "2026-10-21T14:30:57+00:00",
    "08 de octubre de 2026") en formato ISO. Si no se reconoce, None: nunca se adivina una fecha."""
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except ValueError:
        pass
    m = re.fullmatch(r"\s*(\d{1,2}) de ([a-záéíóú]+) de (\d{4})\s*", texto.lower())
    if m and m.group(2) in MESES:
        return date(int(m.group(3)), MESES.index(m.group(2)) + 1, int(m.group(1))).isoformat()
    return None
