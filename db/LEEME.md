# Base de datos · migraciones

PostgreSQL 17 en Docker (`docker compose up -d`, puerto `5433` del computador). Cada migración es un archivo SQL numerado que se aplica una sola vez, en orden y dentro de una transacción: si algo falla, no queda nada a medias. Una migración ya aplicada no se modifica; un cambio se hace con una migración nueva.

| Archivo | Qué hace | Estado |
|---|---|---|
| `0001_official_data.sql` | Primera versión de los datos oficiales (en inglés, en el esquema `public`) | Aplicada el 26 oct 2026 |
| `0002_esquemas_util_y_oficial.sql` | Crea `util` y `oficial`; mueve las tablas de 0001 a `oficial` y las renombra al español sin perder datos; traduce estados y marcas; restricciones CHECK con nombre; triggers; funciones y procedimientos de `oficial` | Aplicada el 21 nov 2026 |
| `0003_esquema_social.sql` | Esquema `social`: usuarios, publicaciones, seguimientos, reacciones, etiquetas, figuras públicas, declaraciones, tendencias y outbox con entrega por consumidor | Aplicada el 21 nov 2026 |
| `0004_esquema_ia.sql` | Esquema `ia`: cola de trabajos con `FOR UPDATE SKIP LOCKED`, intentos y cuentas sin secretos | Aplicada el 21 nov 2026 |
| `0005_esquema_temas.sql` | Esquema `temas`: medios, artículos, temas del día y declaraciones reportadas con cita textual; `util.cifras_en_texto` | Aplicada el 21 nov 2026 |
| `0006_esquema_verificacion.sql` | Esquema `verificacion`: afirmaciones, verificaciones versionadas, evidencia, pruebas de robustez, revisiones, filtro previo y outbox | Aplicada el 21 nov 2026 |
| `0008_extraccion_por_consenso.sql` | Decisión 26: un trabajo de IA puede exigir proveedor; `verificacion.lecturas_coinciden` compara dos lecturas y `registrar_afirmaciones_consenso` deja en revisión las que difieren | Aplicada el 21 nov 2026 |
| `0009_motor_de_verificacion.sql` | Funciones de `oficial` para el motor (`series_candidatas`, `notas_en`, `detalle_observaciones`) y la dirección de una afirmación (sube o baja) | Aplicada el 21 nov 2026 |
| `0010_trabajo_fallido_es_definitivo.sql` | Encolar devuelve el trabajo fallido en vez de repetirlo; para reintentar se usa una versión nueva del prompt | Aplicada el 21 nov 2026 |
| `0011_redondeo_para_mostrar.sql` | Decisión 27: la explicación puede mostrar el valor oficial redondeado a 0, 1 o 2 decimales; ninguna otra cifra | Aplicada el 21 nov 2026 |
| `0012_sesiones_seguras.sql` | Sesiones en el servidor que se pueden cerrar (`social.sesion`), registro de intentos de acceso (`social.intento_acceso`, el origen se guarda como sha256, nunca la IP), bloqueo tras 5 fallos por correo o 20 por origen en 15 minutos, y `social.sesion_activa()` para que cada servicio compruebe la sesión en cada petición | Aplicada el 21 nov 2026 |
| `0013_cobertura_de_temas.sql` | Funciones `temas.cobertura_tema` (medios que cubren un tema, con artículos y hora del primero) y `temas.actividad_tema` (artículos por tramo de la ventana; la suma es el total). Solo cuentan: cobertura no es importancia | Aplicada el 21 nov 2026 |
| `0014_perfil_y_busqueda.sql` | Foto de perfil (nombre del archivo), estado `desactivada` (decisión 30, sin vuelta atrás desde la app), búsqueda de personas con `pg_trgm`, y procedimientos `actualizar_perfil`, `fijar_foto`, `cambiar_correo`, `cambiar_clave` (cierra las otras sesiones) y `desactivar_cuenta`; evento `usuario_actualizado` para el grafo | Aplicada el 21 nov 2026 |
| `0015_nombres_anteriores.sql` | El nombre de usuario se puede cambiar una vez cada 30 días; el anterior queda reservado para su dueño (`social.nombre_anterior`) y las menciones viejas siguen llevando a su perfil (`social.resolver_nombre`) | Aplicada el 21 nov 2026 |
| `0016_formato_de_publicaciones.sql` | Formato en las publicaciones (`**negrita**`, `*cursiva*`, `[texto](https://…)`), nunca HTML. `util.texto_plano` quita las marcas: el límite de 500 cuenta lo visible (tope de 1.500 con marcas), etiquetas y menciones salen del texto visible y la verificación lee el texto plano. Las mismas reglas están en `web/src/formato.ts` (casos compartidos en `tests/datos/casos_formato.json`) | Aplicada el 21 nov 2026 |
| `0017_texto_plano_nulo.sql` | Corrige 0016: `util.texto_plano` es `STRICT` (un compartido sin comentario tiene texto nulo y debe seguir siendo válido) | Aplicada el 21 nov 2026 |
| `0018_comunidades.sql` | Comunidades (decisión 28): `comunidad`, `integrante`, `solicitud_ingreso` y `bitacora_comunidad` (solo inserción); `publicacion.comunidad_id` y `fijada_en`. Permisos por papel en `social.puede` (administrador, gestor, moderador, integrante); trigger que nunca deja una comunidad sin administrador (bloquea la fila para evitar carreras); visibilidad en `social.puede_ver_publicacion` (también para la verificación); las respuestas heredan la comunidad y lo privado no se comparte; procedimientos para crear, configurar, entrar, resolver solicitudes, salir, expulsar con motivo, asignar papeles, publicar y fijar (máx. 3); eventos de outbox para el grafo | Aplicada el 21 nov 2026 |
| `0019_figuras_publicas.sql` | Gestión de figuras públicas: solo verificadores y administradores crean y editan (`crear_figura`, `editar_figura`, `fijar_foto_figura`); el cargo lleva fuente oficial obligatoria y el partido solo con fuente (`CHECK`); nombres únicos sin tildes ni mayúsculas (`util.nombre_comparable`) y aviso de parecidos (`figuras_parecidas`); fichas archivables; `bitacora_figura` de solo inserción con el antes y el después; `propuesta_figura` para que cualquiera proponga y un verificador acepte o rechace con motivo | Aplicada el 21 nov 2026 |
| `0020_tendencias_sin_privado.sql` | Las tendencias de respaldo (`social.tendencias_basicas`) no cuentan publicaciones de comunidades privadas (igual que las del grafo) | Aplicada el 21 nov 2026 |
| `0021_consenso_por_afirmacion.sql` | Decisión 33: `verificacion.clave_afirmacion` y `registrar_afirmaciones_consenso` emparejan las dos lecturas afirmación por afirmación; lo que coincide queda `extraida`, lo demás `requiere_revision`; consenso del texto `coinciden`, `parcial` o `difieren` | Aplicada el 21 nov 2026 |
| `0022_consenso_sin_duplicados.sql` | Una cifra que solo leyó la segunda lectura no se guarda dos veces si ya está en revisión por la primera (mismo valor, o mismo periodo, variante y comparación) | Aplicada el 21 nov 2026 |
| `0023_consenso_dedup_solo_contra_a.sql` | Esa deduplicación compara solo contra las filas de la primera lectura en desacuerdo, nunca entre filas de la segunda | Aplicada el 21 nov 2026 |
| `0024_compartida_sin_comentario.sql` | `social.texto_para_verificar` devuelve `''` (no NULL) para una publicación visible sin texto: una compartida sin comentario queda `sin_cifras` en lugar de verse "pendiente" para siempre; NULL sigue significando retirada. Completa el procesamiento de las que ya existían | Aplicada el 21 nov 2026 (respaldo `antes_0024.dump`) |
| `0025_analisis_de_enlaces.sql` | Análisis de enlaces externos (decisión 29): `verificacion.enlace` (solo metadatos que la página declara y la huella; nunca el cuerpo) y `verificacion.fragmento_enlace` (citas cortas con cifras, solo inserción), cuarto origen de `afirmacion` con clave foránea real, `registrar_enlace` (todo o nada: filtro previo en la base, como máximo 20 fragmentos, límite de 10 análisis por hora y por persona con bloqueo consultivo, reutiliza un análisis idéntico de los últimos 30 días) y `estado_enlace()` | Aplicada el 21 nov 2026 (respaldo `antes_0025.dump`) |
| `0026_fragmentos_sin_solo_anios.sql` | Con noticias reales: en un enlace, un fragmento necesita una cifra que no sea un año (`fragmento_verificable`); en una nota de Infobae bajó de 7 a 4 fragmentos, sin perder ninguna cifra de los indicadores | Aplicada el 21 nov 2026 |
| `0027_una_compartida_por_persona.sql` | Una persona comparte sin comentario una misma publicación una sola vez (índice único parcial `publicacion_una_compartida_idx`; retirarla permite volver a compartir). Cada clic creaba otra compartida: se retiraron 106 duplicadas de una cuenta de desarrollo, conservando la primera, con el UPDATE de siempre (contadores y grafo al día) | Aplicada el 22 nov 2026 (respaldo `antes_0027.dump`) |
| `0028_imagen_de_tema.sql` | `temas.imagen_tema`: la imagen de Unsplash de cada tema del día, buscada una sola vez, con el crédito del fotógrafo (CHECK: solo `images.unsplash.com` y enlaces de `unsplash.com`), fila sin imagen si no hubo resultado, solo inserción; un tema con la misma etiqueta reutiliza la imagen | Aplicada el 22 nov 2026 |
| `0029_series_publicas.sql` | `oficial.series_publicas()`: una serie por indicador, variante y territorio en la página de datos (la directa del productor primero, igual que el motor) y los otros canales de la misma serie, que se usan para contrastar | Aplicada el 22 nov 2026 |
| `0030_imagen_de_tema_versionada.sql` | Las búsquedas de imagen se versionan (llave `tema_id, version`): con datos reales, buscar con el título trajo una flor para "Escándalo Verónica Estrada"; la versión `categoria-1` nunca busca con nombres, sino con reglas fijas (ciudad, Congreso, clima, seguridad sin violencia). `imagen_vigente()` da la más reciente | Aplicada el 22 nov 2026 |
| `0031_guias_de_lectura.sql` | Decisión 34: `verificacion.motivo_sin_dato` (y la columna en la verificación), `verificacion.consejo` (curado, sin cifras), `oficial.consulta_fuente` (solo `gov.co` por https), `verificacion.guia_redactada` (sin cifras ni juicios por CHECK, publicada solo si el juez la consideró neutral), `consulta_externa` y `verificacion_externa` (sin la calificación de otros medios), `registrar_verificacion` con motivo y `guia_de()` | Aplicada el 22 nov 2026 |
| `0032_motivo_en_verificaciones_anteriores.sql` | Las 50 verificaciones "sin dato comparable" anteriores reciben su motivo como versión nueva (la verificación es de solo inserción) | Aplicada el 22 nov 2026 (respaldo `antes_0032.dump`) |
| `0033_prompt_vigente.sql` | `verificacion.prompt_vigente`: la versión de cada prompt que se publica la fija la base. Al revisar las guías v1 con datos reales, algunas decían de dónde "proviene" la cifra o la llamaban "confiable"; la v2 lo corrige y las v1 dejaron de mostrarse sin borrarse | Aplicada el 22 nov 2026 |
| `0034_cola_con_prioridad.sql` | La cola de IA atiende primero lo que una persona espera (`ia.prioridad_trabajo`: cifras antes que guías y juez) y `ia.primer_proveedor_habilitado` elige el segundo lector entre los que tienen cuenta (Gemini y, si no, OpenRouter), así nada se encola para un proveedor sin llave. Solo funciones | Aplicada el 22 nov 2026 |
| `0035_roles_con_bitacora.sql` | Roles con procedimiento y bitácora pública: `social.asignar_rol` (solo un administrador, motivo obligatorio), `social.asignar_rol_consola` (primer administrador; ningún servicio puede ejecutarlo), `social.cambio_rol` de solo inserción, un trigger que rechaza cambiar el rol por fuera de ellos y otro que impide quedarse sin administrador; vista `social.equipo` | Aplicada el 22 nov 2026 (respaldo `antes_0035.dump`) |
| `0036_permisos_e_indices_de_auditoria.sql` | Auditoría: 58 rutinas posteriores a la 0007 eran ejecutables por PUBLIC (los permisos por defecto por esquema no pueden quitar el global); se cierran todas, se quita el permiso por defecto global y cada servicio recibe su esquema y, de otros, solo lo que su código llama. Índices para las 22 llaves foráneas sin índice; comentarios en 10 tablas | Aplicada el 22 nov 2026 (respaldo `antes_0036.dump`) |
| `0037_sin_bloqueos_mutuos.sql` | Auditoría: 12 respuestas o reacciones simultáneas a la misma publicación fallaban 11 por bloqueo mutuo; `publicar` y `reaccionar` toman la publicación de destino con FOR NO KEY UPDATE desde el inicio | Aplicada el 22 nov 2026 (respaldo `antes_0037.dump`) |
| `0038_reacciones_respetan_la_privacidad.sql` | Auditoría: quien no era integrante podía reaccionar a una publicación de una comunidad privada conociendo su id; `reaccionar` ahora exige `puede_ver_publicacion` | Aplicada el 22 nov 2026 (respaldo `antes_0038.dump`) |
| `0007_roles_por_servicio.sql` | Un rol por microservicio con permisos solo sobre su esquema; lecturas entre servicios por funciones `SECURITY DEFINER` | Aplicada el 21 nov 2026 |

