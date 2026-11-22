# Modelo de grafo (Neo4j) — proyecto final de Bases de Datos

Versión 2 (20 nov 2026). Neo4j 5.26 Community (implementado el 21 nov 2026 en `src/servicios/grafo/`). Diagramas: [diagramas/NEO4J_1 y NEO4J_2](../../diagramas/LEEME.md). Complementa el [MER](01_MER.md) y el [MR](02_MR.md). Nombres en español sin tildes (decisión 14, [glosario](glosario_codigo.md)).

## Papel del grafo

- **PostgreSQL es la fuente de verdad.** Neo4j guarda una **proyección** de la red social para las consultas de varios saltos, que en SQL necesitarían varias uniones recursivas: el feed, a quién seguir, la difusión de una publicación y las tendencias por diversidad.
- **El grafo no se edita directamente.** Solo lo escribe el servicio de grafo, a partir de los eventos de `social.evento_salida` y `verificacion.evento_salida`. Si Neo4j se pierde, se reconstruye completo desde PostgreSQL.
- **No guarda contraseñas, correos ni etiquetas políticas.** Solo identificadores, nombres públicos, fechas y estados.

## Nodos

| Etiqueta | Propiedades | Restricción |
| --- | --- | --- |
| `Usuario` | `id`, `nombre_usuario`, `estado`, `creado_en` | `id` único |
| `Publicacion` | `id`, `estado`, `creado_en` | `id` único |
| `Etiqueta` | `nombre` | `nombre` único |
| `Figura` | `id`, `nombre_completo` | `id` único |
| `Serie` | `codigo`, `indicador` | `codigo` único |

```cypher
CREATE CONSTRAINT usuario_id IF NOT EXISTS FOR (u:Usuario) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT publicacion_id IF NOT EXISTS FOR (p:Publicacion) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT etiqueta_nombre IF NOT EXISTS FOR (e:Etiqueta) REQUIRE e.nombre IS UNIQUE;
CREATE CONSTRAINT figura_id IF NOT EXISTS FOR (f:Figura) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT serie_codigo IF NOT EXISTS FOR (s:Serie) REQUIRE s.codigo IS UNIQUE;
CREATE INDEX publicacion_creado_en IF NOT EXISTS FOR (p:Publicacion) ON (p.creado_en);
```

## Relaciones

| Relación | Desde → hasta | Propiedades | Origen en PostgreSQL |
| --- | --- | --- | --- |
| `SIGUE` | `Usuario` → `Usuario` | `desde` | `social.seguimiento` |
| `PUBLICO` | `Usuario` → `Publicacion` | | `social.publicacion.autor_id` |
| `RESPONDE_A` | `Publicacion` → `Publicacion` | | `social.publicacion.responde_a_id` |
| `COMPARTE` | `Publicacion` → `Publicacion` | | `social.publicacion.comparte_id` |
| `REACCIONO` | `Usuario` → `Publicacion` | `tipo`, `en` | `social.reaccion` |
| `ETIQUETADA_CON` | `Publicacion` → `Etiqueta` | | `social.publicacion_etiqueta` |
| `MENCIONA` | `Publicacion` → `Figura` o `Usuario` | | `social.mencion_figura`, `social.mencion_usuario` |
| `VERIFICADA_CON` | `Publicacion` → `Serie` | `conclusion` | `verificacion.verificacion` (vigente) |

```
(Usuario)-[:SIGUE]->(Usuario)
(Usuario)-[:PUBLICO]->(Publicacion)-[:ETIQUETADA_CON]->(Etiqueta)
(Publicacion)-[:RESPONDE_A]->(Publicacion)
(Publicacion)-[:COMPARTE]->(Publicacion)
(Usuario)-[:REACCIONO]->(Publicacion)
(Publicacion)-[:MENCIONA]->(Figura)
(Publicacion)-[:VERIFICADA_CON]->(Serie)
```

## Sincronización desde PostgreSQL (transactional outbox)

1. Cuando el servicio social publica, sigue o reacciona, un **trigger** inserta el evento en `social.evento_salida` **dentro de la misma transacción**. Si la transacción falla, tampoco queda el evento. Lo mismo hace el servicio de verificación en `verificacion.evento_salida`.
2. El servicio de grafo lee en orden de `id` los eventos que todavía no tienen su fila en `entrega_evento` con `consumidor = 'grafo'` (decisión 18; el servicio de verificación lee los mismos outbox con su propio consumidor). Aplica cada uno en Neo4j con `MERGE`, que es idempotente: aplicar un evento dos veces no lo duplica.
3. Al aplicarlo, inserta su fila en `entrega_evento`. Si Neo4j está caído, los eventos esperan y nada se pierde. Los eventos que no son de la red (`declaracion_creada`, `declaracion_reportada_creada`) el grafo los ignora.

