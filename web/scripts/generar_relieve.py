"""Genera el puntillismo del relieve de Colombia para la pantalla de acceso.

Uso (desde la raíz del proyecto): uv run --no-project python web/scripts/generar_relieve.py
Salida: web/src/datos/relieve_colombia.json (se versiona; la app no descarga nada en tiempo de uso).

Fuentes, ambas de dominio público:
- Elevación: NOAA ETOPO1 (1 minuto de arco), servido por el ERDDAP de NOAA CoastWatch,
  muestreado cada 0,1°. https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.html
- Contorno: Natural Earth 1:50m, países (v5.1.2). https://www.naturalearthdata.com

Es una ilustración, no una cifra: no se muestra ningún valor. Aun así sale de datos reales.

Cómo se dibuja (puntillismo): cada celda de 0,1° dentro del país puede tener un punto, con un
pequeño desplazamiento aleatorio fijo (semilla) para que no se vea una cuadrícula. La probabilidad,
el tamaño y la luz del punto crecen con la altura; la luz además depende del sombreado del relieve
(luz rasante desde el noroeste), así las cordilleras, la Sierra Nevada y los valles se leen por
densidad y brillo, sin líneas.
"""

import csv
import io
import json
import math
import random
import urllib.request
from pathlib import Path

PASO = 0.1
SUR, NORTE, OESTE, ESTE = -4.4, 12.6, -79.2, -66.8
URL_ETOPO = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv?"
    f"altitude%5B({SUR}):6:({NORTE})%5D%5B({OESTE}):6:({ESTE})%5D"
)
URL_PAISES = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"
    "ne_50m_admin_0_countries.geojson"
)
SALIDA = Path(__file__).resolve().parents[1] / "src/datos/relieve_colombia.json"
ESCALA = 40  # unidades de dibujo por grado


def descargar(url: str) -> bytes:
    peticion = urllib.request.Request(url, headers={"User-Agent": "parrhesia-relieve/1.0"})
    with urllib.request.urlopen(peticion, timeout=120) as r:
        return r.read()


def contorno_colombia() -> list[list[tuple[float, float]]]:
    paises = json.loads(descargar(URL_PAISES))
    pais = next(f for f in paises["features"] if f["properties"]["ADMIN"] == "Colombia")
    g = pais["geometry"]
    poligonos = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    # Solo el territorio continental (el anillo más grande); las islas no se ven a esta escala.
    anillo = max((p[0] for p in poligonos), key=len)
    return [[(x, y) for x, y in anillo]]


def dentro(lon: float, lat: float, anillo: list[tuple[float, float]]) -> bool:
    adentro = False
    j = len(anillo) - 1
    for i, (xi, yi) in enumerate(anillo):
        xj, yj = anillo[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            adentro = not adentro
        j = i
    return adentro


def main() -> None:
    filas = list(csv.reader(io.StringIO(descargar(URL_ETOPO).decode())))[2:]
    altura = {(round(float(la), 1), round(float(lo), 1)): float(al) for la, lo, al in filas}
    anillo = contorno_colombia()[0]
    azar = random.Random(1810)  # semilla fija: el dibujo es siempre el mismo

    def alt(la: float, lo: float) -> float:
        return max(0.0, altura.get((round(la, 1), round(lo, 1)), 0.0))

    puntos = []
    la = SUR
    while la <= NORTE + 1e-9:
        lo = OESTE
        while lo <= ESTE + 1e-9:
            if dentro(lo, la, anillo):
                h = alt(la, lo)
                e = min(h, 5200) / 5200
                # Sombreado: pendiente con luz desde el noroeste (como en los mapas físicos).
                dx = (alt(la, lo + PASO) - alt(la, lo - PASO)) / (2 * 11100)
                dy = (alt(la + PASO, lo) - alt(la - PASO, lo)) / (2 * 11100)
                sombra = max(0.0, min(1.0, 0.55 + 0.9 * (-dx + dy) * 6))
                if azar.random() < 0.38 + 0.62 * e ** 0.55:
                    jx, jy = azar.uniform(-0.035, 0.035), azar.uniform(-0.035, 0.035)
                    x = round((lo + jx - OESTE) * ESCALA, 1)
                    y = round((NORTE - (la + jy)) * ESCALA, 1)
                    nivel = min(15, int(e ** 0.6 * 16))
                    luz = min(15, int((0.25 + 0.45 * e ** 0.5 + 0.3 * sombra) * 15.99))
                    puntos += [x, y, nivel, luz]
            lo = round(lo + PASO, 1)
        la = round(la + PASO, 1)

    datos = {
        "fuente": "Elevación: NOAA ETOPO1 (dominio público). Contorno: Natural Earth 1:50m (dominio público).",
        "ancho": round((ESTE - OESTE) * ESCALA),
        "alto": round((NORTE - SUR) * ESCALA),
        "puntos": puntos,  # grupos de 4: x, y, nivel de altura (0-15), luz (0-15)
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, separators=(",", ":")))
    print(f"{len(puntos) // 4} puntos · {SALIDA.stat().st_size // 1024} KB → {SALIDA}")


if __name__ == "__main__":
    main()
