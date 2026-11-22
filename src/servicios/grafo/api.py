"""API del servicio de grafo (solo red interna; la usa el servicio social).

    uv run uvicorn servicios.grafo.api:app --port 8002

Contrato: docs/diseno/07_apis.md, sección 3.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from servicios.comun.configuracion import conectar_postgres
from servicios.grafo import consultas
from servicios.grafo.neo4j_cliente import conectar_neo4j, crear_restricciones
from servicios.grafo.sincronizador import Sincronizador

recursos: dict = {}


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    recursos["neo4j"] = conectar_neo4j()
    crear_restricciones(recursos["neo4j"])
    yield
    recursos["neo4j"].close()


app = FastAPI(title="Servicio de grafo", version="1", lifespan=ciclo_de_vida)


def neo4j():
    return recursos["neo4j"]


@app.get("/salud")
def salud():
    estado = {"estado": "ok", "base": "ok", "neo4j": "ok"}
    try:
        with conectar_postgres("PG_URL_GRAFO") as pg:
            pg.execute("SELECT 1")
    except Exception:
        estado.update(estado="falla", base="falla")
    try:
        neo4j().verify_connectivity()
    except Exception:
        estado.update(estado="falla", neo4j="falla")
    return JSONResponse(estado, status_code=200 if estado["estado"] == "ok" else 503)


@app.get("/v1/feed/{usuario_id}")
def feed(usuario_id: str, limite: int = Query(50, ge=1, le=100), antes_de: str | None = None):
    publicaciones = consultas.feed(neo4j(), usuario_id, limite, antes_de)
    siguiente = publicaciones[-1]["creado_en"] if len(publicaciones) == limite else None
    return {"publicaciones": publicaciones, "siguiente": siguiente}


@app.get("/v1/sugerencias/{usuario_id}")
def sugerencias(usuario_id: str):
    return {"sugerencias": consultas.sugerencias(neo4j(), usuario_id)}


@app.get("/v1/comunidades/recomendadas/{usuario_id}")
def comunidades_recomendadas(usuario_id: str):
    return {"comunidades": consultas.comunidades_recomendadas(neo4j(), usuario_id)}


@app.get("/v1/comunidades/{comunidad_id}/relacionadas")
def comunidades_relacionadas(comunidad_id: str):
    return {"comunidades": consultas.comunidades_relacionadas(neo4j(), comunidad_id)}


@app.get("/v1/otras-voces/{usuario_id}")
def otras_voces(usuario_id: str):
    return {"personas": consultas.otras_voces(neo4j(), usuario_id)}


@app.get("/v1/difusion/{publicacion_id}")
def difusion(publicacion_id: str):
    return consultas.difusion(neo4j(), publicacion_id)


@app.post("/v1/tendencias/calcular")
def calcular_tendencias(horas: int = Query(24, ge=1, le=168)):
    hasta = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    desde = hasta - timedelta(hours=horas)
    filas = consultas.calcular_tendencias(neo4j(), desde, hasta)
    if filas:
        with conectar_postgres("PG_URL_GRAFO") as pg:
            consultas.registrar_tendencias(pg, desde, hasta, filas)
    return {"ventana_inicio": desde.isoformat(), "ventana_fin": hasta.isoformat(), "tendencias": filas}


@app.post("/v1/reconstruir")
def reconstruir():
    """Vacía Neo4j y lo reconstruye desde PostgreSQL: el grafo es una proyección, no la fuente de verdad."""
    with conectar_postgres("PG_URL_GRAFO") as pg:
        aplicados = Sincronizador(pg, neo4j()).reconstruir()
    return {"eventos_aplicados": aplicados}