## Cómo aplicarlas

```bash
export PATH="$HOME/.docker/bin:$PATH"   # en Mac, si docker no se encuentra
docker compose up -d
uv run python -m app.db.migrate
```

Las pruebas (`uv run pytest -m "not live"`) crean una base temporal, le aplican todas las migraciones y la borran al terminar: la base de desarrollo no se toca.

Antes de una migración que cambia datos existentes se guarda una copia en `data/respaldos/` (fuera de git):

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > data/respaldos/antes_NNNN.dump
```

## Datos de demostración (`db/semillas/demo.py`)

Una red que ya parece usada, sin gastar IA: 40 personas ficticias (correo `@demo.parrhesia.local`), 11 comunidades (3 privadas, con solicitudes pendientes), unas 380 publicaciones en los últimos 45 días con respuestas, compartidas, etiquetas, menciones y formato, seguimientos, reacciones y publicaciones fijadas. No crea figuras públicas ni temas del día (son personas y medios reales) y se detiene si algún texto pasaría el filtro previo de verificación.

```bash
uv run python db/semillas/demo.py --seguidor dubal_aguilar              # siembra y conecta esa cuenta con la demo
uv run python db/semillas/demo.py --resembrar --seguidor dubal_aguilar  # el día de la presentación
uv run python db/semillas/demo.py --cifras                              # agrega las 11 publicaciones con cifras (usan IA)
uv run python db/semillas/demo.py --fotos                               # avatares ilustrados (DiceBear, CC0), nunca fotos de personas reales
uv run python db/semillas/demo.py --resembrar --seguidor dubal_aguilar --incluir-de dubal_aguilar  # y borra lo que esa cuenta hizo sobre la demo
uv run python db/semillas/figuras.py --verificador prueba_editor        # figuras públicas reales (13), con fuente
uv run python db/semillas/declaraciones.py --verificador prueba_editor  # 7 declaraciones reales, solo texto entre comillas del medio
uv run python db/consola/asignar_rol.py --usuario <usuario> --rol admin --motivo "..."  # primer administrador (solo consola)
uv run python db/semillas/demo.py --limpiar                             # borra la demo
```

La demo trae 8 debates (pensiones, seguridad, impuestos, salud, energía, paz, educación y salario mínimo) con posturas distintas defendidas con argumentos, sin cifras y sin frases atribuidas a personas reales. Al limpiar se borran también las verificaciones de la demo, pero no los trabajos de IA (son la caché). Las publicaciones con cifras (`CIFRAS`) son frases de la evaluación con conclusión conocida (se sostiene, se debilita, se invierte, sin dato comparable y en revisión), puestas en boca de personas ficticias y sin atribuir cifras a instituciones reales; sembradas el mismo día UTC de la evaluación reutilizan sus lecturas, otro día cuestan unas 11 lecturas de cada proveedor. Las fechas son relativas al momento de sembrar, así que la demo envejece: se resiembra el día de la presentación. `--limpiar` (y `--resembrar`, que limpia y siembra en una sola transacción) es **solo para desarrollo**: apaga los triggers de solo inserción y sin borrado (`DISABLE TRIGGER USER`, que deja activas las claves foráneas) únicamente dentro de esa transacción, borra solo lo de las cuentas de la demo y su outbox, y se niega si algo de otras cuentas depende de la demo. Luego reconstruye Neo4j desde el outbox y calcula las tendencias. La clave de las cuentas se imprime al sembrar y no se guarda.

## Esquema `oficial` (migración 0002)

| Tabla | Qué guarda |
|---|---|
| `fuente` | Productores (DANE, Policía…) y canales de acceso (SUAMECA, datos.gov.co). Copia de git |
| `indicador` | Los 8 indicadores de la v1. Copia de git |
| `serie` | Una ficha del catálogo: qué se mide, cómo y de dónde, con su huella y si está aprobada. Copia de git |
| `aprobacion_serie` | Cada estado de aprobación visto en git, aunque la ficha cambie después. Solo inserción |
| `nota_serie` | Notas de una serie: cambios de metodología, conflictos entre fuentes. Copia de git |
| `diferencia_version` | Diferencias conocidas entre fuentes, con el valor exacto de cada una. Copia de git |
| `archivo_evidencia` | Publicaciones oficiales descargadas (líneas de los manifiestos). Solo inserción |
| `brecha_contexto` | Catálogo de brechas de contexto que detectan las pruebas de robustez |
| `descarga` y `archivo_original` | Cada descarga y sus archivos originales con su huella. Solo inserción |
| `observacion` | Un valor oficial de un periodo; una versión nueva es una fila nueva. Solo inserción |
| `comparacion_contraste` | Cada comparación contra una segunda fuente. Solo inserción |
| `alerta` y `evento_alerta` | Marcas que piden revisión humana y su historial (quién, cuándo, por qué) |

"Copia de git" quiere decir que la reescribe `app.db.sync` en cada corrida y nunca se edita a mano.

### Lógica en la base

| Objeto | Tipo | Qué hace |
|---|---|---|
| `util.prohibir_cambios()` | función de trigger | Error ante cualquier `UPDATE` o `DELETE` en las tablas de solo inserción |
| `util.marcar_actualizado()` | función de trigger | `actualizado_en = now()` en cada modificación |
| `util.validar_transicion()` | función de trigger | Máquina de estados: solo deja pasar los cambios de `estado` que recibe como argumento |
| `oficial.observaciones_vigentes(serie, desde, hasta)` | función | El valor vigente y aceptado de cada periodo; si la última versión está en cuarentena, el periodo no aparece |
| `oficial.observacion_en(serie, periodo, territorio)` | función | El valor de un solo periodo, o nada |
| `oficial.esta_aceptada(observacion)` | función | Si la observación es la versión vigente de su periodo y está aceptada |
| `oficial.serie_aprobada(codigo)` | función | Si la serie existe y su ficha está aprobada |
| `oficial.alertas_abiertas(serie)` | función | Alertas abiertas de una serie |
| `oficial.cerrar_alerta(alerta, actor, motivo)` | procedimiento | Cierra la alerta y registra el evento, bloqueando la fila (`FOR UPDATE`) |
| `oficial.reabrir_alerta(alerta, actor, motivo)` | procedimiento | Lo contrario, también con su evento |
| `alerta_cambio_con_evento` | trigger diferido | Al confirmar, rechaza un cambio de estado de una alerta que no tenga su evento |
| `alerta_solo_cambia_estado`, `alerta_transicion` | triggers | Una alerta solo cambia de estado, y solo entre `abierta` y `cerrada` |

### Para probar en pgAdmin o psql

```sql
-- Inflación anual de 2026, solo valores vigentes y aceptados
SELECT * FROM oficial.observaciones_vigentes('inflation_annual_national', '2026-01', '2026-12');

