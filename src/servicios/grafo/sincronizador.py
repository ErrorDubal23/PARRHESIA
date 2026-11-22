"""Lleva los eventos del outbox de PostgreSQL a Neo4j.

Por cada lote: lee los eventos pendientes para el consumidor "grafo", los aplica en
Neo4j en una sola transacción de Neo4j y, solo después, los marca como entregados
en PostgreSQL. Si algo falla entre los dos pasos, el lote se vuelve a aplicar y,
como todo es MERGE, el grafo queda igual.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from neo4j import Driver

from servicios.grafo import eventos
from servicios.grafo.neo4j_cliente import crear_restricciones, vaciar

CONSUMIDOR = "grafo"
# El outbox de social va primero: las verificaciones hablan de publicaciones.
OUTBOX = (("social", eventos.TIPOS_SOCIAL), ("verificacion", eventos.TIPOS_VERIFICACION))


@dataclass
class Resultado:
    aplicados: int = 0
    por_esquema: dict[str, int] | None = None


class Sincronizador:
    def __init__(self, pg: psycopg.Connection, neo4j: Driver, lote: int = 200) -> None:
        self.pg = pg
        self.neo4j = neo4j
        self.lote = lote

    def procesar_pendientes(self) -> Resultado:
        """Aplica todo lo pendiente, lote por lote, hasta vaciar los dos outbox."""
        resultado = Resultado(por_esquema={})
        for esquema, tipos in OUTBOX:
            while True:
                filas = self.pg.execute(
                    f"SELECT id, tipo_evento, datos FROM {esquema}.eventos_pendientes(%s, %s, %s)",
                    (CONSUMIDOR, tipos, self.lote),
                ).fetchall()
                if not filas:
                    break
                self._aplicar_lote(filas)
                self.pg.execute(f"CALL {esquema}.marcar_entregados(%s, %s)", (CONSUMIDOR, [f[0] for f in filas]))
                resultado.aplicados += len(filas)
                resultado.por_esquema[esquema] = resultado.por_esquema.get(esquema, 0) + len(filas)
        return resultado

    def reconstruir(self) -> int:
        """Vacía Neo4j y vuelve a aplicar toda la historia del outbox, en orden.

        El outbox es de solo inserción: guarda cada cambio de la red desde el
        principio, así que repetirlo deja el grafo exactamente como estaba.
        """
        vaciar(self.neo4j)
        crear_restricciones(self.neo4j)
        total = 0
        for esquema, tipos in OUTBOX:
            ultimo = 0
            while True:
                filas = self.pg.execute(
                    f"SELECT id, tipo_evento, datos FROM {esquema}.evento_salida"
                    " WHERE tipo_evento = ANY (%s) AND id > %s ORDER BY id LIMIT %s",
                    (tipos, ultimo, self.lote),
                ).fetchall()
                if not filas:
                    break
                self._aplicar_lote(filas)
                ultimo = filas[-1][0]
                total += len(filas)
        return total

    def _aplicar_lote(self, filas) -> None:
        def trabajo(tx):
            for _, tipo_evento, datos in filas:
                eventos.aplicar(tx, tipo_evento, datos)

        with self.neo4j.session() as sesion:
            sesion.execute_write(trabajo)
