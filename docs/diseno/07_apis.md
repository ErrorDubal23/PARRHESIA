# Contratos de las APIs de los microservicios

Versión 1 (21 nov 2026). Último documento del diseño: dice qué expone cada microservicio, qué recibe, qué devuelve y qué objeto de la base usa. Complementa la [lógica de la base](05_logica_bd.md), el [servicio de IA](03_servicio_ia.md), los [temas del día](06_temas_del_dia.md) y el [modelo de grafo](04_modelo_grafo.md).

## Decisiones nuevas (por aprobar)

| # | Decisión | Por qué |
| --- | --- | --- |
| 21 | Cada servicio tiene dos partes: una **API** (FastAPI) y, si la necesita, un **trabajador** (proceso que escucha `pg_notify` o corre por horario). Los dos usan el mismo rol de PostgreSQL | Separa lo que responde a la app de lo que trabaja en segundo plano; el trabajador puede caerse sin tumbar la API |
| 22 | La app habla solo con la **puerta de entrada (Nginx)**, que enruta `/api/<servicio>/v1/...`. Los servicios no se exponen afuera | Un solo punto de entrada, un solo dominio para la app web |
| 23 | **Sesión con JWT** firmado por el servicio social (HS256, secreto en el `.env`). Todos los servicios validan el token con el mismo secreto y leen el rol (`usuario`, `verificador`, `admin`). Contraseñas con argon2id | Ningún servicio tiene que llamar a otro para saber quién es el usuario |
| 24 | **Las cifras viajan como texto** en JSON (`"valor": "9.36"`), nunca como número | Un número en JSON se lee como `float` y puede perder decimales; el texto conserva el decimal exacto de la base |
| 25 | Entre servicios se prefiere **una función de la base autorizada** (las de la migración 0007) antes que una llamada HTTP. Solo hay HTTP entre servicios para Neo4j (social → grafo) | Menos piezas que pueden fallar; la base ya garantiza los permisos |

## Convenciones comunes

- **Rutas en español**, en minúsculas y con guiones: `/api/social/v1/publicaciones/{id}/reacciones`.
- **Formato:** JSON en UTF-8. Fechas en ISO 8601 con zona (`2026-11-21T14:30:00-05:00`). Identificadores `uuid`.
- **Paginación por cursor**, no por página: la respuesta trae `siguiente` (un texto opaco) y la petición lo devuelve en `?despues=`. Así el feed no repite ni salta publicaciones cuando entran nuevas.
- **Errores:** siempre con la misma forma. El `codigo` es el que lanza la base (`autor_inactivo`, `cita_no_textual`…); el servicio solo lo traduce a un estado HTTP y a un mensaje en español.

```json
{ "error": { "codigo": "publicacion_destino_no_visible", "mensaje": "La publicación fue retirada y ya no se puede responder." } }
```

| Origen del error | HTTP |
| --- | --- |
| Datos mal formados (validación de FastAPI) | 422 |
| `CHECK`, valor fuera de lo permitido | 422 |
| `UNIQUE` (correo o nombre de usuario repetido) | 409 |
| Códigos de procedimiento `*_inexistente`, `*_no_visible` | 404 |
| `sin_permiso`, rol insuficiente | 403 |
| Sin token o token vencido | 401 |
| Estado que no permite la acción (`alerta_no_abierta`, `no se permite pasar de…`) | 409 |

- **Salud:** cada servicio responde `GET /salud` con `{"estado": "ok", "base": "ok"}`, y el de grafo agrega `"neo4j"`. Docker Compose lo usa para saber si el servicio está listo.
- **Documentación automática:** FastAPI publica cada contrato en `/docs` (OpenAPI). Este documento es la versión para aprobar; el código no puede contradecirlo.
- **Lenguaje neutral:** la API devuelve códigos (`se_debilita`) y la app los muestra con el texto acordado ("La conclusión se debilita"). Nunca "falso", "mentira" ni "engaño".

## Mapa de servicios