-- Intentar modificar un dato oficial (debe fallar: solo inserción)
UPDATE oficial.observacion SET valor = 0;

-- Cerrar una alerta deja su evento
CALL oficial.cerrar_alerta('<id de la alerta>', 'Dubal', 'El decreto confirma el valor');
SELECT * FROM oficial.evento_alerta ORDER BY creado_en DESC;
```

## Esquema `social` (migración 0003)

| Tabla | Qué guarda |
|---|---|
| `usuario` | La cuenta. Solo acepta la contraseña como huella bcrypt o argon2id (`usuario_clave_es_hash`); correo y nombre de usuario en minúsculas y únicos |
| `seguimiento` | Quién sigue a quién; nadie se sigue a sí mismo |
| `publicacion` | Original, respuesta o compartida. No se edita ni se borra: solo se retira. Lleva sus contadores, que mantienen triggers |
| `etiqueta`, `publicacion_etiqueta` | Hashtags y las publicaciones que los usan |
| `reaccion` | "Me gusta" o "útil", una por usuario y publicación |
| `figura_publica`, `declaracion`, `declaracion_etiqueta` | Figuras públicas, lo que dijeron (con su fuente) y sus temas |
| `mencion_usuario`, `mencion_figura` | A quién menciona cada publicación |
| `tendencia` | Las tendencias de cada ventana, calculadas por el servicio de grafo. Solo inserción |
| `evento_salida`, `entrega_evento` | Outbox: cada cambio queda como evento en la misma transacción, y cada consumidor (grafo, verificación) marca lo que ya procesó |

| Objeto | Tipo | Qué hace |
|---|---|---|
| `registrar_usuario`, `publicar`, `retirar_publicacion`, `seguir`, `dejar_de_seguir`, `reaccionar`, `quitar_reaccion`, `registrar_declaracion`, `registrar_tendencias`, `marcar_entregados` | procedimientos | Cada uno es una sola transacción: o queda todo, o no queda nada |
| `extraer_etiquetas`, `extraer_menciones` | funciones | `#etiquetas` y `@menciones` de un texto, en minúsculas y sin repetir |
| `hilo` | función recursiva | El árbol de respuestas de una publicación (`WITH RECURSIVE`) |
| `estadisticas_usuario`, `tendencias_basicas`, `contenido_tendencia`, `eventos_pendientes` | funciones | Seguidores y publicaciones; tendencias sin grafo; contenido de una tendencia; eventos pendientes de un consumidor |
| `publicacion_existe`, `declaracion_existe`, `figura_existe`, `rol_usuario`, `texto_para_verificar` | funciones `SECURITY DEFINER` | Para los otros esquemas: responden sin dar permiso de leer las tablas |
| `publicacion_contadores`, `reaccion_contadores` | triggers | Mantienen los contadores en la misma transacción |
| `publicacion_cambios_permitidos`, `publicacion_transicion` | triggers | El texto no se edita; una retirada no vuelve a ser visible |
| `<tabla>_salida` y `evento_salida_aviso` | triggers | Escriben el evento en el outbox y avisan con `pg_notify` |

