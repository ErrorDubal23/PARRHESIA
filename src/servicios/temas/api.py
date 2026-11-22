"""API del servicio de temas del día.

    uv run uvicorn servicios.temas.api:app --port 8004

Contrato: docs/diseno/07_apis.md, sección 4. Las conclusiones de las declaraciones
las da el servicio de verificación (GET /v1/textos/declaracion_reportada/{id}).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from servicios.comun import errores
from servicios.comun.configuracion import crear_pool
from servicios.comun.errores import ErrorApi
from servicios.comun.sesion import Usuario, usuario_actual

recursos: dict = {}


@asynccontextmanager
async def ciclo_de_vida(aplicacion: FastAPI):
    recursos["pool"] = crear_pool("PG_URL_TEMAS")
    aplicacion.state.pool = recursos["pool"]   # la usa la sesión para revisar en la base que siga vigente
    yield
    recursos["pool"].close()


app = FastAPI(title="Servicio de temas del día", version="1", lifespan=ciclo_de_vida)
errores.instalar(app)


def conexion():
    with recursos["pool"].connection() as conn:
        yield conn


class Medio(BaseModel):
    url_sitio: str = Field(pattern=r"^https?://")
    canal: str = Field(pattern=r"^(rss|gdelt)$")
    url_canal: str = Field(pattern=r"^https?://")
    habilitado: bool = True


@app.get("/salud")
def salud(conn=Depends(conexion)):
    conn.execute("SELECT 1")
    return {"estado": "ok", "base": "ok"}


@app.get("/v1/temas")
def temas(conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute("SELECT tema_id::text AS id, posicion, titulo, etiqueta, total_medios, total_articulos,"
                            " ventana_inicio, ventana_fin FROM temas.temas_actuales()").fetchall()
        for f in filas:
            _cobertura(cur, f)
        registrados = [m["nombre"] for m in cur.execute(
            "SELECT nombre FROM temas.medio WHERE habilitado ORDER BY nombre").fetchall()]
    # Los medios registrados permiten dibujar la huella de cobertura (cuáles cubren y cuáles no).
    return {"temas": filas, "medios_registrados": registrados}


def _cobertura(cur, tema: dict) -> None:
    """Agrega a un tema sus medios (en el orden en que lo publicaron), su actividad por tramo de 3 horas
    y su imagen con el crédito del fotógrafo (o None)."""
    imagen = cur.execute("SELECT * FROM temas.imagen_vigente(%s)", (tema["id"],)).fetchone()
    tema["imagen"] = imagen if imagen and imagen["url"] else None
    tema["medios"] = cur.execute("SELECT medio, articulos, primero FROM temas.cobertura_tema(%s)", (tema["id"],)).fetchall()
    tema["actividad"] = [f["articulos"] for f in cur.execute(
        "SELECT articulos FROM temas.actividad_tema(%s, 8)", (tema["id"],)).fetchall()]


@app.get("/v1/temas/{tema_id}")
def tema(tema_id: UUID, conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        datos = cur.execute("SELECT id::text, titulo, etiqueta, total_medios, total_articulos, ventana_inicio, ventana_fin"
                            " FROM temas.tema WHERE id = %s", (tema_id,)).fetchone()
        if datos is None:
            raise ErrorApi("tema_inexistente", 404, "No existe ese tema.")
        _cobertura(cur, datos)
        filas = cur.execute("SELECT * FROM temas.pagina_tema(%s)", (tema_id,)).fetchall()
    articulos = [{"id": str(f["id"]), "medio": f["medio"], "titulo": f["titulo"], "url": f["url"],
                  "publicado_en": f["publicado_en"]} for f in filas if f["tipo"] == "articulo"]
    declaraciones = [{"id": str(f["id"]), "medio": f["medio"], "actor": f["actor"],
                      "figura_id": str(f["figura_id"]) if f["figura_id"] else None,
                      "texto_citado": f["texto_citado"], "titulo_articulo": f["titulo"], "url": f["url"],
                      "publicado_en": f["publicado_en"]} for f in filas if f["tipo"] == "declaracion"]
    return {**datos, "articulos": articulos, "declaraciones": declaraciones}


@app.get("/v1/medios")
def medios(conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        return {"medios": cur.execute("SELECT nombre, url_sitio, canal, url_canal, habilitado FROM temas.medio"
                                      " ORDER BY nombre").fetchall()}


@app.put("/v1/medios/{nombre}")
def configurar_medio(nombre: str, datos: Medio, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    if usuario.rol != "admin":
        raise ErrorApi("sin_permiso", 403)
    conn.execute("CALL temas.configurar_medio(%s, %s, %s, %s, %s)",
                 (nombre, datos.url_sitio, datos.canal, datos.url_canal, datos.habilitado))
    return {"nombre": nombre, **datos.model_dump()}
