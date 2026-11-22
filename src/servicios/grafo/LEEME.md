# Servicio de grafo

Proyección de la red social en Neo4j. PostgreSQL es la fuente de verdad; este servicio es el único que escribe en Neo4j, a partir del outbox (`social.evento_salida` y `verificacion.evento_salida`).

| Archivo | Qué hace |
|---|---|
| `eventos.py` | El Cypher de cada evento (todo `MERGE`: aplicarlo dos veces deja el mismo grafo) |
| `sincronizador.py` | Lee los eventos pendientes del consumidor `grafo`, los aplica en Neo4j y los marca como entregados; `reconstruir()` vuelve a aplicar toda la historia |
| `consultas.py` | Feed, a quién seguir, difusión y tendencias por diversidad |
| `api.py` | API interna (contrato en `docs/diseno/07_apis.md`, sección 3) |
| `trabajador.py` | Proceso de fondo: escucha `pg_notify('evento_salida')` y calcula tendencias cada hora |

```bash
docker compose up -d                                        # PostgreSQL y Neo4j
uv run python -m servicios.grafo.trabajador                 # sincronizador
uv run uvicorn servicios.grafo.api:app --port 8002          # API (documentación en /docs)
curl -X POST http://127.0.0.1:8002/v1/reconstruir           # rehacer el grafo desde PostgreSQL
```

Neo4j Browser: <http://localhost:7474> (usuario `neo4j`, contraseña `NEO4J_PASSWORD` del `.env`). Para ver la red:

```cypher
MATCH (u:Usuario)-[r]->(x) RETURN u, r, x LIMIT 200
```