```sql
-- Publicar con etiquetas y menciones (devuelve el id)
CALL social.publicar('<id del autor>', 'El #desempleo bajó, dice @beto', NULL, NULL, NULL, NULL);
-- Intentar editar el texto (debe fallar)
UPDATE social.publicacion SET texto = 'otro texto';
-- Ver los eventos que generó
SELECT tipo_evento, datos FROM social.evento_salida ORDER BY id;
```

## Esquema `ia` (migración 0004)

| Tabla | Qué guarda |
|---|---|
| `credencial` | Cada cuenta del proveedor por su **alias**. No hay columna para la llave: vive en la configuración del servicio de IA |
| `trabajo` | Una tarea para la IA con su entrada, su huella y, al terminar, su salida validada. Estados: `en_cola → en_curso → terminado / fallido` |
| `intento` | Cada llamada al proveedor: cuenta, modelo, tokens y resultado. Solo inserción |

| Objeto | Tipo | Qué hace |
|---|---|---|
| `encolar_trabajo` | procedimiento | Encola, o devuelve el trabajo ya resuelto con la misma entrada (caché) o el ya pendiente |
| `tomar_trabajo` | función | Toma el siguiente trabajo con `FOR UPDATE SKIP LOCKED` y le da un plazo de 5 minutos |
| `elegir_credencial` | función | La cuenta disponible que lleva más tiempo sin usarse |
| `registrar_intento` | procedimiento | `ok` → terminado; `limite_alcanzado` → pausa la cuenta y el trabajo pasa a otra; error → reintenta a los 2, 4, 8 y 16 s y al quinto queda fallido |
| `configurar_credencial`, `estado_cola` | procedimiento, función | Agregar una cuenta; ver cuántos trabajos hay en cada estado |
| `trabajo_huella`, `trabajo_transicion`, `trabajo_cambios_permitidos`, `trabajo_aviso` | triggers | Huella calculada por la base, máquina de estados, entrada inmutable y aviso con `pg_notify` |

