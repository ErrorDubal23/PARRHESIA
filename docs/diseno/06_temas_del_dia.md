# Temas del día: de qué se está hablando y qué dicen los datos

Versión 1 (21 nov 2026). Decisión 17 ([00_decisiones.md](00_decisiones.md)). Es la parte central de la funcionalidad 3 del brief (tendencias). Complementa el [MR](02_MR.md), la [lógica de la base](05_logica_bd.md) y el [servicio de IA](03_servicio_ia.md).

## Qué ve el usuario

La página principal muestra los **5 a 7 temas de los que más medios están hablando**. Cada tema tiene:

1. **Un título neutral** (por ejemplo, "Reforma tributaria") y los artículos que lo forman, con su medio y su enlace.
2. **Lo que se dijo con cifras.** Cada declaración aparece como la reporta el medio: *"Según El Tiempo (20 nov), Fulano dijo: '…el desempleo bajó al 8 %…'"*, con el texto exacto y el enlace.
3. **Lo que dicen los datos**, junto a cada declaración: el dato oficial, la conclusión (se sostiene, se debilita, se invierte o sin dato comparable) y la explicación. La explicación dice qué pasa con el dato, por ejemplo: "la cifra corresponde a otro periodo", "el valor es nominal y la comparación necesita el real" o "el valor citado no coincide con el oficial".
4. **Un resumen en conteos**: cuántas declaraciones con cifras tiene el tema y cómo quedaron.
5. **Lo que se dice en la red:** publicaciones de los usuarios con la etiqueta del tema, cada una con su verificación, y un botón para opinar sobre el tema.

"Se saca de contexto" son las pruebas de robustez (periodo limitado, nominal frente a real, variante equivocada, dato provisional, nota de la serie). "Se alteró la cifra" es un valor citado que no coincide con el oficial. Nunca se dice "mentira" ni se juzga la intención de nadie.

**Límite de la v1:** solo se verifican cifras de los 8 indicadores. Una afirmación que se tendría que contrastar con un documento firmado (un decreto, una ley o una votación) se muestra con "sin dato comparable con los datos registrados". El contraste con registros oficiales está en el backlog.

## Flujo

```
medios (RSS) ──► servicio de temas ──► temas.articulo
                       │
                       ├─► ia.trabajo "agrupar_temas" ──► temas.tema + temas.tema_articulo
                       │        (la IA agrupa; la base cuenta medios y ordena)
                       │
                       └─► ia.trabajo "extraer_declaraciones" ──► temas.declaracion_reportada
                                (la base revisa que la cita esté textual en el artículo)
                                            │  temas.evento_salida
                                            ▼
                         servicio de verificación (el mismo motor de las publicaciones)
```

1. **Recolección** (cada 3 horas): el servicio de temas lee el RSS de cada medio registrado y guarda los artículos nuevos con `temas.registrar_articulos`. Un artículo repetido (misma URL) se ignora. Se guarda el título, el resumen y, si el medio lo permite en su `robots.txt`, el texto del artículo. El texto se usa solo para verificar las citas; la app muestra el fragmento citado y el enlace al medio, nunca el artículo completo.
2. **Agrupación** (una llamada a la IA por ventana): la IA recibe los títulos y resúmenes de las últimas 24 horas y devuelve grupos: un título neutral y los `id` de los artículos de cada grupo. **La IA no cuenta ni ordena:** `temas.registrar_temas` calcula en la base cuántos medios distintos tiene cada grupo, descarta los que tienen menos de 3 y guarda los 7 primeros.
3. **Extracción** (una llamada por tema): la IA lee los artículos del tema y devuelve las declaraciones con cifras: quién lo dijo, como lo nombra el artículo, y la cita exacta. Un trigger rechaza la cita si no está **textualmente** en el artículo guardado. Así la IA no puede atribuirle a nadie una frase que no está en la fuente.
4. **Verificación:** cada declaración nueva genera el evento `declaracion_reportada_creada`. El servicio de verificación la procesa igual que una publicación: extrae las afirmaciones, las une a la serie oficial, aplica las pruebas, saca la conclusión y redacta la explicación con el validador de cifras.

**Costo de IA:** una llamada de agrupación cada 3 horas y una de extracción por tema nuevo, más la verificación de las declaraciones con cifras. Del orden de decenas de miles de tokens al día. La caché de `ia.trabajo` evita repetir un trabajo con la misma entrada.

**Filtro previo sin IA** (para temas y publicaciones): solo pasa a la IA un texto que tenga al menos una cifra y una palabra clave de los 8 indicadores (`verificacion.palabra_clave`). Así, una opinión sin cifras no gasta tokens.

## Medios

