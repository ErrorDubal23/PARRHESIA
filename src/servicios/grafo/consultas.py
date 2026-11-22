"""Las consultas que justifican el grafo (docs/diseno/04_modelo_grafo.md): red, tendencias y descubrimiento."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
from neo4j import Driver
from psycopg.types.json import Jsonb

FEED = """
CALL () {
  MATCH (yo:Usuario {id: $yo})-[:SIGUE]->(a:Usuario)-[:PUBLICO]->(p:Publicacion)
  RETURN p, a, 1 AS distancia
  UNION
  MATCH (yo:Usuario {id: $yo})-[:SIGUE]->(:Usuario)-[:SIGUE]->(a:Usuario)-[:PUBLICO]->(p:Publicacion)
  WHERE a.id <> $yo AND NOT (yo)-[:SIGUE]->(a)
  RETURN p, a, 2 AS distancia
  UNION
  // Lo propio también (auditoría FN-03): quien publica ve su publicación en su inicio, mezclada por fecha con
  // lo de quienes sigue. Antes, una cuenta nueva publicaba y su inicio seguía "vacío".
  MATCH (a:Usuario {id: $yo})-[:PUBLICO]->(p:Publicacion)
  RETURN p, a, 1 AS distancia
}
WITH p, a, min(distancia) AS distancia
MATCH (yo:Usuario {id: $yo})
WHERE p.estado = 'visible'
  AND NOT (p)-[:RESPONDE_A]->()   // el inicio muestra publicaciones y compartidas; las respuestas, en su hilo
  AND NOT EXISTS { MATCH (p)-[:EN]->(c:Comunidad {privacidad: 'privada'}) WHERE NOT (yo)-[:INTEGRA]->(c) }
  AND p.creado_en >= datetime() - duration('P7D')
  AND ($antes_de IS NULL OR p.creado_en < datetime($antes_de))
RETURN p.id AS publicacion_id, a.id AS autor_id, distancia, toString(p.creado_en) AS creado_en
ORDER BY distancia, p.creado_en DESC
LIMIT $limite
"""

SUGERENCIAS = """
MATCH (yo:Usuario {id: $yo})-[:SIGUE]->(f:Usuario)-[:SIGUE]->(s:Usuario)
WHERE s.id <> $yo AND s.estado = 'activo' AND NOT (yo)-[:SIGUE]->(s)
RETURN s.id AS usuario_id, s.nombre_usuario AS nombre_usuario, count(DISTINCT f) AS en_comun
ORDER BY en_comun DESC, nombre_usuario
LIMIT 10
"""

DIFUSION = """
MATCH ruta = (origen:Publicacion {id: $publicacion})<-[:COMPARTE*1..10]-(c:Publicacion)
MATCH (u:Usuario)-[:PUBLICO]->(c)
RETURN c.id AS compartida_id, u.nombre_usuario AS compartida_por, length(ruta) AS profundidad,
       nodes(ruta)[-2].id AS compartida_de
ORDER BY profundidad, compartida_id
"""

# Una etiqueta sube más cuando la usan personas que NO se siguen entre sí. No mira
# el lado político de nadie: solo la estructura de la red (decisión 8).
TENDENCIAS = """
MATCH (e:Etiqueta)<-[:ETIQUETADA_CON]-(p:Publicacion)<-[:PUBLICO]-(a:Usuario)
WHERE p.creado_en >= datetime($desde) AND p.creado_en < datetime($hasta)
  AND p.estado = 'visible'
  AND a.estado = 'activo'
  AND a.creado_en < datetime($desde) - duration('P7D')
  AND NOT (p)-[:EN]->(:Comunidad {privacidad: 'privada'})   // lo privado no sale de su comunidad