```sql
-- Dos ventanas de psql: en las dos, BEGIN; y luego
SELECT id FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones']);
-- cada una recibe un trabajo distinto, sin esperar a la otra.
```

## Esquema `temas` (migración 0005)

| Tabla | Qué guarda |
|---|---|
| `medio` | Medios registrados y su canal (RSS o GDELT) |
| `articulo` | Lo que publicó un medio, con su huella. Solo inserción |
| `tema`, `tema_articulo` | Los temas de cada ventana y sus artículos. Mínimo 3 medios distintos; título y etiqueta sin cifras. Solo inserción |
| `declaracion_reportada` | Lo que un artículo dice que alguien dijo, con cifras y con la cita exacta. Solo inserción |
| `evento_salida`, `entrega_evento` | Outbox hacia el servicio de verificación |

| Objeto | Tipo | Qué hace |
|---|---|---|
| `util.cifras_en_texto` | función | Cifras de un texto en formato colombiano (`1.234,5` → 1234.5) |
| `registrar_articulos` | procedimiento | Guarda los artículos nuevos de un medio; los repetidos se ignoran |
| `registrar_temas` | procedimiento | Recibe los grupos de la IA; la base revisa los artículos, cuenta medios, descarta los de menos de 3, ordena y guarda los 7 primeros. Todo o nada |
| `registrar_declaraciones` | procedimiento | Guarda las citas de un artículo; si una no es textual, no queda ninguna |
| `declaracion_reportada_validar` | trigger | La cita debe aparecer tal cual en el artículo (`cita_no_textual`) |
| `buscar_figura` | función | Liga un actor a una figura registrada solo si el nombre coincide exactamente |
| `articulos_ventana`, `temas_actuales`, `pagina_tema` | funciones | Entrada de la agrupación, temas de la última ventana y contenido de un tema |