| Evento | Cypher que aplica |
| --- | --- |
| `usuario_creado` | `MERGE (u:Usuario {id: $id}) SET u.nombre_usuario = $nombre_usuario, u.estado = $estado, u.creado_en = datetime($creado_en)` |
| `usuario_cambio_estado` | `MATCH (u:Usuario {id: $id}) SET u.estado = $estado` |
| `usuario_actualizado` (0014) | `MERGE (u:Usuario {id: $id}) SET u.nombre_usuario = $nombre_usuario` (cuando cambia el nombre de usuario) |
| `seguimiento_creado` | `MATCH (a:Usuario {id: $seguidor}), (b:Usuario {id: $seguido}) MERGE (a)-[s:SIGUE]->(b) SET s.desde = datetime($en)` |
| `seguimiento_borrado` | `MATCH (:Usuario {id: $seguidor})-[s:SIGUE]->(:Usuario {id: $seguido}) DELETE s` |
| `publicacion_creada` | `MERGE` de la `Publicacion`, su `PUBLICO` y su `RESPONDE_A` o `COMPARTE` |
| `publicacion_etiquetada` | `MATCH (p:Publicacion {id: $publicacion}) MERGE (e:Etiqueta {nombre: $etiqueta}) MERGE (p)-[:ETIQUETADA_CON]->(e)` |
| `publicacion_menciona` | `MERGE` de `MENCIONA` hacia la `Figura` o el `Usuario` mencionado |
| `figura_creada` | `MERGE (f:Figura {id: $id}) SET f.nombre_completo = $nombre_completo` |
| `publicacion_retirada` | `MATCH (p:Publicacion {id: $id}) SET p.estado = $estado` (no se borra: se conserva la difusión) |
| `reaccion_puesta` / `reaccion_quitada` | `MERGE` o `DELETE` de `REACCIONO` con su `tipo` |
| `verificacion_publicada` (viene de `verificacion.evento_salida`) | `MERGE (p)-[v:VERIFICADA_CON]->(s:Serie {codigo: $serie})` con `v.conclusion` |

## Las cuatro consultas que justifican el grafo

### 1. Feed: personas que sigo y las que siguen ellas

```cypher
CALL {
  MATCH (yo:Usuario {id: $yo})-[:SIGUE]->(a:Usuario)-[:PUBLICO]->(p:Publicacion)
  RETURN p, a, 1 AS distancia
  UNION
  MATCH (yo:Usuario {id: $yo})-[:SIGUE]->(:Usuario)-[:SIGUE]->(a:Usuario)-[:PUBLICO]->(p:Publicacion)
  WHERE a.id <> $yo AND NOT (yo)-[:SIGUE]->(a)
  RETURN p, a, 2 AS distancia
}
WITH p, a, min(distancia) AS distancia
WHERE p.estado = 'visible' AND p.creado_en >= datetime() - duration('P7D')
RETURN p.id AS publicacion_id, a.nombre_usuario AS autor, distancia
ORDER BY distancia, p.creado_en DESC
LIMIT 50
```

El servicio social completa el texto y los contadores de cada publicación con una consulta a PostgreSQL por los `id` devueltos.

### 2. A quién seguir: amigos de mis amigos

```cypher
MATCH (yo:Usuario {id: $yo})-[:SIGUE]->(f:Usuario)-[:SIGUE]->(s:Usuario)
WHERE s.id <> $yo AND s.estado = 'activo' AND NOT (yo)-[:SIGUE]->(s)
RETURN s.id AS usuario_id, s.nombre_usuario AS nombre_usuario, count(DISTINCT f) AS en_comun
ORDER BY en_comun DESC
LIMIT 10
```

### 3. Difusión de una publicación

```cypher
MATCH ruta = (origen:Publicacion {id: $publicacion})<-[:COMPARTE*1..10]-(c:Publicacion)
MATCH (u:Usuario)-[:PUBLICO]->(c)
RETURN c.id AS compartida_id, u.nombre_usuario AS compartida_por, length(ruta) AS profundidad
ORDER BY profundidad
```