WITH e, collect(DISTINCT a) AS autores, count(DISTINCT p) AS publicaciones
WHERE size(autores) >= 3
CALL (autores) {
  UNWIND autores AS x
  MATCH (x)-[:SIGUE]->(y:Usuario)
  WHERE y IN autores
  RETURN count(*) AS enlaces
}
WITH e, publicaciones, size(autores) AS n, enlaces
WITH e, publicaciones, n, 1.0 - toFloat(enlaces) / (n * (n - 1)) AS diversidad
RETURN e.nombre AS etiqueta, publicaciones, n AS autores, diversidad, publicaciones * diversidad AS puntaje
ORDER BY puntaje DESC, autores DESC, etiqueta
LIMIT 10
"""


# --- Descubrimiento sin burbujas (T11) --------------------------------------------------------
# Los intereses de una persona salen de lo que publica o a lo que reacciona (sus etiquetas), nunca
# de una inclinación política. Lo publicado en comunidades privadas no alimenta ninguna sugerencia:
# revelaría de qué se habla adentro. Se prioriza lo que está FUERA de la red cercana.

MIS_TEMAS = """
MATCH (yo:Usuario {id: $yo})-[:PUBLICO|REACCIONO]->(mia:Publicacion)-[:ETIQUETADA_CON]->(e:Etiqueta)
WHERE mia.estado = 'visible' AND NOT (mia)-[:EN]->(:Comunidad {privacidad: 'privada'})
WITH yo, collect(DISTINCT e) AS mis_temas
"""

# Comunidades públicas que hablan de mis temas; pesa más la que tiene integrantes fuera de mi red
# (ni los sigo, ni me siguen, ni los sigue alguien a quien sigo).
COMUNIDADES_RECOMENDADAS = MIS_TEMAS + """
UNWIND mis_temas AS e
MATCH (e)<-[:ETIQUETADA_CON]-(p:Publicacion)-[:EN]->(c:Comunidad {privacidad: 'publica'})
WHERE p.estado = 'visible' AND NOT (yo)-[:INTEGRA]->(c)
WITH yo, c, collect(DISTINCT e.nombre) AS temas, count(DISTINCT p) AS publicaciones
OPTIONAL MATCH (m:Usuario)-[:INTEGRA]->(c)
WITH yo, c, temas, publicaciones, collect(m) AS integrantes
WITH c, temas, publicaciones, size(integrantes) AS total,
     size([m IN integrantes WHERE NOT EXISTS { (yo)-[:SIGUE]-(m) }
                               AND NOT EXISTS { (yo)-[:SIGUE]->(:Usuario)-[:SIGUE]->(m) }]) AS lejanos
WITH c, temas, publicaciones, total, CASE total WHEN 0 THEN 1.0 ELSE toFloat(lejanos) / total END AS fuera_de_mi_red
RETURN c.id AS comunidad_id, temas[0..5] AS temas, publicaciones, fuera_de_mi_red,
       size(temas) * (0.5 + fuera_de_mi_red) AS puntaje
ORDER BY puntaje DESC, publicaciones DESC, comunidad_id
LIMIT 6
"""

# Otras comunidades públicas que discuten los mismos temas; primero las que comparten MENOS integrantes:
# el mismo asunto visto desde otros grupos.
COMUNIDADES_RELACIONADAS = """
MATCH (c:Comunidad {id: $comunidad, privacidad: 'publica'})<-[:EN]-(p:Publicacion)-[:ETIQUETADA_CON]->(e:Etiqueta)
WHERE p.estado = 'visible'
WITH c, collect(DISTINCT e) AS temas_c
UNWIND temas_c AS e
MATCH (e)<-[:ETIQUETADA_CON]-(q:Publicacion)-[:EN]->(otra:Comunidad {privacidad: 'publica'})
WHERE otra <> c AND q.estado = 'visible'
WITH c, otra, collect(DISTINCT e.nombre) AS temas, count(DISTINCT q) AS publicaciones
OPTIONAL MATCH (c)<-[:INTEGRA]-(m:Usuario)-[:INTEGRA]->(otra)
WITH otra, temas, publicaciones, count(DISTINCT m) AS en_comun
RETURN otra.id AS comunidad_id, temas[0..5] AS temas, publicaciones, en_comun
ORDER BY size(temas) DESC, en_comun ASC, publicaciones DESC
LIMIT 5
"""

# Personas que discuten mis temas y están fuera de mi red cercana (lo contrario de "amigos de amigos").
OTRAS_VOCES = MIS_TEMAS + """
UNWIND mis_temas AS e
MATCH (e)<-[:ETIQUETADA_CON]-(p:Publicacion)<-[:PUBLICO]-(otra:Usuario)
WHERE otra <> yo AND otra.estado = 'activo' AND p.estado = 'visible'
  AND NOT (p)-[:EN]->(:Comunidad {privacidad: 'privada'})
  AND NOT (yo)-[:SIGUE]->(otra)
  AND NOT EXISTS { (yo)-[:SIGUE]->(:Usuario)-[:SIGUE]->(otra) }