## Esquema `verificacion` (migración 0006)

Aquí están las garantías centrales del proyecto, cumplidas por la base aunque el código de un servicio tenga un error.

| Tabla | Qué guarda |
|---|---|
| `palabra_clave`, `prueba_robustez` | Catálogos: palabras de los 8 indicadores (filtro previo) y las 6 pruebas de robustez |
| `procesamiento` | Qué textos ya se revisaron y con qué resultado (sin cifras, sin afirmaciones, con afirmaciones, fallido) |
| `afirmacion` | Una cifra de una publicación, una declaración o una declaración reportada. Solo cambia su estado |
| `verificacion` | La conclusión, versionada: se sostiene, se debilita, se invierte o sin dato comparable. Solo inserción |
| `evidencia`, `resultado_prueba` | Observaciones oficiales que la respaldan y el resultado de cada prueba. Solo inserción |
| `revision_humana` | Revisión de un verificador. Solo inserción |
| `evento_salida`, `entrega_evento` | Outbox hacia el grafo (`verificacion_publicada`) |

| Garantía | Cómo |
|---|---|
| Toda conclusión con dato tiene evidencia oficial citada | Trigger diferido `verificacion_tiene_evidencia` |
| La evidencia es la versión vigente y aceptada (nunca en cuarentena) | Trigger `evidencia_observacion_aceptada` con `oficial.esta_aceptada` |
| Una explicación validada no tiene cifras fuera de la evidencia | Trigger diferido `explicacion_cifras_respaldadas` con `util.cifras_en_texto` y `cifras_permitidas` |
| Hay serie si y solo si hay dato comparable | `CHECK verificacion_serie_si_hay_dato` |
| La serie existe y está aprobada | Trigger `verificacion_serie_existe` |
| El texto de origen existe (en `social` o `temas`) | Trigger `afirmacion_destino_existe` |
| Solo un verificador revisa | Trigger `revision_por_verificador` |

