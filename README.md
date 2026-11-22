# Parrhesia · Red social con el dato oficial al lado

Proyecto final de Bases de Datos. Una red social colombiana donde cualquiera publica su opinión y donde cada
publicación que cita una cifra pública (inflación, desempleo, homicidios…) queda unida al dato oficial completo.
El sistema no dice "verdadero" o "falso": dice si la conclusión **se sostiene**, **se debilita**, **se invierte**
o si **no hay dato comparable**, con la misma regla para todos.

**Tecnologías:** PostgreSQL 17 · Neo4j 5 · Python (FastAPI) · React + TypeScript · Nginx · Docker.

---

## En una frase

La página web habla con una sola puerta de entrada (Nginx); detrás hay seis servicios pequeños en Python, y
todos guardan en **PostgreSQL**, que es la fuente de verdad. **Neo4j** es una copia de la red (quién sigue a quién,
qué se comparte) que se alimenta sola desde PostgreSQL y sirve para el inicio, las tendencias y las sugerencias.

## Qué se puede hacer

| Función | En la página |
|---|---|
| Red social | Crear cuenta, publicar, responder, compartir, reaccionar, etiquetas (#), mencionar (@), seguir, comunidades públicas y privadas |
| Verificación automática | Si una publicación cita una cifra, aparece sola la conclusión con el dato oficial, la fuente y cómo comprobarlo |
| Temas del día y tendencias | Lo que cubren varios medios hoy y las etiquetas que más usan personas que no se siguen entre sí |
| Figuras públicas | Ficha con el cargo y su fuente, y sus declaraciones con cifras, verificadas |
| Datos oficiales | Cada serie con su fuente, sus notas y el archivo original |
| Analizar un enlace | Pegar una noticia de otra red: se revisan sus cifras con el mismo motor |

## Las herramientas y cómo se conectan

| Herramienta | Qué es | Para qué la usamos | Se conecta con |
|---|---|---|---|
| **PostgreSQL 17** | Base de datos relacional | Todo lo importante: cuentas, publicaciones, datos oficiales, verificaciones. Reglas en la base: procedimientos, triggers, restricciones, tablas de solo inserción y un rol con permisos mínimos por servicio | Los servicios, por la red interna de Docker. Desde el computador, puerto 5433 |
| **Neo4j 5** | Base de datos de grafos | La red: seguimientos, compartidas, comunidades. Calcula el inicio, las tendencias y a quién seguir | Servicio de grafo (puerto 7687). Neo4j Browser en el puerto 7474 |
| **Outbox** | Tabla de eventos en PostgreSQL | Cada cambio queda anotado en la misma transacción; Neo4j y la verificación lo leen después. Si algo se cae, no se pierde nada | PostgreSQL → servicios de grafo y verificación |
| **FastAPI (Python)** | Servicios web | Seis servicios: social, verificación, datos oficiales, temas del día, IA y grafo | PostgreSQL y Neo4j |
| **Nginx** | Puerta de entrada | La página y la API salen por un solo puerto (8080); los servicios no se ven desde fuera | Navegador y servicios |
| **React + TypeScript** | La página web | Todo lo que se ve | Nginx |
| **IA (Groq y Gemini)** | Modelos de lenguaje | Solo leen el texto y extraen la cifra. Los números, la comparación y la conclusión salen de la base y de reglas fijas | Servicio de IA (opcional: sin llaves, las verificaciones quedan pendientes) |
| **Docker Desktop** | Programa que corre aplicaciones empaquetadas | Encender todo con un comando, sin instalar PostgreSQL ni Neo4j a mano | Todos los contenedores |

## Qué hay en cada carpeta

| Carpeta | Qué contiene |
|---|---|
| `db/migrations/` | La base de datos, en scripts numerados (tablas, restricciones, procedimientos, triggers, permisos). [db/LEEME.md](db/LEEME.md) explica cada uno |
| `db/semillas/`, `db/consola/` | Datos de demostración y tareas de administración |
| `diagramas/` | MER (notación de Chen), modelo relacional y grafo, en `.png` y `.drawio` |
| `docs/diseno/` | Diseño del proyecto: MER, modelo relacional, grafo, lógica de la base, APIs, Docker |
| `src/servicios/` | Los microservicios |
| `src/app/` | Conectores de datos oficiales (DANE, Banco de la República, Policía) |
| `web/` | La página web |
| `gateway/` | La puerta de entrada (Nginx) |
| `catalog/`, `evidence/` | Fichas aprobadas de cada serie oficial y evidencia de las fuentes |
| `tests/` | Pruebas automáticas |

---

## Requisitos

| Programa | Nota |
|---|---|
| **Docker Desktop** | <https://www.docker.com/products/docker-desktop/>. En Windows, al instalarlo deja marcado *Use WSL 2*; si lo pide, reinicia el computador. Antes de seguir, ábrelo y espera a que diga *Engine running* |
| **Git** | En Windows, *Git for Windows* (trae *Git Bash*) |
| **uv** | Instala Python y las librerías del proyecto solo. Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` · Mac: `curl -LsSf https://astral.sh/uv/install.sh \| sh`. Cierra y vuelve a abrir la terminal después de instalarlo |

No hace falta instalar PostgreSQL, Neo4j, Node ni Python a mano: Docker y uv se encargan.

---

## Correr el proyecto en local

Los comandos son los mismos en Windows (PowerShell o Git Bash) y en Mac (Terminal).

### 1. Descargar el proyecto

```bash
git clone <url-del-repositorio>
cd <carpeta-del-repositorio>
```

### 2. Crear el archivo `.env`

```bash
uv run python scripts/preparar_env.py
```

Crea el `.env` con contraseñas al azar para la base, Neo4j y los servicios. Nunca sobrescribe uno que ya
exista. La primera vez, uv descarga Python y las librerías (tarda un poco).

### 3. Encender todo

```bash
docker compose up -d --build
```

La primera vez tarda varios minutos: construye las imágenes, crea la base con todas las migraciones y los roles.
Para ver que todo esté arriba: `docker compose ps` (todos en *running* o *healthy*).

### 4. Cargar los datos oficiales

```bash
uv run python -m app.runs dane --db
```

Descarga del DANE y del Banco de la República la inflación y el desempleo, los contrasta y los guarda.
(Los homicidios, `uv run python -m app.runs homicides --db`, necesitan un token gratuito de datos.gov.co en
`SOCRATA_APP_TOKEN`).

### 5. Cargar la demostración

```bash
uv run python db/semillas/demo.py
uv run python db/semillas/demo.py --fotos
```

Crea 40 personas ficticias, 11 comunidades y unas 400 publicaciones con debates. **Al terminar imprime la
contraseña de las cuentas de la demo: anótala.**

### 6. Abrir la página

<http://localhost:8080>

---

## Usuarios de prueba

Todas las cuentas de la demo usan la contraseña que imprimió el paso 5. El correo es
`<usuario>@demo.parrhesia.local`.

| Usuario | Correo |
|---|---|
| `laura_castano` | `laura_castano@demo.parrhesia.local` |
| `alejandro_pineda` | `alejandro_pineda@demo.parrhesia.local` |
| `camila_ortega` | `camila_ortega@demo.parrhesia.local` |

También puedes crear tu propia cuenta en *Crear cuenta*. Para que sea **administradora** (registra figuras
públicas y asigna verificadores en la página *Equipo*):

```bash
uv run python db/consola/asignar_rol.py --usuario <tu_usuario> --rol admin --motivo "Administrador de mi copia local."
```

Con tu cuenta de administrador puedes cargar las figuras públicas y sus declaraciones reales:

```bash
uv run python db/semillas/figuras.py --verificador <tu_usuario>
uv run python db/semillas/declaraciones.py --verificador <tu_usuario>
```

---

## Verificación automática (opcional)

Sin llaves de IA la red social funciona completa, pero las publicaciones con cifras se quedan en
"verificación pendiente". Para activarla, pon en el `.env` una llave gratuita de
[Groq](https://console.groq.com) (`GROQ_KEY_groq_cuenta_1=`) y una de
[Gemini](https://aistudio.google.com) (`GEMINI_KEY_gemini_1=`), y reinicia los trabajadores:

```bash
docker compose up -d ia-trabajador verificacion-trabajador
```

---

## Apagar y volver a encender

```bash
docker compose stop        # apaga todo; los datos quedan guardados
docker compose start       # lo vuelve a encender otro día
```

**Nunca uses `docker compose down -v`**: la `-v` borra los datos.

## Problemas comunes

| Lo que pasa | Qué hacer |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop no está abierto: ábrelo y espera *Engine running* |
| `port is already allocated` (8080 o 5433) | Otro programa usa ese puerto: en `.env` cambia `PUERTO_APP=8081` o `POSTGRES_PORT=5434` y repite el paso 3 |
| `uv` no se reconoce | Cierra y vuelve a abrir la terminal después de instalarlo |
| La página dice que una parte no está disponible | Ese servicio está arrancando: espera un minuto o mira `docker compose ps` |

## Pruebas automáticas

```bash
docker compose --profile pruebas up -d neo4j-pruebas
uv run pytest
```

Las pruebas crean una base temporal con todas las migraciones y la borran al terminar: la base real no se toca.
