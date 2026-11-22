"""Comunidades (decisión 28): endpoints del servicio social.

Toda escritura es un procedimiento de la base (migración 0018), que es donde viven los permisos de
cada papel, la regla de nunca quedarse sin administrador y la visibilidad de lo privado. Aquí solo se
reciben los datos, se llama al procedimiento y se arma la respuesta.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from servicios.comun.errores import ErrorApi
from servicios.comun.sesion import Usuario, usuario_actual, usuario_opcional
from servicios.social import fotos, lecturas
import httpx

from servicios.social.api import conexion, id_de, url_grafo

router = APIRouter(prefix="/v1")
PERMISOS = ("ver", "publicar", "moderar", "gestionar_integrantes", "configurar")


class NuevaComunidad(BaseModel):
    nombre: str = Field(min_length=3, max_length=60)
    descripcion: str = Field(min_length=10, max_length=500)
    reglas: str | None = Field(default=None, max_length=2000)
    privacidad: Literal["publica", "privada"] = "publica"


class CambioComunidad(BaseModel):
    nombre: str | None = Field(default=None, min_length=3, max_length=60)
    descripcion: str | None = Field(default=None, min_length=10, max_length=500)
    reglas: str | None = Field(default=None, max_length=2000)
    privacidad: Literal["publica", "privada"] | None = None


class Ingreso(BaseModel):
    mensaje: str | None = Field(default=None, max_length=280)


class Papel(BaseModel):
    papel: Literal["integrante", "moderador", "gestor", "administrador"]


class Expulsion(BaseModel):
    nombre_usuario: str
    motivo: str = Field(min_length=10, max_length=500)


class Resolucion(BaseModel):
    aceptar: bool
    motivo: str | None = Field(default=None, max_length=500)


class PublicacionEnComunidad(BaseModel):
    texto: str = Field(min_length=1, max_length=1500)
    figuras_ids: list[UUID] = Field(default_factory=list, max_length=10)


RESUMEN = """
SELECT c.id::text, c.nombre, c.descripcion, c.reglas, c.privacidad, c.imagen, c.total_integrantes, c.creada_en,
       u.nombre_usuario AS creada_por, social.mi_papel(c.id, %(yo)s::uuid) AS mi_papel,
       EXISTS (SELECT 1 FROM social.solicitud_ingreso s WHERE s.comunidad_id = c.id AND s.usuario_id = %(yo)s::uuid
               AND s.estado = 'pendiente') AS solicitud_pendiente,
       (SELECT count(*) FROM social.publicacion p WHERE p.comunidad_id = c.id AND p.estado = 'visible') AS total_publicaciones