WITH otra, collect(DISTINCT e.nombre) AS temas, count(DISTINCT p) AS publicaciones
RETURN otra.id AS usuario_id, otra.nombre_usuario AS nombre_usuario, temas[0..4] AS temas, publicaciones
ORDER BY size(temas) DESC, publicaciones DESC, nombre_usuario
LIMIT 8
"""


def _lista(neo4j: Driver, consulta: str, **parametros) -> list[dict]:
    registros, _, _ = neo4j.execute_query(consulta, **parametros)
    return [r.data() for r in registros]


def comunidades_recomendadas(neo4j: Driver, usuario_id: str) -> list[dict]:
    return _lista(neo4j, COMUNIDADES_RECOMENDADAS, yo=usuario_id)


def comunidades_relacionadas(neo4j: Driver, comunidad_id: str) -> list[dict]:
    return _lista(neo4j, COMUNIDADES_RELACIONADAS, comunidad=comunidad_id)


def otras_voces(neo4j: Driver, usuario_id: str) -> list[dict]:
    return _lista(neo4j, OTRAS_VOCES, yo=usuario_id)


def feed(neo4j: Driver, usuario_id: str, limite: int = 50, antes_de: str | None = None) -> list[dict]:
    registros, _, _ = neo4j.execute_query(FEED, yo=usuario_id, limite=limite, antes_de=antes_de)
    return [r.data() for r in registros]


def sugerencias(neo4j: Driver, usuario_id: str) -> list[dict]:
    registros, _, _ = neo4j.execute_query(SUGERENCIAS, yo=usuario_id)
    return [r.data() for r in registros]


def difusion(neo4j: Driver, publicacion_id: str) -> dict:
    registros, _, _ = neo4j.execute_query(DIFUSION, publicacion=publicacion_id)
    compartidas = [r.data() for r in registros]
    return {
        "publicacion_id": publicacion_id,
        "alcance": len({c["compartida_por"] for c in compartidas}),
        "profundidad_maxima": max((c["profundidad"] for c in compartidas), default=0),
        "compartidas": compartidas,
    }


def calcular_tendencias(neo4j: Driver, desde: datetime, hasta: datetime) -> list[dict]:
    registros, _, _ = neo4j.execute_query(TENDENCIAS, desde=desde.isoformat(), hasta=hasta.isoformat())
    filas = []
    for posicion, r in enumerate(registros, start=1):
        diversidad = Decimal(str(round(r["diversidad"], 4)))
        filas.append({
            "etiqueta": r["etiqueta"], "total_publicaciones": r["publicaciones"], "total_autores": r["autores"],
            "diversidad": str(diversidad), "puntaje": str(Decimal(r["publicaciones"]) * diversidad), "posicion": posicion,
        })
    return filas


def registrar_tendencias(pg: psycopg.Connection, desde: datetime, hasta: datetime, filas: list[dict]) -> bool:
    """Guarda la ventana en social.tendencia: todas las filas o ninguna.

    La tabla es de solo inserción: si esa ventana ya se calculó (por ejemplo, el trabajador se reinició dentro
    de la misma hora), queda el primer cálculo y se devuelve False en lugar de fallar.
    """
    try:
        pg.execute("CALL social.registrar_tendencias(%s, %s, %s)", (desde, hasta, Jsonb(filas)))
    except psycopg.errors.UniqueViolation:
        return False
    return True
