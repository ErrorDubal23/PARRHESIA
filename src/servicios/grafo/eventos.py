"""Cómo se aplica cada evento del outbox en Neo4j.

Todo es MERGE (o DELETE de algo que puede no estar): aplicar un evento dos veces,
o volver a aplicar toda la historia, deja el mismo grafo. Por eso el sincronizador
puede caerse entre Neo4j y PostgreSQL sin dañar nada (entrega "al menos una vez").
Los nodos que todavía no existen se crean con MERGE: el orden de llegada no importa.
"""

from __future__ import annotations

from neo4j import ManagedTransaction

CYPHER: dict[str, str] = {
    "usuario_creado": """
        MERGE (u:Usuario {id: $id})
        SET u.nombre_usuario = $nombre_usuario, u.estado = $estado, u.creado_en = datetime($creado_en)""",
    "usuario_actualizado": """
        MERGE (u:Usuario {id: $id})
        SET u.nombre_usuario = $nombre_usuario""",
    "usuario_cambio_estado": """
        MERGE (u:Usuario {id: $id})
        SET u.estado = $estado""",
    # Comunidades (T11): solo lo necesario para descubrir. Papeles y permisos viven en PostgreSQL.
    "comunidad_creada": """
        MERGE (c:Comunidad {id: $id})
        SET c.nombre = $nombre, c.privacidad = $privacidad, c.creada_en = datetime($creada_en)""",
    "comunidad_actualizada": """
        MERGE (c:Comunidad {id: $id})
        SET c.nombre = $nombre, c.privacidad = $privacidad""",
    "integrante_agregado": """
        MERGE (u:Usuario {id: $usuario})
        MERGE (c:Comunidad {id: $comunidad})
        MERGE (u)-[i:INTEGRA]->(c)
        SET i.desde = datetime($desde)""",
    "integrante_quitado": """
        MATCH (:Usuario {id: $usuario})-[i:INTEGRA]->(:Comunidad {id: $comunidad})
        DELETE i""",
    "publicacion_en_comunidad": """
        MERGE (p:Publicacion {id: $publicacion})
        MERGE (c:Comunidad {id: $comunidad})
        MERGE (p)-[:EN]->(c)""",
    "seguimiento_creado": """
        MERGE (a:Usuario {id: $seguidor})
        MERGE (b:Usuario {id: $seguido})
        MERGE (a)-[s:SIGUE]->(b)
        SET s.desde = datetime($en)""",
    "seguimiento_borrado": """
        MATCH (:Usuario {id: $seguidor})-[s:SIGUE]->(:Usuario {id: $seguido})
        DELETE s""",
    "publicacion_creada": """
        MERGE (p:Publicacion {id: $id})
        SET p.estado = coalesce(p.estado, 'visible'), p.creado_en = datetime($creado_en)
        MERGE (u:Usuario {id: $autor})
        MERGE (u)-[:PUBLICO]->(p)
        FOREACH (x IN CASE WHEN $responde_a IS NULL THEN [] ELSE [$responde_a] END |
            MERGE (o:Publicacion {id: x}) MERGE (p)-[:RESPONDE_A]->(o))
        FOREACH (x IN CASE WHEN $comparte IS NULL THEN [] ELSE [$comparte] END |
            MERGE (o:Publicacion {id: x}) MERGE (p)-[:COMPARTE]->(o))""",
    "publicacion_retirada": """
        MERGE (p:Publicacion {id: $id})
        SET p.estado = $estado""",
    "publicacion_etiquetada": """
        MERGE (p:Publicacion {id: $publicacion})
        MERGE (e:Etiqueta {nombre: $etiqueta})
        MERGE (p)-[:ETIQUETADA_CON]->(e)""",
    "reaccion_puesta": """
        MERGE (u:Usuario {id: $usuario})
        MERGE (p:Publicacion {id: $publicacion})
        MERGE (u)-[r:REACCIONO]->(p)
        SET r.tipo = $tipo, r.en = datetime($en)""",
    "reaccion_quitada": """
        MATCH (:Usuario {id: $usuario})-[r:REACCIONO]->(:Publicacion {id: $publicacion})
        DELETE r""",
    "figura_creada": """
        MERGE (f:Figura {id: $id})
        SET f.nombre_completo = $nombre_completo""",
    # Solo las verificaciones de publicaciones entran al grafo, y solo si hay serie
    # (una conclusión "sin dato comparable" no tiene serie). Una versión vieja que
    # llegue tarde no pisa a una más nueva.
    "verificacion_publicada": """
        WITH $publicacion AS publicacion, $serie AS serie
        WHERE publicacion IS NOT NULL AND serie IS NOT NULL
        MERGE (p:Publicacion {id: publicacion})
        MERGE (s:Serie {codigo: serie})
        SET s.indicador = $indicador
        MERGE (p)-[v:VERIFICADA_CON]->(s)
        WITH v WHERE coalesce(v.version, 0) <= $version
        SET v.conclusion = $conclusion, v.version = $version""",
}

# Menciones: el destino puede ser un usuario o una figura.
CYPHER_MENCION = {
    "usuario": """
        MERGE (p:Publicacion {id: $publicacion})
        MERGE (d:Usuario {id: $destino_id})
        MERGE (p)-[:MENCIONA]->(d)""",
    "figura": """
        MERGE (p:Publicacion {id: $publicacion})
        MERGE (d:Figura {id: $destino_id})
        MERGE (p)-[:MENCIONA]->(d)""",
}

# Eventos que el grafo procesa de cada outbox. declaracion_creada no es de la red.
TIPOS_SOCIAL = [t for t in CYPHER if t != "verificacion_publicada"] + ["publicacion_menciona"]
TIPOS_VERIFICACION = ["verificacion_publicada"]


def aplicar(tx: ManagedTransaction, tipo_evento: str, datos: dict) -> None:
    if tipo_evento == "publicacion_menciona":
        tx.run(CYPHER_MENCION[datos["tipo_destino"]], datos).consume()
    elif tipo_evento in CYPHER:
        parametros = dict(datos)
        if tipo_evento == "verificacion_publicada":
            parametros.setdefault("indicador", None)
        tx.run(CYPHER[tipo_evento], parametros).consume()
    else:
        raise ValueError(f"evento desconocido para el grafo: {tipo_evento}")