| Objeto | Tipo | Qué hace |
|---|---|---|
| `requiere_extraccion` | función | Filtro previo sin IA: una cifra y una palabra de los 8 indicadores |
| `registrar_afirmaciones`, `registrar_procesamiento` | procedimientos | Guardan lo que extrajo la IA y marcan el texto como revisado |
| `registrar_verificacion` | procedimiento | Bloquea la afirmación (`FOR UPDATE`), crea la versión siguiente con su evidencia y sus pruebas |
| `registrar_revision` | procedimiento | Revisión humana; "corregida" deja la afirmación en revisión |
| `verificacion_vigente`, `estado_publicacion`, `resumen_conclusiones`, `cifras_permitidas` | funciones | Versión vigente; estado que muestra la app; conteo por conclusión para tendencias y temas; cifras que puede usar una explicación |

```sql
-- Intentar publicar una explicación con una cifra inventada (debe fallar al confirmar)
BEGIN;
CALL verificacion.registrar_verificacion('<afirmación>', 'unemployment_rate_national', 'se_debilita',
     'El dato oficial es 9,3 %, unos 1,2 puntos más.', true, 'motor-1',
     '[{"observacion_id": "<observación>", "rol": "citada"}]', '[]', NULL);
COMMIT;   -- ERROR: cifra_sin_respaldo: la explicación usa {1.2} y no está en la evidencia
```

