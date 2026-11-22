"""API del servicio de verificación.

    uv run uvicorn servicios.verificacion.api:app --port 8003

Contrato: docs/diseno/07_apis.md, sección 2. Las cifras viajan como texto (decisión 24).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from servicios.comun import errores
from servicios.comun.configuracion import crear_pool
from servicios.comun.errores import ErrorApi
from servicios.comun.sesion import Usuario, usuario_actual, usuario_opcional, verificador
from servicios.verificacion import enlaces

recursos: dict = {}


@asynccontextmanager
async def ciclo_de_vida(aplicacion: FastAPI):
    recursos["pool"] = crear_pool("PG_URL_VERIFICACION")
    aplicacion.state.pool = recursos["pool"]   # la usa la sesión para revisar en la base que siga vigente
    yield
    recursos["pool"].close()


app = FastAPI(title="Servicio de verificación", version="1", lifespan=ciclo_de_vida)
errores.instalar(app)


def conexion():
    with recursos["pool"].connection() as conn:
        yield conn


class PedidoResumen(BaseModel):
    publicaciones: list[UUID] = Field(default_factory=list, max_length=500)
    declaraciones: list[UUID] = Field(default_factory=list, max_length=500)
    declaraciones_reportadas: list[UUID] = Field(default_factory=list, max_length=500)


class Revision(BaseModel):
    decision: Literal["confirmada", "corregida"]
    motivo: str = Field(min_length=3, max_length=1000)


def _texto(valor) -> str | None:
    return None if valor is None else str(valor)


def _evidencia(conn, verificacion_id) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        roles = {str(r["observacion_id"]): r["rol"] for r in cur.execute(
            "SELECT observacion_id, rol FROM verificacion.evidencia WHERE verificacion_id = %s", (verificacion_id,))}
        if not roles:
            return []
        detalle = cur.execute("SELECT * FROM oficial.detalle_observaciones(%s)", (list(roles),)).fetchall()
    orden = {"citada": 0, "contraste": 1, "completa": 2}
    return sorted(({"observacion_id": str(d["observacion_id"]), "rol": roles[str(d["observacion_id"])],
                    "serie": d["codigo_serie"], "nombre_serie": d["nombre_serie"], "fuente": d["fuente"],
                    "periodo": d["periodo"], "valor": _texto(d["valor"])} for d in detalle),
                  key=lambda e: (orden[e["rol"]], e["periodo"]))


def _verificacion(conn, fila: dict) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        pruebas = cur.execute(
            "SELECT r.codigo_prueba AS codigo, p.nombre, r.resultado, r.detalle FROM verificacion.resultado_prueba r"
            " JOIN verificacion.prueba_robustez p ON p.codigo = r.codigo_prueba WHERE r.verificacion_id = %s"
            " ORDER BY r.codigo_prueba", (fila["id"],)).fetchall()
    return {"id": str(fila["id"]), "version": fila["version"], "conclusion": fila["conclusion"],
            # Solo se muestra una explicación que pasó el validador de cifras.
            "explicacion": fila["explicacion"] if fila["explicacion_validada"] else None,
            "serie": fila["codigo_serie"], "motor": fila["version_motor"], "creado_en": fila["creado_en"].isoformat(),
            "evidencia": _evidencia(conn, fila["id"]), "pruebas": pruebas}


@app.get("/salud")
def salud(conn=Depends(conexion)):
    conn.execute("SELECT 1")
    return {"estado": "ok", "base": "ok"}


@app.get("/v1/textos/{tipo}/{texto_id}")
def texto(tipo: Literal["publicacion", "declaracion", "declaracion_reportada", "fragmento_enlace"], texto_id: UUID,
          usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    # Lo publicado en una comunidad privada solo lo ven sus integrantes: tampoco su verificación (que cita el texto).
    if tipo == "publicacion" and not conn.execute("SELECT coalesce(social.puede_ver_publicacion(%s, %s), true)",
                                                  (texto_id, usuario.id if usuario else None)).fetchone()[0]:
        raise ErrorApi("publicacion_inexistente", 404, "No existe esa publicación.")
    return _estado_texto(conn, tipo, texto_id)


def _estado_texto(conn, tipo: str, texto_id) -> dict:
    columna = {"publicacion": "publicacion_id", "declaracion": "declaracion_id",
               "declaracion_reportada": "declaracion_reportada_id", "fragmento_enlace": "fragmento_enlace_id"}[tipo]
    with conn.cursor(row_factory=dict_row) as cur:
        afirmaciones = cur.execute(f"SELECT * FROM verificacion.afirmacion WHERE {columna} = %s ORDER BY posicion",
                                   (texto_id,)).fetchall()
        procesado = cur.execute("SELECT resultado FROM verificacion.procesamiento WHERE origen_tipo = %s AND origen_id = %s",
                                (tipo, texto_id)).fetchone()
        resultado = []
        for a in afirmaciones:
            vigente = cur.execute("SELECT * FROM verificacion.verificacion_vigente(%s)", (a["id"],)).fetchone()
            resultado.append({
                "id": str(a["id"]), "texto_citado": a["texto_citado"], "indicador": a["codigo_indicador"],
                "variante": a["variante"], "periodo": a["periodo_hasta"], "territorio": a["territorio"],
                "valor_dicho": _texto(a["valor_dicho"]), "direccion": a["direccion"], "estado": a["estado"],
                "consenso": a["consenso"], "verificacion": _verificacion(conn, vigente) if vigente else None,
                "guia": cur.execute("SELECT verificacion.guia_de(%s) AS g", (a["id"],)).fetchone()["g"]})
    if procesado is None:
        estado = "pendiente"
    elif procesado["resultado"] in ("sin_cifras", "sin_afirmaciones"):
        estado = "sin_cifras"
    elif procesado["resultado"] == "fallido" or any(a["estado"] == "requiere_revision" for a in resultado):
        estado = "requiere_revision"
    elif any(a["verificacion"] is None for a in resultado):
        estado = "pendiente"
    else:
        estado = "lista"
    return {"estado": estado, "afirmaciones": resultado}


@app.get("/v1/verificaciones/{verificacion_id}")
def ver_verificacion(verificacion_id: UUID, conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        fila = cur.execute("SELECT * FROM verificacion.verificacion WHERE id = %s", (verificacion_id,)).fetchone()
        if fila is None:
            raise ErrorApi("verificacion_inexistente", 404, "No existe esa verificación.")
        anteriores = cur.execute(
            "SELECT id::text, version, conclusion, creado_en FROM verificacion.verificacion"
            " WHERE afirmacion_id = %s AND version < %s ORDER BY version DESC", (fila["afirmacion_id"], fila["version"])).fetchall()
    return {**_verificacion(conn, fila), "versiones_anteriores": anteriores}


@app.post("/v1/resumen")
def resumen(pedido: PedidoResumen, conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute("SELECT * FROM verificacion.resumen_conclusiones(%s, %s, %s)",
                            ([str(i) for i in pedido.publicaciones], [str(i) for i in pedido.declaraciones],
                             [str(i) for i in pedido.declaraciones_reportadas])).fetchall()
    return {"conclusiones": filas, "total": sum(f["total"] for f in filas)}


@app.get("/v1/revisiones/pendientes")
def revisiones_pendientes(limite: int = Query(50, ge=1, le=200), _: Usuario = Depends(verificador), conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT id::text, texto_citado, codigo_indicador AS indicador, periodo_hasta AS periodo,"
            " valor_dicho::text, consenso, publicacion_id::text, declaracion_id::text, declaracion_reportada_id::text,"
            " creado_en FROM verificacion.afirmacion WHERE estado = 'requiere_revision' ORDER BY creado_en LIMIT %s",
            (limite,)).fetchall()
    return {"pendientes": filas}


@app.post("/v1/verificaciones/{verificacion_id}/revisiones", status_code=201)
def revisar(verificacion_id: UUID, datos: Revision, usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    conn.execute("CALL verificacion.registrar_revision(%s, %s, %s, %s)",
                 (verificacion_id, usuario.id, datos.decision, datos.motivo))
    return {"verificacion_id": str(verificacion_id), "decision": datos.decision}


# --- Análisis de enlaces externos (decisión 29) ----------------------------------------------------

class PedidoEnlace(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    texto: str | None = Field(default=None, min_length=20, max_length=20000)


def cliente_http():
    with httpx.Client() as http:
        yield http


def resolver_dns():
    return enlaces._resolver


@app.post("/v1/enlaces", status_code=201)
def analizar_enlace(pedido: PedidoEnlace, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion),
                    http=Depends(cliente_http), resolver=Depends(resolver_dns)):
    """Lee la página en memoria y guarda solo metadatos declarados y fragmentos con cifras; la verificación
    de cada fragmento sigue por la cola, como la de una publicación."""
    if (pedido.url is None) == (pedido.texto is None):
        raise ErrorApi("datos_invalidos", 422, "Pega un enlace o un texto (uno de los dos).")
    try:
        lectura = enlaces.leer_enlace(http, pedido.url, resolver) if pedido.url else enlaces.leer_texto(pedido.texto)
    except enlaces.EnlaceNoLeido as e:
        raise ErrorApi(e.codigo, 422, e.mensaje)
    enlace_id, reutilizado = conn.execute(
        "CALL verificacion.registrar_enlace(%s, %s, %s, %s, %s, %s, NULL, NULL)",
        (usuario.id, lectura.url, Jsonb(lectura.metadatos), lectura.fecha_referencia, lectura.huella,
         lectura.candidatos)).fetchone()
    return {"id": str(enlace_id), "reutilizado": reutilizado}


@app.get("/v1/enlaces/{enlace_id}")
def ver_enlace(enlace_id: UUID, conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        enlace = cur.execute(
            "SELECT id::text, url, dominio, titulo, sitio, autor_declarado, publicado_declarado, creado_en,"
            " verificacion.estado_enlace(id) AS estado FROM verificacion.enlace WHERE id = %s", (enlace_id,)).fetchone()
        if enlace is None:
            raise ErrorApi("enlace_inexistente", 404, "No existe ese análisis.")
        fragmentos = cur.execute("SELECT id, posicion, texto FROM verificacion.fragmento_enlace"
                                 " WHERE enlace_id = %s ORDER BY posicion", (enlace_id,)).fetchall()
    enlace["fragmentos"] = [{"id": str(f["id"]), "posicion": f["posicion"], "texto": f["texto"],
                             **_estado_texto(conn, "fragmento_enlace", f["id"])} for f in fragmentos]
    return enlace


@app.get("/v1/consejos/general/{referencia}")
def consejo_general(referencia: str, conn=Depends(conexion)):
    """Consejos generales de lectura (decisión 34), por ejemplo cómo leer un tema del día."""
    with conn.cursor(row_factory=dict_row) as cur:
        fila = cur.execute("SELECT para_entenderlo, pasos FROM verificacion.consejo WHERE origen = 'general' AND referencia = %s",
                           (referencia,)).fetchone()
    if fila is None:
        raise ErrorApi("consejo_inexistente", 404, "No existe ese consejo.")
    return fila