| Servicio | Prefijo | Rol de PostgreSQL | Trabajador | Quién lo llama |
| --- | --- | --- | --- | --- |
| Social | `/api/social/v1` | `svc_social` | — | La app |
| Grafo | `/api/grafo/v1` (solo red interna) | `svc_grafo` | Sincronizador (outbox → Neo4j) y cálculo de tendencias cada hora | El servicio social |
| Verificación | `/api/verificacion/v1` | `svc_verificacion` | Lee los outbox de `social` y `temas`, aplica el filtro previo, encola a la IA y corre el motor de reglas | La app |
| IA | sin API pública | `svc_ia` | Toma trabajos de `ia.trabajo` y llama a Groq | Nadie: solo la cola |
| Temas | `/api/temas/v1` | `svc_temas` | Recolector de medios cada 3 horas, agrupación y extracción | La app |
| Datos oficiales | `/api/oficial/v1` | `svc_oficial` | Conectores una vez al día | La app |

```
              app web (React)
                    │  HTTPS
                    ▼
          puerta de entrada (Nginx)
   ┌──────────┬─────┴──────┬──────────┬──────────┐
 social   verificación   temas     oficial    (grafo: solo interno)
   │ HTTP       │            │          │
   ▼            │            │          │
 grafo ─► Neo4j │            │          │
   └────────────┴──── PostgreSQL ───────┘ ◄── IA (solo cola) ──► Groq
```

---

## 1. Servicio social

Autenticación: `🔓` pública, `🔒` con sesión, `🛡` verificador o admin.

### Cuentas y sesión

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `POST /cuentas` | 🔓 | Registra una cuenta. Recibe `nombre_usuario`, `nombre_visible`, `correo`, `clave`; el servicio calcula la huella argon2id | `CALL social.registrar_usuario` |
| `POST /sesiones` | 🔓 | Inicia sesión con `correo` y `clave`; devuelve `{"vence_en", "usuario"}`. El token va solo en la cookie `HttpOnly` (0012) | `social.acceso_bloqueado`, `iniciar_sesion` |
| `GET /yo` | 🔒 | Mi perfil, con mi rol, mi foto y mi correo (solo lo ve su dueño) | `social.usuario` |
| `PATCH /yo` | 🔒 | Cambia `nombre_visible`, `nombre_usuario` (una vez cada 30 días; el anterior sigue llevando al perfil) o `biografia` (`""` la borra) | `social.actualizar_perfil` |
| `GET /cuentas/disponible?nombre_usuario=` | 🔓 | `disponible`, `en_uso` (actual o reservado) o `invalido` | `social.nombre_usuario_disponible` |
| `PUT /yo/correo` | 🔒 | Nuevo correo; exige la contraseña actual | `social.cambiar_correo` |
| `PUT /yo/clave` | 🔒 | Nueva contraseña; exige la actual y cierra las demás sesiones | `social.cambiar_clave` |
| `PUT /yo/foto` (multipart) | 🔒 | Foto JPG/PNG/WebP ≤ 2 MB: se vuelve a codificar como WebP 400 × 400 sin metadatos | `social.fijar_foto` |
| `DELETE /yo/foto` | 🔒 | Quita la foto | `social.fijar_foto` |
| `POST /yo/desactivacion` | 🔒 | Desactiva la cuenta (decisión 30); exige la contraseña y cierra todas las sesiones | `social.desactivar_cuenta` |
| `GET /fotos/{archivo}` | 🔓 | La foto (caché inmutable) | volumen `fotos` |
| `GET /figuras?archivadas=` · `GET /figuras/{id}` | 🔓 | Fichas con la fuente de cada dato y sus declaraciones | `social.figura_publica` |
| `POST /figuras` · `PATCH /figuras/{id}` · `PUT /figuras/{id}/foto` | 🔒 verificador | Crear, editar (con motivo; archivar) y foto | `crear_figura`, `editar_figura`, `fijar_foto_figura` |
| `GET /figuras/parecidas?nombre=` · `GET /figuras/{id}/bitacora` | 🔓 | Fichas con nombre parecido (antes de crear); cambios de una ficha | `figuras_parecidas`, `bitacora_figura` |
| `GET /equipo` | 🔓 | Quién es verificador o administrador y la bitácora de roles con su motivo (decisión 36) | `social.equipo`, `social.cambio_rol` |
| `POST /equipo/roles` | 🔒 admin (lo exige la base) | Dar o quitar un rol con motivo; nunca deja a Parrhesia sin administrador | `asignar_rol` |
| `POST /propuestas-figura` | 🔒 | Proponer una figura con su fuente | `proponer_figura` |
| `GET /propuestas-figura` · `POST /propuestas-figura/{id}/resolucion` | 🔒 verificador | Revisar propuestas; aceptar crea la ficha, rechazar exige motivo | `resolver_propuesta_figura` |
| `GET /comunidades/recomendadas` | 🔒 | Comunidades públicas sugeridas por temas compartidos, primero las de fuera de mi red (grafo; aviso si no responde) | grafo `COMUNIDADES_RECOMENDADAS` |
| `GET /comunidades/{id}/relacionadas` | 🔓 | Comunidades públicas con los mismos temas, primero las de menos integrantes en común (vacío si es privada) | grafo `COMUNIDADES_RELACIONADAS` |
| `GET /personas/otras-voces` | 🔒 | Personas fuera de mi red cercana que hablan de mis temas | grafo `OTRAS_VOCES` |
| `GET /comunidades?q=&mias=` | 🔓 | Comunidades (su ficha es pública aunque sean privadas), con mi papel, si tengo una solicitud pendiente, publicaciones y última actividad | `social.comunidad`, `mi_papel`, vista `social.actividad_comunidad` |
| `POST /comunidades` · `PATCH /comunidades/{id}` · `PUT /comunidades/{id}/imagen` | 🔒 | Crear (quien crea es administrador) y configurar | `crear_comunidad`, `configurar_comunidad`, `fijar_imagen_comunidad` |
| `GET /comunidades/{id}` | 🔓 | Ficha y permisos de quien consulta (`ver`, `publicar`, `moderar`, `gestionar_integrantes`, `configurar`) | `social.puede` |
| `POST /comunidades/{id}/ingreso` · `DELETE /comunidades/{id}/integrantes/yo` | 🔒 | Entrar (pública) o solicitar (privada); salir | `entrar_a_comunidad`, `salir_de_comunidad` |
| `GET /comunidades/{id}/integrantes` · `PUT …/integrantes/{nombre}/papel` · `POST …/expulsiones` | 🔓/🔒 | Integrantes; asignar papel (administrador); expulsar con motivo (gestor o administrador) | `asignar_papel`, `expulsar_de_comunidad` |
| `GET /comunidades/{id}/solicitudes` · `POST …/solicitudes/{id}/resolucion` | 🔒 | Solicitudes pendientes y su resolución | `resolver_solicitud` |
| `GET` · `POST /comunidades/{id}/publicaciones` | 🔓/🔒 | Publicaciones (fijadas primero) y publicar como integrante | `publicar_en_comunidad` |
| `PUT` · `DELETE /publicaciones/{id}/fijada` | 🔒 | Fijar (máx. 3) o desfijar | `fijar_publicacion` |
| `GET /comunidades/{id}/bitacora` | 🔓 | Lo que hicieron quienes administran y moderan, para quien puede ver la comunidad | `bitacora_comunidad` |
| `GET /usuarios?q=` | 🔓 | Buscar personas activas por nombre; con sesión dice si ya las sigo | `social.buscar_usuarios` |

