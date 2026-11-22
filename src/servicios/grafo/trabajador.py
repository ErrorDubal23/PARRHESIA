"""Trabajador del servicio de grafo: sincroniza el outbox con Neo4j y calcula tendencias.

    uv run python -m servicios.grafo.trabajador

Escucha pg_notify('evento_salida'): cuando un trigger escribe un evento, PostgreSQL
avisa y el trabajador lo aplica enseguida. Si no llega aviso, revisa cada 30 s de
todos modos (por si un aviso se perdió). Cada hora calcula las tendencias de las
últimas 24 horas y las guarda en social.tendencia.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from servicios.comun.configuracion import conectar_postgres
from servicios.grafo import consultas
from servicios.grafo.neo4j_cliente import conectar_neo4j, crear_restricciones
from servicios.grafo.sincronizador import Sincronizador

registro = logging.getLogger("grafo")
ESPERA_MAXIMA = 30  # segundos sin aviso antes de revisar de todos modos


def calcular_tendencias(pg, neo4j) -> None:
    hasta = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    desde = hasta - timedelta(hours=24)
    filas = consultas.calcular_tendencias(neo4j, desde, hasta)
    if filas:
        consultas.registrar_tendencias(pg, desde, hasta, filas)
    registro.info("tendencias %s – %s: %d etiquetas", desde.isoformat(), hasta.isoformat(), len(filas))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    neo4j = conectar_neo4j()
    crear_restricciones(neo4j)
    escucha = conectar_postgres("PG_URL_GRAFO")
    escucha.execute("LISTEN evento_salida")
    proxima_tendencia = 0.0
    with conectar_postgres("PG_URL_GRAFO") as pg:
        sincronizador = Sincronizador(pg, neo4j)
        while True:
            resultado = sincronizador.procesar_pendientes()
            if resultado.aplicados:
                registro.info("aplicados %d eventos %s", resultado.aplicados, resultado.por_esquema)
            if time.monotonic() >= proxima_tendencia:
                calcular_tendencias(pg, neo4j)
                proxima_tendencia = time.monotonic() + 3600
            # Espera un aviso de PostgreSQL (o el tiempo máximo) antes de volver a revisar.
            for _ in escucha.notifies(timeout=ESPERA_MAXIMA, stop_after=1):
                pass


if __name__ == "__main__":
    main()
