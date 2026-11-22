"""Consultas de lectura del servicio social: arman las publicaciones como las ve la app."""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from servicios.social import fotos

PUBLICACIONES = """
SELECT p.id, p.texto, p.estado, p.responde_a_id, p.comparte_id, p.creado_en,
       p.total_respuestas, p.total_compartidas, p.total_reacciones,
       u.nombre_usuario, u.nombre_visible, u.foto, p.comunidad_id, p.fijada_en, c.nombre AS comunidad_nombre,
       c.privacidad AS comunidad_privacidad,
       ARRAY(SELECT e.nombre FROM social.publicacion_etiqueta pe JOIN social.etiqueta e ON e.id = pe.etiqueta_id
             WHERE pe.publicacion_id = p.id ORDER BY e.nombre) AS etiquetas,
       verificacion.estado_publicacion(p.id) AS verificacion,
       (SELECT u2.nombre_usuario FROM social.publicacion p2 JOIN social.usuario u2 ON u2.id = p2.autor_id
        WHERE p2.id = p.responde_a_id) AS responde_a_usuario,
       (SELECT r.tipo FROM social.reaccion r WHERE r.publicacion_id = p.id AND r.usuario_id = %(yo)s) AS mi_reaccion,
       (SELECT count(*) FROM social.reaccion r WHERE r.publicacion_id = p.id AND r.tipo = 'me_gusta') AS total_me_gusta,
       (SELECT x.id FROM social.publicacion x WHERE x.comparte_id = p.id AND x.autor_id = %(yo)s
          AND x.texto IS NULL AND x.estado = 'visible') AS mi_compartida
FROM social.publicacion p JOIN social.usuario u ON u.id = p.autor_id
LEFT JOIN social.comunidad c ON c.id = p.comunidad_id
WHERE p.id = ANY (%(ids)s)
  AND social.puede_ver_publicacion(p.id, %(yo)s::uuid)   -- lo de una comunidad privada, solo para integrantes
"""


def publicaciones(conn: Connection, ids: list, yo: str | None = None, con_original: bool = True) -> list[dict]:
    """Las publicaciones en el mismo orden de `ids`. Una retirada se muestra sin su texto.

    Una compartida trae su `original` (un solo nivel, y solo si quien mira puede verlo), para que se sepa
    qué se compartió; una respuesta trae a quién responde.
    """
    if not ids:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        filas = {str(f["id"]): f for f in cur.execute(PUBLICACIONES, {"ids": [str(i) for i in ids], "yo": yo})}
    resultado = []
    for i in ids:
        f = filas.get(str(i))
        if f is None:
            continue
        visible = f["estado"] == "visible"
        resultado.append({
            "id": str(f["id"]),
            "autor": {"nombre_usuario": f["nombre_usuario"], "nombre_visible": f["nombre_visible"],
                      "foto": fotos.url(f["foto"])},
            "texto": f["texto"] if visible else None,
            "estado": f["estado"],
            "responde_a_id": str(f["responde_a_id"]) if f["responde_a_id"] else None,
            "comparte_id": str(f["comparte_id"]) if f["comparte_id"] else None,
            "etiquetas": f["etiquetas"],
            "creado_en": f["creado_en"].isoformat(),
            "totales": {"respuestas": f["total_respuestas"], "compartidas": f["total_compartidas"],
                        "reacciones": f["total_reacciones"], "me_gusta": f["total_me_gusta"],
                        "util": f["total_reacciones"] - f["total_me_gusta"]},
            "mi_reaccion": f["mi_reaccion"],
            "mi_compartida": str(f["mi_compartida"]) if f["mi_compartida"] else None,
            "verificacion": f["verificacion"],
            "comunidad": ({"id": str(f["comunidad_id"]), "nombre": f["comunidad_nombre"], "privacidad": f["comunidad_privacidad"]}
                          if f["comunidad_id"] else None),
            "fijada": f["fijada_en"] is not None,
            "responde_a": {"nombre_usuario": f["responde_a_usuario"]} if f["responde_a_usuario"] else None,
            "original": None,
        })
    if con_original:
        compartidas = [p["comparte_id"] for p in resultado if p["comparte_id"]]
        originales = {o["id"]: o for o in publicaciones(conn, compartidas, yo, con_original=False)}
        for p in resultado:
            p["original"] = originales.get(p["comparte_id"]) if p["comparte_id"] else None
    return resultado


def usuario_por_nombre(conn: Connection, nombre_usuario: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, nombre_usuario, nombre_visible, biografia, rol, estado, foto, creado_en FROM social.usuario"
            " WHERE id = social.resolver_nombre(%s)", (nombre_usuario,)).fetchone()  # también nombres anteriores


def feed_de_respaldo(conn: Connection, yo: str, antes_de: datetime | None, limite: int) -> list[str]:
    """Si el grafo no responde: lo propio y lo de las personas que sigo (sin el segundo nivel)."""
    filas = conn.execute(
        "SELECT p.id FROM social.publicacion p"
        " WHERE (p.autor_id = %s OR p.autor_id IN (SELECT seguido_id FROM social.seguimiento WHERE seguidor_id = %s))"
        " AND p.estado = 'visible' AND p.responde_a_id IS NULL"
        " AND p.creado_en >= now() - interval '7 days'"
        " AND (%s::timestamptz IS NULL OR p.creado_en < %s::timestamptz)"
        " ORDER BY p.creado_en DESC LIMIT %s", (yo, yo, antes_de, antes_de, limite)).fetchall()
    return [str(f[0]) for f in filas]