La lista de medios es pública y se registra en `temas.medio`. Se elige con medios de distintas líneas editoriales y se aplica la misma regla a todos. Lista inicial aprobada el 21 nov 2026, abierta a cambios (se confirma que cada medio tenga RSS al implementar): El Tiempo, El Espectador, Semana, La Silla Vacía, Caracol Radio, Blu Radio, Portafolio, La República, Infobae Colombia y RTVC Noticias. Si el RSS no alcanza, GDELT (gratis) es el segundo canal (`canal = 'gdelt'`).

## Modelo de datos: esquema `temas`

### `temas.medio`
| Columna | Tipo | Restricciones |
| --- | --- | --- |
| `id` | uuid | **PK** |
| `nombre` | text | NN, **UK** |
| `url_sitio` | text | NN |
| `canal` | text | NN, `CHECK (canal IN ('rss','gdelt'))` |
| `url_canal` | text | NN (la dirección del RSS o la consulta de GDELT) |
| `habilitado` | boolean | NN |
| `creado_en`, `actualizado_en` | timestamptz | NN |

### `temas.articulo`
| Columna | Tipo | Restricciones |
| --- | --- | --- |
| `id` | uuid | **PK** |
| `medio_id` | uuid | NN, **FK** → `medio.id` |
| `url` | text | NN, **UK** |
| `titulo` | text | NN |
| `resumen` | text | |
| `texto` | text | Nulo si el medio no permite leer el artículo |
| `publicado_en` | timestamptz | NN |
| `huella` | text | NN (sha256 de título, resumen y texto) |
| `creado_en` | timestamptz | NN |

Índice en `(publicado_en)`. Solo inserción.

### `temas.tema`
| Columna | Tipo | Restricciones |
| --- | --- | --- |
| `id` | uuid | **PK** |
| `ventana_inicio`, `ventana_fin` | timestamptz | NN, `CHECK (ventana_fin > ventana_inicio)` |
| `titulo` | text | NN, sin cifras (lo revisa un trigger: un título con números podría colar un dato) |
| `etiqueta` | text | NN, la etiqueta con la que los usuarios publican sobre el tema (por ejemplo `reformatributaria`) |
| `total_articulos`, `total_medios` | integer | NN; los calcula la base, no la IA |
| `posicion` | smallint | NN, `CHECK (posicion BETWEEN 1 AND 7)` |
| `trabajo_ia_id` | uuid | Referencia a `ia.trabajo.id` (la agrupación) |
| `creado_en` | timestamptz | NN |

**UK** (`ventana_inicio`, `ventana_fin`, `posicion`). `CHECK (total_medios >= 3)`. Solo inserción: cada ventana queda guardada.

### `temas.tema_articulo`
| Columna | Tipo | Restricciones |
| --- | --- | --- |
| `tema_id` | uuid | **PK**, **FK** → `tema.id` |
| `articulo_id` | uuid | **PK**, **FK** → `articulo.id` |

### `temas.declaracion_reportada`
| Columna | Tipo | Restricciones |
| --- | --- | --- |
| `id` | uuid | **PK** |
| `articulo_id` | uuid | NN, **FK** → `articulo.id` |
| `actor` | text | NN, como lo nombra el artículo |
| `figura_id` | uuid | Referencia a `social.figura_publica.id` si el actor es una figura registrada (revisada por trigger); nulo si no |
| `texto_citado` | text | NN, el fragmento exacto del artículo |
| `trabajo_ia_id` | uuid | Referencia a `ia.trabajo.id` (la extracción) |
| `creado_en` | timestamptz | NN |

**UK** (`articulo_id`, `texto_citado`). Solo inserción.

### `temas.evento_salida` y `temas.entrega_evento`

Misma estructura que en `social` (ver la decisión 18 abajo). Lleva `declaracion_reportada_creada` al servicio de verificación.

### Cambios en otros esquemas

- `verificacion.afirmacion` gana `declaracion_reportada_id` (referencia lógica a `temas.declaracion_reportada`). El arco exclusivo pasa a `CHECK (num_nonnulls(publicacion_id, declaracion_id, declaracion_reportada_id) = 1)`.
- `verificacion.palabra_clave` (nueva): `codigo_indicador`, `palabra`, **PK** compuesta. Por ejemplo, `unemployment`: "desempleo", "desocupación", "tasa de desempleo". La usa el filtro previo.
- `ia.trabajo.tipo` suma `agrupar_temas` y `extraer_declaraciones`.

## Entrega de eventos por consumidor (decisión 18)

Ahora un mismo outbox tiene **más de un lector**: el servicio de grafo y el de verificación leen `social.evento_salida`. Una sola columna `aplicado_en` ya no alcanza, porque el primero que la llena le escondería el evento al otro. Por eso cada esquema con outbox tiene además una tabla de entregas:

| Tabla | Columnas | Restricciones |
| --- | --- | --- |
| `<esquema>.entrega_evento` | `evento_id`, `consumidor`, `entregado_en` | **PK** (`evento_id`, `consumidor`); **FK** `evento_id` → `evento_salida.id`; `CHECK (consumidor IN ('grafo','verificacion'))`. Solo inserción |

