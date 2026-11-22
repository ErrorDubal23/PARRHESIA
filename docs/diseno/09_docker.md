# Docker: despliegue, persistencia y resistencia a fallos

Versión 1 (21 nov 2026). Todo se levanta con `docker compose up -d --build` y la aplicación queda en <http://localhost:8080>.

## Contenedores

| Contenedor | Qué es | Rol de PostgreSQL | Si se detiene… |
| --- | --- | --- | --- |
| `db` | PostgreSQL 17, fuente de verdad (volumen `pgdata`) | `app` (superusuario, solo para preparar) | Las escrituras fallan con un mensaje claro; nada se pierde. Al volver, todo sigue donde estaba |
| `neo4j` | Neo4j 5.26, proyección de la red (volumen `neo4jdata`) | — | El feed sigue desde PostgreSQL (`"fuente": "respaldo"`); los eventos esperan en el outbox. Al volver, el grafo se pone al día solo |
| `preparar` | Aplica las migraciones y pone las contraseñas de los roles. Corre una vez y termina | `app` | — |
| `social` | API de la red social | `svc_social` | Esa sección responde 503; el resto sigue |
| `verificacion` | API de verificación | `svc_verificacion` | Esa sección responde 503; publicar y el feed siguen |
| `verificacion-trabajador` | Filtro, consenso, motor y explicación | `svc_verificacion` | Las publicaciones quedan "pendiente"; al volver, se verifican |
| `ia-trabajador` | Llama a Groq y OpenRouter | `svc_ia` | Los trabajos esperan en `ia.trabajo`; al volver, se resuelven |
| `temas`, `temas-trabajador` | Temas del día | `svc_temas` | Se ven los temas ya calculados; la recolección se retoma al volver |
| `oficial` | API de datos oficiales | `svc_oficial` | Esa sección responde 503 |
| `grafo`, `grafo-trabajador` | Consultas y sincronización de Neo4j | `svc_grafo` | Igual que si se detiene Neo4j |
| `puerta` | Nginx, la única entrada (puerto 8080) | — | La app no se alcanza desde afuera; los servicios siguen trabajando por dentro |

Todos tienen `restart: unless-stopped`: si se reinicia el computador o Docker, vuelven a arrancar solos, en orden (las APIs esperan a que la base esté sana y a que `preparar` termine).

## Por qué no se pierde nada

- **Los datos no viven en los contenedores.** Viven en los volúmenes `pgdata`, `neo4jdata` y `fotos` (fotos de perfil). Un contenedor se puede borrar y volver a crear: el volumen sigue ahí.
- **Las escrituras son transacciones.** Una publicación y su evento del outbox se guardan juntos, o ninguno.
- **Lo que está a medio camino espera en PostgreSQL.** Eventos sin aplicar en el grafo (`entrega_evento`), trabajos de IA en cola (`ia.trabajo`), textos por verificar: todo está en tablas, no en memoria.
- **Neo4j se puede reconstruir desde cero** con `POST /v1/reconstruir` del servicio de grafo (vuelve a aplicar todo el outbox).

## Guion para la sustentación

Probado el 21 nov 2026.

| Paso | Comando | Lo que se ve |
| --- | --- | --- |
| 1. Persistencia | `docker compose down` y luego `docker compose up -d` | Los mismos usuarios, publicaciones, verificaciones y datos oficiales; se puede iniciar sesión con la misma cuenta |
| 2. Se cae la base de grafos | `docker compose stop neo4j`, publicar y abrir el feed | Publicar funciona; el feed sale de PostgreSQL. Con `docker compose start neo4j`, la publicación aparece en el grafo sin hacer nada |
| 3. Se cae la IA | `docker compose stop ia-trabajador` y publicar una cifra | Queda "verificación pendiente". Con `docker compose start ia-trabajador`, se verifica sola |
| 4. Se cae un servicio | `docker compose stop verificacion` | Esa sección responde 503 con un mensaje claro; la red social sigue funcionando |
| 5. Se pierde el grafo | Vaciar Neo4j y `POST /v1/reconstruir` | El mismo grafo, reconstruido desde PostgreSQL |

**Nunca usar `docker compose down -v` en la presentación:** `-v` borra los volúmenes, es decir, los datos.

## Seguridad del acceso (migración 0012)

- **Sesión en cookie `HttpOnly`, `SameSite=Strict`**, 8 horas. Ningún script de la página puede leer el token (no hay token en `localStorage`). `Secure` se activa con `COOKIE_SEGURA=true` cuando haya HTTPS.
- **Sesiones en el servidor.** El token lleva un `jti`; en cada petición el servicio llama `social.sesion_activa(jti)`, que exige sesión no revocada, no vencida y cuenta activa. Cerrar sesión la revoca en la base: una copia del token deja de servir (401). Suspender una cuenta corta el acceso al instante.
- **Escrituras con cookie exigen el encabezado `X-Parrhesia: 1`** (protección CSRF además de `SameSite`).
- **Intentos limitados:** 5 fallos por correo o 20 por origen en 15 minutos → 429, en la base; además Nginx limita `/sesiones` y `/cuentas` a 10 por minuto por IP.
- **No revela si un correo existe:** correo desconocido y contraseña errada responden igual y tardan lo mismo (se verifica contra un hash de relleno).
- **Contraseñas:** argon2id; se rechazan las comunes o las que contienen el nombre de usuario o el correo.
- **Cabeceras:** CSP estricta (`script-src 'self'`, sin scripts en línea), `X-Frame-Options DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`. Tras entrar, solo se redirige a rutas internas.
- **Varias pestañas:** al salir en una, las demás se enteran (`BroadcastChannel`).

Probado por la puerta (21 nov 2026): la cookie llega `HttpOnly` y `SameSite=Strict`, `/yo` 200, escritura sin encabezado 403, salir 204, la cookie copiada después de salir 401, sexto intento fallido 429.

## Pruebas automáticas y Neo4j

Las pruebas del grafo vacían Neo4j en cada prueba, así que usan **un Neo4j aparte** (perfil `pruebas`, puerto 7688, sin volumen) y nunca el de desarrollo:

```bash
docker compose --profile pruebas up -d neo4j-pruebas
uv run pytest
```