## Roles (migración 0007)

| Rol | Escribe en | Lo que usa de otros servicios (solo funciones) |
|---|---|---|
| `svc_oficial` | `oficial` | — |
| `svc_social` | `social` | `verificacion.estado_publicacion`, `resumen_conclusiones` |
| `svc_verificacion` | `verificacion` | `oficial.observaciones_vigentes`, `observacion_en`, `esta_aceptada`, `serie_aprobada`; `social.texto_para_verificar` y funciones de existencia; `temas.texto_para_verificar`; `ia.encolar_trabajo`, `resultado_trabajo`; lee y marca los outbox de `social` y `temas` |
| `svc_ia` | `ia` | — |
| `svc_temas` | `temas` | `social.figura_existe`; `ia.encolar_trabajo`, `resultado_trabajo` |
| `svc_grafo` | `social.tendencia` y las entregas de los outbox | Lee los outbox de `social` y `verificacion` |

Los roles se crean sin poder iniciar sesión. Al montar cada servicio se les pone la contraseña desde el `.env` (`ALTER ROLE svc_social LOGIN PASSWORD '...'`), que nunca queda en git. Por ahora los conectores siguen usando el usuario de `DATABASE_URL`.

```sql
SET ROLE svc_verificacion;
SELECT correo FROM social.usuario;     -- ERROR: permission denied
SELECT social.rol_usuario('<id>');     -- funciona: es una función autorizada
RESET ROLE;
```

Equivalencias de nombres con el inglés: [docs/diseno/glosario_codigo.md](../docs/diseno/glosario_codigo.md).