### Usuarios y seguimiento

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `GET /usuarios/{nombre_usuario}` | 🔓 | Perfil público y estadísticas | vista `social.perfil_publico` |
| `GET /usuarios/{nombre_usuario}/publicaciones?despues=` | 🔓 | Sus publicaciones visibles, de la más nueva a la más vieja | `social.publicacion` |
| `PUT /usuarios/{nombre_usuario}/seguidores/yo` | 🔒 | Seguir (repetirlo no es un error) | `CALL social.seguir` |
| `DELETE /usuarios/{nombre_usuario}/seguidores/yo` | 🔒 | Dejar de seguir | `CALL social.dejar_de_seguir` |
| `GET /sugerencias` | 🔒 | A quién seguir (amigos de mis amigos) | HTTP → grafo `GET /sugerencias/{usuario}` |

### Publicaciones

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `POST /publicaciones` | 🔒 | Publica, responde o comparte. El texto puede llevar formato (`**negrita**`, `*cursiva*`, `[texto](https://…)`); hasta 500 caracteres visibles y 1.500 con marcas. Etiquetas, menciones y verificación usan el texto plano | `CALL social.publicar` |
| `GET /publicaciones/{id}` | 🔓 | Una publicación con sus contadores y su estado de verificación | `social.publicacion`, `verificacion.estado_publicacion` |
| `GET /publicaciones/{id}/hilo` | 🔓 | El hilo completo de respuestas, en orden de lectura | `social.hilo` (recursiva) |
| `GET /publicaciones/{id}/difusion` | 🔓 | Árbol de quién compartió a quién | HTTP → grafo `GET /difusion/{id}` |
| `DELETE /publicaciones/{id}` | 🔒 | Retira la publicación (no se borra). Solo el autor, o un admin | `CALL social.retirar_publicacion` |
| `PUT /publicaciones/{id}/reacciones/yo` | 🔒 | Pone o cambia mi reacción: `{"tipo": "me_gusta" \| "util"}` | `CALL social.reaccionar` |
| `DELETE /publicaciones/{id}/reacciones/yo` | 🔒 | Quita mi reacción | `CALL social.quitar_reaccion` |