Un consumidor lee sus pendientes con:

```sql
SELECT e.* FROM social.evento_salida e
WHERE e.tipo_evento = ANY ($tipos)
  AND NOT EXISTS (SELECT 1 FROM social.entrega_evento d
                  WHERE d.evento_id = e.id AND d.consumidor = $consumidor)
ORDER BY e.id
LIMIT 100;
```

y, después de procesar cada evento, inserta su fila en `entrega_evento`. No se usa un "último `id` leído", porque los `id` se asignan al insertar y no al confirmar: una transacción lenta puede confirmar un `id` menor después de que el consumidor ya pasó de largo.

| Outbox | Lo lee | Eventos |
| --- | --- | --- |
| `social.evento_salida` | `grafo` | Todos los de la red |
| `social.evento_salida` | `verificacion` | `publicacion_creada`, `declaracion_creada` |
| `verificacion.evento_salida` | `grafo` | `verificacion_publicada` |
| `temas.evento_salida` | `verificacion` | `declaracion_reportada_creada` |

## Procedimientos, funciones y triggers

| Objeto | Tipo | Qué hace |
| --- | --- | --- |
| `temas.registrar_articulos(medio_id, articulos jsonb)` | procedimiento | Inserta los artículos con `ON CONFLICT (url) DO NOTHING`, todos en una transacción. Devuelve cuántos son nuevos |
| `temas.articulos_ventana(desde, hasta)` | función `STABLE` | Los artículos de la ventana (`id`, medio, título y resumen): es la entrada del trabajo de agrupación |
| `temas.registrar_temas(ventana_inicio, ventana_fin, trabajo_ia_id, grupos jsonb)` | procedimiento | Recibe los grupos validados de la IA. Revisa que cada `id` de artículo exista y esté en la ventana, cuenta en la base los medios distintos de cada grupo, descarta los de menos de 3, ordena por medios distintos y luego por artículos, y guarda los 7 primeros con sus artículos. Todo o nada |
| `temas.registrar_declaraciones(articulo_id, trabajo_ia_id, declaraciones jsonb)` | procedimiento | Inserta las declaraciones extraídas. Busca la figura con `temas.buscar_figura`. Si una cita no pasa el trigger, se deshace todo el lote del artículo y el trabajo se marca con salida inválida |
| `temas.buscar_figura(actor)` | función `STABLE`, `SECURITY DEFINER` | El `id` de la figura registrada cuyo `nombre_completo` coincide con el actor (sin distinguir mayúsculas ni tildes); nulo si no hay una sola coincidencia exacta. No adivina |
| `temas.cobertura_tema(tema_id)` (0013) | función `STABLE` | Medios que cubren el tema, con sus artículos y la hora del primero: la "huella de cobertura" de la app |
| `temas.actividad_tema(tema_id, tramos)` (0013) | función `STABLE` | Artículos del tema por tramo de su ventana (8 de 3 horas); la suma siempre es el total del tema |
| `temas.pagina_tema(tema_id)` | función `STABLE` | Artículos, declaraciones y etiqueta del tema. La app la combina con `verificacion.resumen_conclusiones` y con las publicaciones de la etiqueta |
| `verificacion.requiere_extraccion(texto)` | función `STABLE` | El filtro previo: verdadero si hay al menos una cifra (`util.cifras_en_texto`) y una palabra de `verificacion.palabra_clave` |
| `declaracion_cita_textual` | trigger `BEFORE INSERT` en `declaracion_reportada` | `position(texto_citado IN titulo, resumen o texto del artículo) > 0`; si no aparece, error `cita_no_textual` |
| `tema_titulo_sin_cifras` | trigger `BEFORE INSERT` en `tema` | `cardinality(util.cifras_en_texto(titulo)) = 0` |
| `declaracion_figura_existe` | trigger `BEFORE INSERT` en `declaracion_reportada` | Si `figura_id` no es nulo, que exista en `social.figura_publica` |
| `declaracion_reportada_salida` | trigger `AFTER INSERT` | Inserta `declaracion_reportada_creada` en `temas.evento_salida` |
| `<tabla>_solo_insercion` | `articulo`, `tema`, `tema_articulo`, `declaracion_reportada`, `entrega_evento` | `util.prohibir_cambios()` |

`verificacion.cifras_en_texto` pasa a ser `util.cifras_en_texto`, porque ahora la usan dos esquemas.

## Para la materia

- **Transacciones:** `registrar_temas` y `registrar_declaraciones` son todo o nada; si una cita no es textual, no queda ninguna del lote.
- **Triggers como garantía contra la IA:** la cita textual y el título sin cifras se cumplen en la base, aunque el código del servicio tenga un error.
- **Microservicio nuevo** (`temas`) con su esquema y su rol (`svc_temas`), comunicado por outbox y por la cola de IA.
