"""API del servicio de datos oficiales.

    uv run uvicorn servicios.oficial.api:app --port 8005

Contrato: docs/diseno/07_apis.md, sección 5. Las cifras viajan como texto (decisión 24):
el valor es exactamente el publicado, sin redondear.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from servicios.comun import errores
from servicios.comun.configuracion import crear_pool
from servicios.comun.errores import ErrorApi
from servicios.comun.reglas_datos import es_provisional, fecha_fuente, hace_un_anio
from servicios.comun.sesion import Usuario, verificador

recursos: dict = {}


@asynccontextmanager
async def ciclo_de_vida(aplicacion: FastAPI):
    recursos["pool"] = crear_pool("PG_URL_OFICIAL")
    aplicacion.state.pool = recursos["pool"]   # la usa la sesión para revisar en la base que siga vigente
    yield
    recursos["pool"].close()


app = FastAPI(title="Servicio de datos oficiales", version="1", lifespan=ciclo_de_vida)
errores.instalar(app)


def conexion():
    with recursos["pool"].connection() as conn:
        yield conn


class Motivo(BaseModel):
    motivo: str = Field(min_length=3, max_length=1000)


def _texto(valor):
    return None if valor is None else str(valor)


@app.get("/salud")
def salud(conn=Depends(conexion)):
    conn.execute("SELECT 1")
    return {"estado": "ok", "base": "ok"}


def _resumen(cur, codigo: str, indicador: str, geografia: str) -> dict | None:
    """Lo que la app destaca de una serie, tal como se publicó (no se calcula nada): el último valor
    vigente con la fecha en que la fuente lo actualizó, el del periodo anterior y el del mismo periodo
    del año anterior, si el dato todavía es provisional, las notas vigentes y los últimos 25 valores."""
    filas = cur.execute(
        "SELECT observacion_id::text, periodo, valor FROM oficial.observaciones_vigentes(%s, '0000', '9999')"
        " WHERE territorio = %s ORDER BY periodo", (codigo, geografia)).fetchall()
    if not filas:
        return None
    ultimo = filas[-1]
    descarga = cur.execute(
        "SELECT d.actualizado_fuente, d.descargado_en FROM oficial.observacion o"
        " JOIN oficial.descarga d ON d.id = o.descarga_id WHERE o.id = %s", (ultimo["observacion_id"],)).fetchone()
    por_periodo = {f["periodo"]: f for f in filas}
    mensual = len(ultimo["periodo"]) == 7
    anio = por_periodo.get(hace_un_anio(ultimo["periodo"])) if mensual else None
    notas = cur.execute("SELECT tipo, estado FROM oficial.notas_en(%s, %s)", (codigo, ultimo["periodo"])).fetchall()
    punto = lambda f: {"periodo": f["periodo"], "valor": _texto(f["valor"])}  # noqa: E731
    return {
        "ultimo": {**punto(ultimo), "observacion_id": ultimo["observacion_id"],
                   "provisional": es_provisional(indicador, ultimo["periodo"]),
                   "actualizado_fuente": fecha_fuente(descarga["actualizado_fuente"]) if descarga else None,
                   "descargado_en": descarga["descargado_en"] if descarga else None},
        "anterior": punto(filas[-2]) if len(filas) > 1 else None,
        "hace_un_anio": punto(anio) if anio else None,
        "notas_vigentes": notas,
        "recientes": [punto(f) for f in filas[-25:]],
    }


@app.get("/v1/series")
def series(conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT s.codigo, s.nombre, i.codigo AS indicador, s.variante, s.etiqueta_unidad AS unidad, s.frecuencia,"
            " s.geografia, p.nombre AS productor, c.nombre AS canal,"
            " (SELECT max(o.periodo) FROM oficial.observacion o WHERE o.serie_id = s.id) AS ultimo_periodo"
            " , sp.otros_canales"
            " FROM oficial.series_publicas() sp JOIN oficial.serie s ON s.codigo = sp.codigo"
            " JOIN oficial.indicador i ON i.id = s.indicador_id"
            " JOIN oficial.fuente p ON p.id = s.fuente_productora_id JOIN oficial.fuente c ON c.id = s.fuente_canal_id"
            " ORDER BY i.codigo, s.codigo").fetchall()
        for f in filas:
            f["resumen"] = _resumen(cur, f["codigo"], f["indicador"], f["geografia"])
    return {"series": filas}


@app.get("/v1/series/{codigo}")
def serie(codigo: str, desde: str = "0000", hasta: str = "9999", conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        datos = cur.execute(
            "SELECT s.codigo, s.nombre, i.codigo AS indicador, s.variante, s.etiqueta_unidad AS unidad, s.frecuencia, s.geografia,"
            " p.nombre AS productor, c.nombre AS canal FROM oficial.serie s"
            " JOIN oficial.indicador i ON i.id = s.indicador_id"
            " JOIN oficial.fuente p ON p.id = s.fuente_productora_id JOIN oficial.fuente c ON c.id = s.fuente_canal_id"
            " WHERE s.codigo = %s AND s.aprobada", (codigo,)).fetchone()
        if datos is None:
            raise ErrorApi("serie_inexistente", 404, "No existe esa serie o no está aprobada.")
        valores = cur.execute("SELECT observacion_id::text, periodo, territorio, valor, marcas"
                              " FROM oficial.observaciones_vigentes(%s, %s, %s)", (codigo, desde, hasta)).fetchall()
        notas = cur.execute(
            "SELECT n.clave_nota, n.tipo, n.vigente_desde, n.vigente_hasta, n.estado, n.contenido FROM oficial.nota_serie n"
            " JOIN oficial.serie s ON s.id = n.serie_id WHERE s.codigo = %s ORDER BY n.vigente_desde NULLS FIRST", (codigo,)).fetchall()
        alertas = cur.execute("SELECT alerta_id::text, periodo, tipo, valor FROM oficial.alertas_abiertas(%s)", (codigo,)).fetchall()
        resumen = _resumen(cur, codigo, datos["indicador"], datos["geografia"])
    return {**datos, "resumen": resumen, "valores": [{**v, "valor": _texto(v["valor"])} for v in valores], "notas": notas,
            "alertas_abiertas": [{**a, "valor": _texto(a["valor"])} for a in alertas]}


@app.get("/v1/observaciones/{observacion_id}")
def trazabilidad(observacion_id: UUID, conn=Depends(conexion)):
    """De dónde salió un dato: descarga, archivos originales con su huella, contrastes y versiones del mismo periodo."""
    with conn.cursor(row_factory=dict_row) as cur:
        obs = cur.execute(
            "SELECT o.id::text, o.secuencia, s.codigo AS serie, o.periodo, o.territorio, o.valor, o.estado, o.estado_contraste,"
            " o.marcas, o.creado_en, o.descarga_id, o.serie_id FROM oficial.observacion o"
            " JOIN oficial.serie s ON s.id = o.serie_id WHERE o.id = %s", (observacion_id,)).fetchone()
        if obs is None:
            raise ErrorApi("observacion_inexistente", 404, "No existe ese dato.")
        descarga = cur.execute("SELECT canal, descargado_en, actualizado_fuente FROM oficial.descarga WHERE id = %s",
                               (obs["descarga_id"],)).fetchone()
        archivos = cur.execute("SELECT nombre, url, sha256 FROM oficial.archivo_original WHERE descarga_id = %s ORDER BY nombre",
                               (obs["descarga_id"],)).fetchall()
        contrastes = cur.execute(
            "SELECT fuente, nivel, periodo_comparado, valor_fuente, valor_serie, tolerancia, resultado, diferencia_conocida"
            " FROM oficial.comparacion_contraste WHERE observacion_id = %s ORDER BY fuente, nivel", (observacion_id,)).fetchall()
        versiones = cur.execute(
            "SELECT id::text, secuencia, valor, estado, creado_en FROM oficial.observacion"
            " WHERE serie_id = %s AND periodo = %s AND territorio = %s ORDER BY secuencia",
            (obs["serie_id"], obs["periodo"], obs["territorio"])).fetchall()
    for c in contrastes:
        for campo in ("valor_fuente", "valor_serie", "tolerancia"):
            c[campo] = _texto(c[campo])
    del obs["descarga_id"], obs["serie_id"]
    if descarga:  # la fecha como la escribió la fuente y, si se reconoce, en ISO
        descarga = {**descarga, "actualizado_fuente_texto": descarga["actualizado_fuente"],
                    "actualizado_fuente": fecha_fuente(descarga["actualizado_fuente"])}
    return {**obs, "valor": _texto(obs["valor"]), "descarga": descarga, "archivos_originales": archivos,
            "contrastes": contrastes, "versiones": [{**v, "valor": _texto(v["valor"])} for v in versiones]}


@app.get("/v1/alertas")
def alertas(estado: Literal["abierta", "cerrada"] = "abierta", _: Usuario = Depends(verificador), conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT a.id::text, s.codigo AS serie, a.periodo, a.territorio, a.tipo, a.valor, a.estado, a.creado_en"
            " FROM oficial.alerta a JOIN oficial.serie s ON s.id = a.serie_id WHERE a.estado = %s"
            " ORDER BY a.creado_en DESC LIMIT 200", (estado,)).fetchall()
    return {"alertas": [{**f, "valor": _texto(f["valor"])} for f in filas]}


@app.post("/v1/alertas/{alerta_id}/cierre")
def cerrar(alerta_id: UUID, datos: Motivo, usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    conn.execute("CALL oficial.cerrar_alerta(%s, %s, %s)", (alerta_id, usuario.nombre_usuario, datos.motivo))
    return {"alerta_id": str(alerta_id), "estado": "cerrada"}


@app.post("/v1/alertas/{alerta_id}/reapertura")
def reabrir(alerta_id: UUID, datos: Motivo, usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    conn.execute("CALL oficial.reabrir_alerta(%s, %s, %s)", (alerta_id, usuario.nombre_usuario, datos.motivo))
    return {"alerta_id": str(alerta_id), "estado": "abierta"}