Muestra el árbol de quién compartió a quién, hasta 10 niveles. Con `count(DISTINCT u)` se obtiene el alcance.

### 4. Tendencias por diversidad

Una etiqueta sube más cuando la usan personas que **no** están conectadas entre sí, así un grupo cerrado no puede inflar una tendencia. No necesita saber de qué lado político está nadie: solo mira la estructura de la red.

```cypher
MATCH (e:Etiqueta)<-[:ETIQUETADA_CON]-(p:Publicacion)<-[:PUBLICO]-(a:Usuario)
WHERE p.creado_en >= datetime($desde) AND p.creado_en < datetime($hasta)
  AND p.estado = 'visible'
  AND a.estado = 'activo'
  AND a.creado_en < datetime($desde) - duration('P7D')   // las cuentas nuevas no cuentan
WITH e, collect(DISTINCT a) AS autores, count(DISTINCT p) AS publicaciones
WHERE size(autores) >= 3
CALL {
  WITH autores
  UNWIND autores AS x
  MATCH (x)-[:SIGUE]->(y:Usuario)
  WHERE y IN autores
  RETURN count(*) AS enlaces
}
WITH e, publicaciones, size(autores) AS n, enlaces
WITH e, publicaciones, n, 1.0 - toFloat(enlaces) / (n * (n - 1)) AS diversidad
RETURN e.nombre AS etiqueta, publicaciones, n AS autores, diversidad, publicaciones * diversidad AS puntaje
ORDER BY puntaje DESC
LIMIT 10
```

`diversidad` va de 0 (todos los autores se siguen entre sí) a 1 (ninguno sigue a otro). El servicio de grafo guarda el resultado de cada ventana en `social.tendencia` con `social.registrar_tendencias`, así que la historia de las tendencias queda en PostgreSQL.

## Cómo se ve en la presentación

Neo4j Browser (`http://localhost:7474`) dibuja el grafo en vivo. Por ejemplo, la difusión de una publicación:

```cypher
MATCH ruta = (:Publicacion {id: $publicacion})<-[:COMPARTE*1..5]-(:Publicacion)<-[:PUBLICO]-(:Usuario)
RETURN ruta
```


## Comunidades y descubrimiento (T11, decisión 28)

El grafo proyecta solo lo necesario para descubrir. Papeles, permisos y solicitudes viven únicamente en
PostgreSQL (una copia se desincronizaría); el interés de una persona no se guarda: se deduce de las
etiquetas de lo que publica o a lo que reacciona.

```
(:Comunidad {id, nombre, privacidad, creada_en})
(Usuario)-[:INTEGRA {desde}]->(Comunidad)
(Publicacion)-[:EN]->(Comunidad)
```

| Evento del outbox de social | Cypher |
| --- | --- |
| `comunidad_creada` / `comunidad_actualizada` | `MERGE (c:Comunidad {id}) SET c.nombre, c.privacidad` |
| `integrante_agregado` | `MERGE (u)-[:INTEGRA]->(c)` |
| `integrante_quitado` | `MATCH (u)-[i:INTEGRA]->(c) DELETE i` |
| `publicacion_en_comunidad` | `MERGE (p)-[:EN]->(c)` |

**Privacidad en el grafo:** lo publicado en una comunidad privada no alimenta tendencias, sugerencias ni
el feed de quien no es integrante (`NOT (p)-[:EN]->(:Comunidad {privacidad: 'privada'})`). Si una
comunidad cambia de privacidad, el nodo se actualiza y los filtros la aplican de inmediato.

**Consultas de descubrimiento, sin burbujas** (`servicios/grafo/consultas.py`):

| Consulta | Qué devuelve | Cómo evita la burbuja |
| --- | --- | --- |
| `COMUNIDADES_RECOMENDADAS` | Comunidades públicas con mis temas, que aún no integro | Pesa más la que tiene integrantes fuera de mi red (ni los sigo, ni me siguen, ni a dos pasos) |
| `COMUNIDADES_RELACIONADAS` | Otras comunidades públicas con los mismos temas | Primero las que comparten menos integrantes: el mismo asunto desde otros grupos |
| `OTRAS_VOCES` | Personas que hablan de mis temas | Solo personas fuera de mi red cercana (lo contrario de "amigos de amigos") |

Ninguna mira el lado político de nadie: solo etiquetas y estructura de la red. Probado en `tests/test_grafo.py`
(proyección, reconstrucción idéntica, privacidad y orden de las sugerencias).
