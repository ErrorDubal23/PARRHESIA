# Parrhesia

Red social colombiana donde cualquiera publica su opinión y donde cada publicación que cita una cifra pública
queda unida al dato oficial completo. No dice "verdadero" o "falso": la conclusión **se sostiene**, **se
debilita**, **se invierte** o queda **sin dato comparable**, con la misma regla para todos. Proyecto final de
Bases de Datos (diciembre de 2026).

- **PostgreSQL 17**: fuente de verdad (procedimientos, funciones, triggers, tablas de solo inserción, outbox y un
  rol por servicio).
- **Neo4j 5**: proyección de la red (feed, tendencias por diversidad, a quién seguir), alimentada desde
  PostgreSQL por el outbox.
- **Microservicios en Python + FastAPI**: social, verificación, datos oficiales, temas del día, IA y grafo,
  detrás de una puerta de entrada Nginx.
- **App web** en React + Vite + TypeScript. Todo con Docker Compose.

## Arrancar en un equipo nuevo

Requisitos: Docker Desktop, [uv](https://docs.astral.sh/uv/) (Python) y git.

```bash
git clone <repositorio> && cd <carpeta>
uv run python scripts/preparar_env.py      # crea .env con contraseñas al azar (nunca sobrescribe uno existente)
docker compose up -d --build               # aplica las migraciones, crea los roles y levanta todo
```

La app queda en <http://localhost:8080>. La primera vez tarda unos minutos (construye las imágenes).

Opcional, según lo que se quiera mostrar:

```bash
# Datos oficiales (DANE y SUAMECA; homicidios de datos.gov.co necesita SOCRATA_APP_TOKEN en .env)
uv run python -m app.runs dane --db
uv run python -m app.runs homicides --db

# Primer administrador (solo desde la consola; después se asignan roles en la página Equipo)
uv run python db/consola/asignar_rol.py --usuario <tu_usuario> --rol admin --motivo "Primer administrador del proyecto."

# Datos de demostración, figuras públicas y declaraciones reales (ver db/LEEME.md)
uv run python db/semillas/demo.py --resembrar
uv run python db/semillas/figuras.py --verificador <usuario_verificador>
uv run python db/semillas/declaraciones.py --verificador <usuario_verificador>
```

Las llaves de IA (Groq, Gemini, OpenRouter), Unsplash y Fact Check son opcionales: sin ellas la red social funciona y
las verificaciones quedan pendientes. Ver los comentarios en `.env.example`.

**Nunca `docker compose down -v`**: `-v` borra los volúmenes, es decir, los datos. `docker compose down` y
`up -d` conservan todo.

## Pruebas

```bash
docker compose --profile pruebas up -d neo4j-pruebas   # Neo4j aparte para las pruebas del grafo
uv run pytest                                          # crea una base temporal con todas las migraciones y la borra
```

Auditoría (ver `docs/auditoria/`): `scripts/auditoria/bd_catalogo.py` (catálogo y coherencia de la base),
`recorrido_api.py` (recorre los cinco servicios), `ataques.py` (ataques desde fuera) y `caidas.py` (detiene
contenedores y comprueba que todo se recupere; hacer un respaldo antes).

## Dónde está cada cosa

| Carpeta | Qué hay |
| --- | --- |
| `db/migrations/` | Migraciones numeradas de PostgreSQL; [db/LEEME.md](db/LEEME.md) explica cada una |
| `db/semillas/`, `db/consola/` | Datos de demostración y tareas de administración |
| `src/servicios/` | Microservicios (social, verificacion, oficial, temas, ia, grafo y lo común) |
| `src/app/` | Conectores de datos oficiales y migrador |
| `web/` | App web |
| `gateway/` | Puerta de entrada Nginx y encabezados de seguridad |
| `catalog/`, `evidence/` | Fichas de las series aprobadas y evidencia de las fuentes |
| `docs/diseno/` | Diseño: decisiones, MER, modelo relacional, grafo, lógica de la base, APIs, Docker |
| `docs/auditoria/` | Plan de pruebas de la auditoría y sus resultados |
| `diagramas/` | Diagramas en draw.io |
| `evaluacion/` | Evaluación de la verificación automática |

El brief, el alcance y las reglas del proyecto están en [docs/PROYECTO.md](docs/PROYECTO.md).
