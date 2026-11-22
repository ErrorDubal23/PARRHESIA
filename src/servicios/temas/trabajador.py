"""Trabajador de temas del día.

    uv run python -m servicios.temas.trabajador

Cada 3 horas lee los medios. Para cada ventana (las 24 horas que terminan en el
último corte de 3 horas) pide a la IA que agrupe los títulos en temas; la base
cuenta los medios, descarta los grupos de menos de 3 y ordena. Luego, de cada
artículo de los temas, pide las declaraciones con cifras; la base rechaza las citas
que no estén textuales. Las declaraciones van al servicio de verificación por el outbox.
Retoma donde iba si se reinicia: encolar la misma entrada devuelve el mismo trabajo.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from servicios.comun.configuracion import conectar_postgres
from servicios.temas import imagenes
from servicios.temas import recolector

registro = logging.getLogger("temas")
VERSION_AGRUPACION = "agrupar_temas.v2"
VERSION_DECLARACIONES = "extraer_declaraciones.v1"
POR_MEDIO = 20      # titulares por medio en cada ventana: ningún medio domina la muestra, y cabe en una llamada


def ventana(ahora: datetime | None = None) -> tuple[datetime, datetime]:
    ahora = ahora or datetime.now(timezone.utc)
    fin = ahora.replace(hour=ahora.hour - ahora.hour % 3, minute=0, second=0, microsecond=0)
    return fin - timedelta(hours=24), fin


def registrar_medios(pg: psycopg.Connection) -> None:
    for nombre, sitio, canal in recolector.MEDIOS:
        pg.execute("CALL temas.configurar_medio(%s, %s, 'rss', %s, true)", (nombre, sitio, canal))


def recolectar(pg: psycopg.Connection, http: httpx.Client) -> int:
    nuevos = 0
    for medio_id, nombre, url in pg.execute("SELECT id, nombre, url_canal FROM temas.medio WHERE habilitado AND canal = 'rss'").fetchall():
        try:
            articulos = recolector.descargar(http, url)
        except Exception as exc:                       # un medio caído no detiene a los demás
            registro.warning("%s: no se pudo leer (%s)", nombre, type(exc).__name__)
            continue
        n = pg.execute("CALL temas.registrar_articulos(%s, %s, NULL)", (medio_id, Jsonb(articulos))).fetchone()[0]
        nuevos += n
        registro.info("%s: %d artículos, %d nuevos", nombre, len(articulos), n)
    return nuevos


def _encolar(pg, tipo, version, entrada) -> tuple[str, str, dict | None]:
    trabajo = pg.execute("CALL ia.encolar_trabajo(%s, %s, %s, NULL, NULL, NULL)", (tipo, version, Jsonb(entrada))).fetchone()[0]
    estado, salida = pg.execute("SELECT estado, salida FROM ia.resultado_trabajo(%s)", (trabajo,)).fetchone()
    return str(trabajo), estado, salida


def agrupar(pg: psycopg.Connection, desde: datetime, hasta: datetime) -> str:
    """Devuelve 'hecho', 'esperando' o 'sin_articulos'."""
    if pg.execute("SELECT 1 FROM temas.tema WHERE ventana_inicio = %s AND ventana_fin = %s LIMIT 1", (desde, hasta)).fetchone():
        return "hecho"
    with pg.cursor(row_factory=dict_row) as cur:
        articulos = cur.execute(
            "SELECT articulo_id::text AS id, medio, titulo FROM ("
            "  SELECT v.*, row_number() OVER (PARTITION BY medio ORDER BY publicado_en DESC) AS n"
            "  FROM temas.articulos_ventana(%s, %s) v) AS recientes"
            " WHERE n <= %s ORDER BY medio, publicado_en DESC", (desde, hasta, POR_MEDIO)).fetchall()
    if not articulos:
        return "sin_articulos"
    # Identificadores cortos para la IA (a1, a2…): un uuid gasta muchos tokens. Se traducen de vuelta aquí.
    cortos = {f"a{i}": a["id"] for i, a in enumerate(articulos, start=1)}
    entrada = {"articulos": [{"id": corto, "medio": a["medio"], "titulo": a["titulo"]}
                             for corto, a in zip(cortos, articulos)]}
    trabajo, estado, salida = _encolar(pg, "agrupar_temas", VERSION_AGRUPACION, entrada)
    if estado == "en_cola" or estado == "en_curso":
        return "esperando"
    grupos = [{**g, "articulos": [cortos[c] for c in g["articulos"]]} for g in salida["grupos"]] if estado == "terminado" else []
    guardados = pg.execute("CALL temas.registrar_temas(%s, %s, %s, %s, NULL)",
                           (desde, hasta, trabajo, Jsonb(grupos))).fetchone()[0]
    registro.info("ventana %s – %s: %d grupos propuestos, %d temas guardados", desde, hasta, len(grupos), guardados)
    return "hecho"


def extraer_declaraciones(pg: psycopg.Connection, desde: datetime, hasta: datetime) -> int:
    """Pide las declaraciones con cifras de cada artículo de los temas de la ventana. Devuelve cuántos faltan."""
    with pg.cursor(row_factory=dict_row) as cur:
        articulos = cur.execute(
            "SELECT DISTINCT a.id::text, a.titulo, a.resumen, a.texto FROM temas.tema t"
            " JOIN temas.tema_articulo ta ON ta.tema_id = t.id JOIN temas.articulo a ON a.id = ta.articulo_id"
            " WHERE t.ventana_inicio = %s AND t.ventana_fin = %s", (desde, hasta)).fetchall()
    faltan = 0
    for articulo in articulos:
        if not pg.execute("SELECT util.cifras_en_texto(%s || ' ' || coalesce(%s, ''))",
                          (articulo["titulo"], articulo["resumen"])).fetchone()[0]:
            continue                                   # sin cifras: no hay declaraciones que buscar
        trabajo, estado, salida = _encolar(pg, "extraer_declaraciones", VERSION_DECLARACIONES, {"articulo": articulo})
        if estado == "terminado" and salida["declaraciones"]:
            pg.execute("CALL temas.registrar_declaraciones(%s, %s, %s, NULL)",
                       (articulo["id"], trabajo, Jsonb(salida["declaraciones"])))
        elif estado in ("en_cola", "en_curso"):
            faltan += 1
    return faltan


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    proxima_recoleccion = 0.0
    with conectar_postgres("PG_URL_TEMAS") as pg, httpx.Client() as http:
        registrar_medios(pg)
        while True:
            if time.monotonic() >= proxima_recoleccion:
                recolectar(pg, http)
                proxima_recoleccion = time.monotonic() + 3 * 3600
            desde, hasta = ventana()
            if agrupar(pg, desde, hasta) == "hecho":
                extraer_declaraciones(pg, desde, hasta)
            imagenes.completar(pg, http)          # solo busca los temas actuales que aún no tienen imagen
            time.sleep(30)


if __name__ == "__main__":
    main()