`POST /publicaciones`:

```json
{ "texto": "El #desempleo bajó al 8,2 % en septiembre", "responde_a_id": null, "comparte_id": null,
  "figuras_ids": ["3f2c…"] }
```

Respuesta `201`:

```json
{ "id": "a91e…", "autor": { "nombre_usuario": "ana", "nombre_visible": "Ana" },
  "texto": "El #desempleo bajó al 8,2 % en septiembre", "etiquetas": ["desempleo"],
  "estado": "visible", "creado_en": "2026-11-21T14:30:00-05:00",
  "totales": { "respuestas": 0, "compartidas": 0, "reacciones": 0 },
  "verificacion": "pendiente" }
```

`verificacion` es lo que devuelve `verificacion.estado_publicacion`: `pendiente`, `sin_cifras` (es opinión), `lista` o `requiere_revision`. La app vuelve a preguntar mientras diga `pendiente`, o escucha la actualización por la puerta de entrada.

### Feed, etiquetas, tendencias y figuras

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `GET /feed?despues=` | 🔒 | Publicaciones de los últimos 7 días de quienes sigo y de quienes siguen ellos (decisión 8) | HTTP → grafo `GET /feed/{usuario}` devuelve los `id`; social completa texto, contadores y estado de verificación |
| `GET /tendencias` | 🔓 | Etiquetas en tendencia de la última ventana | `social.tendencia`; si no hay ventana reciente, `social.tendencias_basicas` |
| `GET /tendencias/{etiqueta}` | 🔓 | Página de la tendencia: declaraciones y publicaciones de la etiqueta, y el resumen por conclusión | `social.contenido_tendencia`, `verificacion.resumen_conclusiones` |
| `GET /figuras` | 🔓 | Las figuras públicas registradas | `social.figura_publica` |
| `GET /figuras/{id}` | 🔓 | Perfil de la figura con sus declaraciones (la app pide la verificación de cada una a `GET /api/verificacion/v1/textos/declaracion/{id}`) | `social.declaracion` |
| `POST /figuras/{id}/declaraciones` | 🛡 | Registra una declaración con su fuente y sus temas | `CALL social.registrar_declaracion` |

---

## 2. Servicio de verificación

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `GET /textos/{tipo}/{id}` | 🔓 | Todo lo verificado de un texto (`tipo`: `publicacion`, `declaracion`, `declaracion_reportada`, `fragmento_enlace`): estado, afirmaciones y la verificación vigente de cada una | `verificacion.estado_publicacion`, `afirmacion`, `verificacion_vigente` |
| `POST /enlaces` | 🔒 | Analiza un enlace (`url`) o un texto pegado (`texto`): lee la página en memoria y guarda solo metadatos declarados y fragmentos con cifras. 201 `{id, reutilizado}`; 422 `red_cerrada`, `robots`, `destino_no_permitido`, `ilegible`, `url_invalida` (la app ofrece pegar el texto); 429 `limite_enlaces` | `verificacion.registrar_enlace` |
| `GET /enlaces/{id}` | 🔓 | Metadatos declarados, estado y los fragmentos con la verificación de cada uno | `verificacion.enlace`, `fragmento_enlace`, `estado_enlace` |
| `GET /verificaciones/{id}` | 🔓 | Una verificación con su evidencia oficial, sus pruebas de robustez y sus versiones anteriores | `verificacion.*`, `oficial.observaciones_vigentes` |
| `POST /resumen` | 🔓 | Conteo por conclusión de un conjunto de textos (para la página de un tema) | `verificacion.resumen_conclusiones` |
| `GET /conclusiones-por-indicador` | 🔓 | Cuántas cifras verificadas quedaron en cada conclusión, por indicador (página Datos oficiales) | vista materializada `verificacion.conclusiones_por_indicador` |
| `GET /revisiones/pendientes?despues=` | 🛡 | Afirmaciones que requieren revisión humana | `verificacion.afirmacion` con estado `requiere_revision` |
| `POST /verificaciones/{id}/revisiones` | 🛡 | Revisión humana: `{"decision": "confirmada" \| "corregida", "motivo": "…"}` | `CALL verificacion.registrar_revision` |