FROM social.comunidad c JOIN social.usuario u ON u.id = c.creada_por
"""


def _comunidad(fila: dict) -> dict:
    return {**fila, "imagen": fotos.url(fila["imagen"]), "creada_en": fila["creada_en"].isoformat()}


def _exigir(conn, comunidad_id: UUID, usuario_id: str | None, accion: str) -> None:
    if conn.execute("SELECT 1 FROM social.comunidad WHERE id = %s", (comunidad_id,)).fetchone() is None:
        raise ErrorApi("comunidad_inexistente", 404, "No existe esa comunidad.")
    # social.puede da NULL a quien no es integrante: se trata como "no" (igual que en la base, con coalesce).
    if not conn.execute("SELECT coalesce(social.puede(%s, %s, %s), false)", (comunidad_id, usuario_id, accion)).fetchone()[0]:
        if accion == "ver":  # de una privada no se revela nada más allá de su ficha pública
            raise ErrorApi("comunidad_privada", 403, "El contenido de esta comunidad es solo para sus integrantes.")
        raise ErrorApi("sin_permiso", 403)


@router.get("/comunidades")
def listar(q: str | None = Query(default=None, max_length=60), mias: bool = False,
           usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    """Las comunidades se pueden encontrar aunque sean privadas (su ficha es pública; su contenido no)."""
    yo = usuario.id if usuario else None
    filtros, parametros = [], {"yo": yo}
    if q and q.strip():
        filtros.append("(lower(c.nombre) LIKE '%%' || lower(%(q)s) || '%%' OR util.similarity(lower(c.nombre), lower(%(q)s)) > 0.3)")
        parametros["q"] = q.strip()
    if mias and yo:
        filtros.append("social.mi_papel(c.id, %(yo)s::uuid) IS NOT NULL")
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(RESUMEN + (" WHERE " + " AND ".join(filtros) if filtros else "")
                            + " ORDER BY c.total_integrantes DESC, c.nombre LIMIT 60", parametros).fetchall()
    return {"comunidades": [_comunidad(f) for f in filas]}


@router.post("/comunidades", status_code=201)
def crear(datos: NuevaComunidad, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    comunidad_id = conn.execute("CALL social.crear_comunidad(%s, %s, %s, %s, %s, NULL)",
                                (usuario.id, datos.nombre, datos.descripcion, datos.reglas, datos.privacidad)).fetchone()[0]
    return ver(comunidad_id, usuario, conn)


def _del_grafo(ruta: str, clave: str) -> list[dict] | None:
    """Lo que calcula el grafo; None si no responde (la app sigue, solo sin sugerencias)."""
    try:
        respuesta = httpx.get(f"{url_grafo()}{ruta}", timeout=3)
        respuesta.raise_for_status()
        return respuesta.json()[clave]
    except httpx.HTTPError:
        return None


def _completar(conn, sugeridas: list[dict], yo: str | None) -> list[dict]:
    """Agrega a cada comunidad sugerida su ficha (desde PostgreSQL), en el orden del grafo."""
    if not sugeridas:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        fichas = {f["id"]: _comunidad(f) for f in cur.execute(
            RESUMEN + " WHERE c.id = ANY(%(ids)s::uuid[]) AND c.privacidad = 'publica'",
            {"yo": yo, "ids": [s["comunidad_id"] for s in sugeridas]}).fetchall()}
    return [{**fichas[s["comunidad_id"]], **{k: v for k, v in s.items() if k != "comunidad_id"}}
            for s in sugeridas if s["comunidad_id"] in fichas]


@router.get("/comunidades/recomendadas")
def recomendadas(usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """Comunidades públicas por temas que compartes, primero las de fuera de tu red. Sin inclinación política."""
    sugeridas = _del_grafo(f"/v1/comunidades/recomendadas/{usuario.id}", "comunidades")
    if sugeridas is None:
        return {"comunidades": [], "aviso": "Las sugerencias no están disponibles en este momento."}
    return {"comunidades": _completar(conn, sugeridas, usuario.id)}


@router.get("/comunidades/{comunidad_id}/relacionadas")
def relacionadas(comunidad_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    """Otras comunidades que discuten los mismos temas, primero las que comparten menos integrantes.
    Solo para comunidades públicas: de una privada no se revelan sus temas."""
    publica = conn.execute("SELECT privacidad = 'publica' FROM social.comunidad WHERE id = %s", (comunidad_id,)).fetchone()
    if publica is None:
        raise ErrorApi("comunidad_inexistente", 404, "No existe esa comunidad.")
    if not publica[0]:
        return {"comunidades": []}
    sugeridas = _del_grafo(f"/v1/comunidades/{comunidad_id}/relacionadas", "comunidades")
    return {"comunidades": _completar(conn, sugeridas or [], usuario.id if usuario else None)}


@router.get("/personas/otras-voces")
def otras_voces(usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """Personas que discuten tus temas y están fuera de tu red cercana."""
    personas = _del_grafo(f"/v1/otras-voces/{usuario.id}", "personas")
    if personas is None:
        return {"personas": [], "aviso": "Las sugerencias no están disponibles en este momento."}
    with conn.cursor(row_factory=dict_row) as cur:
        datos = {str(f["id"]): f for f in cur.execute(
            "SELECT id, nombre_visible, foto FROM social.usuario WHERE id = ANY(%s::uuid[]) AND estado = 'activo'",
            ([p["usuario_id"] for p in personas],)).fetchall()}
    return {"personas": [{"nombre_usuario": p["nombre_usuario"], "nombre_visible": datos[p["usuario_id"]]["nombre_visible"],
                          "foto": fotos.url(datos[p["usuario_id"]]["foto"]), "temas": p["temas"]}
                         for p in personas if p["usuario_id"] in datos]}


@router.get("/comunidades/{comunidad_id}")
def ver(comunidad_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    yo = usuario.id if usuario else None
    with conn.cursor(row_factory=dict_row) as cur:
        fila = cur.execute(RESUMEN + " WHERE c.id = %(id)s", {"yo": yo, "id": comunidad_id}).fetchone()
        if fila is None:
            raise ErrorApi("comunidad_inexistente", 404, "No existe esa comunidad.")
        permisos = {a: bool(cur.execute("SELECT social.puede(%s, %s, %s) AS p", (comunidad_id, yo, a)).fetchone()["p"])
                    for a in PERMISOS}
    datos = _comunidad(fila)
    if not permisos["ver"]:
        datos["reglas"] = None  # las reglas de una privada son parte de su contenido
    return {**datos, "permisos": permisos}


@router.patch("/comunidades/{comunidad_id}")
def configurar(comunidad_id: UUID, datos: CambioComunidad, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.configurar_comunidad(%s, %s, %s, %s, %s, %s)",
                 (usuario.id, comunidad_id, datos.nombre, datos.descripcion, datos.reglas, datos.privacidad))
    return ver(comunidad_id, usuario, conn)


@router.put("/comunidades/{comunidad_id}/imagen")
def cambiar_imagen(comunidad_id: UUID, imagen: UploadFile = File(...), usuario: Usuario = Depends(usuario_actual),
                   conn=Depends(conexion)):
    _exigir(conn, comunidad_id, usuario.id, "configurar")
    nombre = fotos.guardar(fotos.procesar(imagen.file.read(fotos.MAXIMO_BYTES + 1)))
    try:
        anterior = conn.execute("CALL social.fijar_imagen_comunidad(%s, %s, %s, NULL)", (usuario.id, comunidad_id, nombre)).fetchone()[0]
        conn.commit()
    except Exception:
        fotos.borrar(nombre)
        raise
    fotos.borrar(anterior)
    return {"imagen": fotos.url(nombre)}


@router.post("/comunidades/{comunidad_id}/ingreso")
def entrar(comunidad_id: UUID, datos: Ingreso, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """Pública: entras de una vez. Privada: queda una solicitud para quien gestiona integrantes."""
    resultado = conn.execute("CALL social.entrar_a_comunidad(%s, %s, %s, NULL)", (usuario.id, comunidad_id, datos.mensaje)).fetchone()[0]
    return {"resultado": resultado}


@router.delete("/comunidades/{comunidad_id}/integrantes/yo", status_code=204)
def salir(comunidad_id: UUID, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.salir_de_comunidad(%s, %s)", (usuario.id, comunidad_id))
    return Response(status_code=204)


@router.get("/comunidades/{comunidad_id}/integrantes")
def integrantes(comunidad_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    _exigir(conn, comunidad_id, usuario.id if usuario else None, "ver")
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT u.nombre_usuario, u.nombre_visible, u.foto, i.papel, i.desde FROM social.integrante i"
            " JOIN social.usuario u ON u.id = i.usuario_id WHERE i.comunidad_id = %s AND u.estado = 'activo'"
            " ORDER BY array_position(ARRAY['administrador', 'gestor', 'moderador', 'integrante'], i.papel), i.desde",
            (comunidad_id,)).fetchall()
    return {"integrantes": [{**f, "foto": fotos.url(f["foto"]), "desde": f["desde"].isoformat()} for f in filas]}


@router.put("/comunidades/{comunidad_id}/integrantes/{nombre_usuario}/papel")
def cambiar_papel(comunidad_id: UUID, nombre_usuario: str, datos: Papel, usuario: Usuario = Depends(usuario_actual),
                  conn=Depends(conexion)):
    conn.execute("CALL social.asignar_papel(%s, %s, %s, %s)", (usuario.id, comunidad_id, id_de(conn, nombre_usuario), datos.papel))
    return {"nombre_usuario": nombre_usuario, "papel": datos.papel}


@router.post("/comunidades/{comunidad_id}/expulsiones", status_code=204)
def expulsar(comunidad_id: UUID, datos: Expulsion, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.expulsar_de_comunidad(%s, %s, %s, %s)",
                 (usuario.id, comunidad_id, id_de(conn, datos.nombre_usuario), datos.motivo))
    return Response(status_code=204)


@router.get("/comunidades/{comunidad_id}/solicitudes")
def solicitudes(comunidad_id: UUID, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    _exigir(conn, comunidad_id, usuario.id, "gestionar_integrantes")
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT s.id::text, u.nombre_usuario, u.nombre_visible, u.foto, s.mensaje, s.creada_en FROM social.solicitud_ingreso s"
            " JOIN social.usuario u ON u.id = s.usuario_id WHERE s.comunidad_id = %s AND s.estado = 'pendiente'"
            " ORDER BY s.creada_en", (comunidad_id,)).fetchall()
    return {"solicitudes": [{**f, "foto": fotos.url(f["foto"]), "creada_en": f["creada_en"].isoformat()} for f in filas]}


@router.post("/comunidades/{comunidad_id}/solicitudes/{solicitud_id}/resolucion", status_code=204)
def resolver(comunidad_id: UUID, solicitud_id: UUID, datos: Resolucion, usuario: Usuario = Depends(usuario_actual),
             conn=Depends(conexion)):
    pertenece = conn.execute("SELECT 1 FROM social.solicitud_ingreso WHERE id = %s AND comunidad_id = %s",
                             (solicitud_id, comunidad_id)).fetchone()
    if pertenece is None:
        raise ErrorApi("solicitud_inexistente", 404, "No existe esa solicitud.")
    conn.execute("CALL social.resolver_solicitud(%s, %s, %s, %s)", (usuario.id, solicitud_id, datos.aceptar, datos.motivo))
    return Response(status_code=204)


@router.get("/comunidades/{comunidad_id}/publicaciones")
def publicaciones(comunidad_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    """Primero las fijadas, luego las más recientes. Solo publicaciones raíz (las respuestas van en su hilo)."""
    yo = usuario.id if usuario else None
    _exigir(conn, comunidad_id, yo, "ver")
    ids = [f[0] for f in conn.execute(
        "SELECT id FROM social.publicacion WHERE comunidad_id = %s AND estado = 'visible' AND responde_a_id IS NULL"
        " ORDER BY fijada_en DESC NULLS LAST, creado_en DESC LIMIT 50", (comunidad_id,))]
    return {"publicaciones": lecturas.publicaciones(conn, ids, yo)}


@router.post("/comunidades/{comunidad_id}/publicaciones", status_code=201)
def publicar(comunidad_id: UUID, datos: PublicacionEnComunidad, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    publicacion_id = conn.execute("CALL social.publicar_en_comunidad(%s, %s, %s, %s, NULL)",
                                  (usuario.id, comunidad_id, datos.texto, [str(f) for f in datos.figuras_ids])).fetchone()[0]
    return lecturas.publicaciones(conn, [publicacion_id], usuario.id)[0]


@router.put("/publicaciones/{publicacion_id}/fijada", status_code=204)
def fijar(publicacion_id: UUID, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.fijar_publicacion(%s, %s, true)", (usuario.id, publicacion_id))
    return Response(status_code=204)


@router.delete("/publicaciones/{publicacion_id}/fijada", status_code=204)
def desfijar(publicacion_id: UUID, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.fijar_publicacion(%s, %s, false)", (usuario.id, publicacion_id))
    return Response(status_code=204)


@router.get("/comunidades/{comunidad_id}/bitacora")
def bitacora(comunidad_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    """Lo que hacen quienes administran, a la vista de quien puede ver la comunidad (transparencia)."""
    _exigir(conn, comunidad_id, usuario.id if usuario else None, "ver")
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT b.accion, a.nombre_usuario AS actor, af.nombre_usuario AS afectado, b.publicacion_id::text,"
            " b.motivo, b.datos, b.creada_en FROM social.bitacora_comunidad b JOIN social.usuario a ON a.id = b.actor_id"
            " LEFT JOIN social.usuario af ON af.id = b.afectado_id WHERE b.comunidad_id = %s ORDER BY b.id DESC LIMIT 100",
            (comunidad_id,)).fetchall()
    return {"bitacora": [{**f, "creada_en": f["creada_en"].isoformat()} for f in filas]}
