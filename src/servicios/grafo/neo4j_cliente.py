"""Conexión a Neo4j y restricciones del modelo de grafo."""

from __future__ import annotations

import logging

from neo4j import Driver, GraphDatabase

# Los avisos informativos de Neo4j ("la restricción ya existe") no son errores: no llenan los registros.
logging.getLogger("neo4j").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from servicios.comun.configuracion import obligatoria, variable

# Restricciones e índices (docs/diseno/04_modelo_grafo.md). IF NOT EXISTS: se pueden correr siempre.
RESTRICCIONES = (
    "CREATE CONSTRAINT usuario_id IF NOT EXISTS FOR (u:Usuario) REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT publicacion_id IF NOT EXISTS FOR (p:Publicacion) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT etiqueta_nombre IF NOT EXISTS FOR (e:Etiqueta) REQUIRE e.nombre IS UNIQUE",
    "CREATE CONSTRAINT figura_id IF NOT EXISTS FOR (f:Figura) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT serie_codigo IF NOT EXISTS FOR (s:Serie) REQUIRE s.codigo IS UNIQUE",
    "CREATE CONSTRAINT comunidad_id IF NOT EXISTS FOR (c:Comunidad) REQUIRE c.id IS UNIQUE",
    "CREATE INDEX publicacion_creado_en IF NOT EXISTS FOR (p:Publicacion) ON (p.creado_en)",
)


def conectar_neo4j() -> Driver:
    url = variable("NEO4J_URL", "bolt://127.0.0.1:7687")
    driver = GraphDatabase.driver(url, auth=("neo4j", obligatoria("NEO4J_PASSWORD")))
    driver.verify_connectivity()
    return driver


def crear_restricciones(driver: Driver) -> None:
    with driver.session() as sesion:
        for sentencia in RESTRICCIONES:
            sesion.run(sentencia).consume()


def vaciar(driver: Driver) -> None:
    """Borra todo el grafo. Solo para reconstruirlo desde PostgreSQL."""
    with driver.session() as sesion:
        sesion.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS").consume()