`GET /textos/publicacion/{id}`:

```json
{
  "estado": "lista",
  "afirmaciones": [{
    "id": "c0d4…",
    "texto_citado": "el desempleo bajó al 8,2 % en septiembre",
    "indicador": "unemployment", "variante": "tasa", "periodo": "2026-09", "territorio": "national",
    "valor_dicho": "8.2",
    "verificacion": {
      "id": "77ab…", "version": 1,
      "conclusion": "se_debilita",
      "explicacion": "Para 2026-09 el texto dice 8,2 % y el dato oficial del DANE es 8,9 %.",
      "serie": { "codigo": "unemployment_rate_national", "nombre": "Tasa de desempleo nacional", "fuente": "DANE" },
      "evidencia": [{ "observacion_id": "5e1f…", "periodo": "2026-09", "valor": "8.9", "rol": "citada" }],
      "pruebas": [{ "codigo": "dato_provisional", "nombre": "Dato provisional", "resultado": "sin_brecha" }],
      "creado_en": "2026-11-21T14:31:10-05:00"
    }
  }]
}
```

Solo se devuelve una explicación con `explicacion_validada = true`. Si no pasó el validador, se muestran la conclusión y la evidencia sin texto redactado.

**Trabajador de verificación** (sin API):
1. Lee con `eventos_pendientes('verificacion', …)` los eventos `publicacion_creada`, `declaracion_creada` y `declaracion_reportada_creada`.
2. Trae el texto con `social.texto_para_verificar` o `temas.texto_para_verificar` y le aplica el filtro previo (`verificacion.requiere_extraccion`). Si no pasa, `registrar_procesamiento(…, 'sin_cifras')` y listo: no se gasta IA.
3. Encola `extraer_afirmaciones` con `ia.encolar_trabajo` y espera el resultado con `ia.resultado_trabajo`. Guarda con `registrar_afirmaciones`.
4. Para cada afirmación, el **motor de reglas** (código Python, sin IA): elige la serie, trae el valor con `oficial.observacion_en`, aplica las pruebas y decide la conclusión.
5. Encola `redactar_explicacion`, pasa el texto por el validador de cifras y guarda con `registrar_verificacion`. La base vuelve a revisar las cifras al confirmar.
6. Marca el evento con `marcar_entregados('verificacion', …)`.

---

## 3. Servicio de grafo (solo red interna)

| Método y ruta | Qué hace | Neo4j / PostgreSQL |
| --- | --- | --- |
| `GET /feed/{usuario_id}?limite=50&antes_de=` | `id` de publicaciones para el feed, con su distancia (1 o 2) | Consulta 1 de [04_modelo_grafo.md](04_modelo_grafo.md) |
| `GET /sugerencias/{usuario_id}` | Hasta 10 usuarios a seguir, con cuántos amigos en común | Consulta 2 |
| `GET /difusion/{publicacion_id}` | Árbol de compartidas hasta 10 niveles y el alcance | Consulta 3 |
| `POST /tendencias/calcular` | Calcula la ventana indicada y la guarda | Consulta 4 → `CALL social.registrar_tendencias` |
| `POST /reconstruir` | Vacía Neo4j y lo vuelve a construir desde PostgreSQL (para la demostración: "si se pierde el grafo, se recupera") | Todas las tablas de `social` y `verificacion` |

**Trabajadores:**
- **Sincronizador:** escucha `pg_notify('evento_salida')`, lee con `eventos_pendientes('grafo', …)` de `social` y `verificacion`, aplica cada evento con el Cypher de la tabla de eventos y marca con `marcar_entregados('grafo', …)`.
- **Tendencias:** cada hora llama al cálculo de la ventana de las últimas 24 horas.

---

## 4. Servicio de temas del día

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `GET /temas` | 🔓 | Los temas de la última ventana, en orden, cada uno con sus medios (artículos y hora del primero) y su actividad en 8 tramos de 3 horas; además, los medios registrados para la huella de cobertura | `temas.temas_actuales`, `cobertura_tema`, `actividad_tema` |
| `GET /temas/{id}` | 🔓 | Página del tema: artículos (medio, título, enlace), declaraciones reportadas con su cita exacta, medios y actividad | `temas.pagina_tema`, `cobertura_tema`, `actividad_tema` |
| `GET /medios` | 🔓 | La lista pública de medios, con sus artículos y temas de la ventana actual | `temas.medio`, vista `temas.cobertura_por_medio` |
| `PUT /medios/{nombre}` | 🛡 admin | Agrega, cambia o deshabilita un medio | `CALL temas.configurar_medio` |

La app arma la página de un tema con dos llamadas: `GET /api/temas/v1/temas/{id}`, y para las declaraciones, `GET /api/verificacion/v1/textos/declaracion_reportada/{id}` y `POST /api/verificacion/v1/resumen`. El servicio de temas no conoce las conclusiones: eso es del servicio de verificación.

**Trabajador:**
- **Recolector:** cada 3 horas lee los RSS con `registrar_articulos`.
- **Agrupación:** después de cada recolección, encola `agrupar_temas` con `articulos_ventana` y guarda con `registrar_temas`.
- **Extracción:** por cada tema nuevo, encola `extraer_declaraciones` por artículo y guarda con `registrar_declaraciones`.

---

## 5. Servicio de datos oficiales

| Método y ruta | Acceso | Qué hace | Base de datos |
| --- | --- | --- | --- |
| `GET /series` | 🔓 | Las series aprobadas, con su indicador, fuente y unidad, y un `resumen`: último valor vigente (con fecha de actualización de la fuente en ISO y si es provisional), valor del periodo anterior y del mismo periodo un año antes tal como se publicaron (nunca una diferencia calculada), notas vigentes y los últimos 25 valores | `oficial.serie`, vista `ultimo_dato_serie`, `observaciones_vigentes`, `descarga`, `notas_en` |
| `GET /series/{codigo}?desde=&hasta=` | 🔓 | La serie completa (valores vigentes y aceptados), con su indicador, el mismo `resumen`, sus notas y alertas abiertas | `oficial.observaciones_vigentes`, `nota_serie`, `alertas_abiertas` |
| `GET /observaciones/{id}` | 🔓 | Trazabilidad de un dato: descarga, archivos originales con su huella, contrastes y versiones anteriores del mismo periodo | `oficial.observacion`, `descarga`, `archivo_original`, `comparacion_contraste` |
| `GET /alertas?estado=abierta` | 🛡 | Alertas para revisión humana | `oficial.alerta` |
| `POST /alertas/{id}/cierre` | 🛡 | Cierra una alerta con su motivo | `CALL oficial.cerrar_alerta` |
| `POST /alertas/{id}/reapertura` | 🛡 | La reabre con su motivo | `CALL oficial.reabrir_alerta` |

**Trabajador:** los conectores que ya existen (`app.runs`) corren una vez al día con el rol `svc_oficial`.

---

## 6. Servicio de IA

No tiene API pública: solo un `GET /salud` que, además del estado, devuelve `ia.estado_cola()` (cuántos trabajos hay en cada estado) y qué cuentas están en pausa. La comunicación es solo por la cola (decisión del [03_servicio_ia.md](03_servicio_ia.md)).

---

## Qué demuestra cada parte en la sustentación

| Requisito | Dónde se ve en las APIs |
| --- | --- |
| Microservicios | 6 servicios con su propio rol y esquema, una puerta de entrada, comunicación por outbox, cola y HTTP interno solo para el grafo |
| Procedimientos | Cada `POST`, `PUT` y `DELETE` llama a un procedimiento: la API no escribe en las tablas directamente |
| Funciones | Las lecturas usan funciones de la base (`hilo`, `observaciones_vigentes`, `estado_publicacion`, `resumen_conclusiones`…) |
| Transacciones | Una petición es una transacción: si el procedimiento falla, la API devuelve el error y no queda nada a medias |
| Triggers | Visibles en la respuesta: contadores actualizados, `verificacion: "pendiente"` apenas se publica (el evento ya está en el outbox) |
| Neo4j | Feed, sugerencias, difusión y tendencias; `POST /reconstruir` muestra que el grafo se recupera desde PostgreSQL |
| Docker | Cada servicio con su `GET /salud`, del que dependen los demás en Docker Compose |
