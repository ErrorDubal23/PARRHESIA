# Glosario del código: español ↔ inglés

Versión 1 (20 nov 2026). Decisión 14 ([00_decisiones.md](00_decisiones.md)): para el proyecto final, la base de datos, los microservicios nuevos, el grafo y la app usan nombres **en español, sin tildes ni ñ**. Cuando el proyecto pase a open source, este glosario es la tabla para volver al inglés: cada nombre tiene un solo equivalente.

## Qué va en español y qué no

| Va en español | Se queda como está |
| --- | --- |
| Esquemas, tablas, columnas, índices, restricciones | Palabras reservadas de SQL, Python, Cypher y TypeScript |
| Valores guardados en estados y tipos (`'aceptada'`, `'en_cola'`) | Los conectores existentes en Python (`src/app`) y sus pruebas: el módulo que escribe en la base traduce sus valores con una tabla fija (`ESTADOS`, `MARCAS`) |
| Procedimientos, funciones, triggers, roles | Los **códigos del catálogo** (series, indicadores y fuentes, por ejemplo `inflation`, `homicides`): vienen de fichas aprobadas con su huella; cambiarlos anula las aprobaciones |
| Nodos, relaciones y propiedades de Neo4j | Nombres de librerías, de servicios externos y de modelos de IA |
| Microservicios nuevos, endpoints y la app | |

Reglas de escritura: minúsculas con guion bajo (`snake_case`); sin tildes (`publicacion`, `verificacion`); la ñ se evita eligiendo otra palabra (`clave_hash` en vez de contraseña, `anio` solo si no hay alternativa). Las etiquetas de Neo4j van en `PascalCase` (`Publicacion`) y sus relaciones en mayúsculas (`SIGUE`).

## Esquemas

| Español | Inglés |
| --- | --- |
| `oficial` | `official` |
| `social` | `social` |
| `verificacion` | `verification` |
| `ia` | `ai` |
| `util` | `util` |
| `temas` | `topics` |

## Esquema `oficial` (renombrado en la migración 0002)

| Tabla | Inglés (0001) | Columnas (español ← inglés) |
| --- | --- | --- |
| `fuente` | `source` | `codigo` ← code, `nombre` ← name, `rol` ← role (`productor` ← producer, `canal_acceso` ← access_channel) |
| `indicador` | `indicator` | `codigo`, `categoria` ← category (`economia` ← economy, `seguridad` ← security) |
| `serie` | `series` | `codigo`, `indicador_id`, `fuente_productora_id` ← producer_source_id, `fuente_canal_id` ← access_channel_source_id, `variante` ← variant, `nombre`, `unidad` ← unit, `etiqueta_unidad` ← unit_label, `frecuencia` ← frequency (`mensual`, `anual`), `geografia` ← geography, `huella_contenido` ← content_sha256, `aprobada` ← approved |
| `aprobacion_serie` | `series_approval` | `serie_id`, `estado` ← status (`pendiente`, `aprobada`, `rechazada`), `huella_contenido`, `aprobada_por` ← approved_by, `aprobada_el` ← approved_on, `comentarios` ← comments |
| `nota_serie` | `series_note` | `serie_id`, `clave_nota` ← note_key, `tipo` ← type, `vigente_desde` ← valid_from, `vigente_hasta` ← valid_to, `estado`, `contenido` ← body |
| `diferencia_version` | `known_version_difference` | `serie_id`, `periodo` ← period, `nivel` ← level, `fuente` ← source, `valor_fuente` ← source_value, `valor_serie` ← series_value |
| `archivo_evidencia` | `evidence_file` | `manifiesto` ← manifest, `fuente`, `url`, `descargado_en` ← downloaded_at, `sha256`, `tamano` ← size, `ubicacion` ← location, `cambio` ← changed, `ultima_modificacion` ← last_modified |
| `brecha_contexto` | `context_gap` | `codigo`, `nombre`, `explicacion` ← explanation, `prueba` ← check_name |
| `descarga` | `download` | `serie_id`, `canal` ← channel, `descargado_en`, `actualizado_fuente` ← source_updated |
| `archivo_original` | `raw_file` | `descarga_id`, `nombre`, `url`, `sha256`, `ubicacion` |
| `observacion` | `observation` | `secuencia` ← seq, `serie_id`, `descarga_id`, `periodo`, `territorio` ← territory, `valor` ← value, `estado` (`en_cuarentena` ← quarantined, `aceptada` ← accepted), `estado_contraste` ← contrast_status, `nivel_contraste` ← contrast_level, `marcas` ← flags |
| `comparacion_contraste` | `contrast_check` | `observacion_id`, `fuente`, `nivel`, `periodo_comparado` ← compared_period, `valor_fuente`, `valor_serie`, `tolerancia` ← tolerance, `resultado` ← outcome, `diferencia_conocida` ← known_difference |
| `alerta` | `alert` | `serie_id`, `observacion_id`, `periodo`, `territorio`, `tipo` ← kind, `valor`, `estado` (`abierta` ← open, `cerrada` ← closed) |
| `evento_alerta` | `alert_event` | `alerta_id`, `evento` ← event (`abierta`, `comentada`, `cerrada`, `reabierta`), `actor`, `motivo` ← reason |

Columnas comunes en todos los esquemas: `creado_en` ← created_at, `actualizado_en` ← updated_at.

Estados de contraste (`estado_contraste`, `resultado`): `paso` ← passed, `pendiente` ← pending, `no_aplica` ← not_applicable, `no_disponible` ← unavailable, `fallo` ← failed. Niveles: `mensual` ← monthly, `anual` ← annual.

Marcas de una observación (`marcas`):

| Español | Inglés |
| --- | --- |
| `valor_faltante` | `missing_value` |
| `fuera_de_rango` | `out_of_range` |
| `hueco_anterior` | `gap_before` |
| `duplicada` | `duplicate` |
| `salto` | `jump` |
| `no_creciente` | `not_increasing` |
| `contraste_pendiente` | `contrast_pending` |
| `contraste_no_coincide` | `contrast_mismatch` |
| `sin_segunda_fuente` | `no_second_source` |
| `contraste_no_disponible` | `contrast_unavailable` |
| `diferencia_version_conocida` | `known_version_difference` |
| `valor_productor_usado` | `producer_value_used` |
| `historia_cambio` | `history_changed` |

## Esquema `social`

| Tabla | Inglés | Columnas |
| --- | --- | --- |
| `usuario` | `user_account` | `nombre_usuario` ← handle, `nombre_visible` ← display_name, `correo` ← email, `clave_hash` ← password_hash, `rol` (`usuario`, `verificador`, `admin`), `estado` (`activo`, `en_revision` ← under_review, `suspendido`), `biografia` ← bio |
| `seguimiento` | `follow` | `seguidor_id` ← follower_id, `seguido_id` ← followed_id |
| `publicacion` | `post` | `autor_id` ← author_id, `texto` ← body, `responde_a_id` ← parent_post_id, `comparte_id` ← repost_of_id, `estado` (`visible`, `retirada_por_autor`, `retirada_por_moderacion`), `total_respuestas` ← reply_count, `total_compartidas` ← repost_count, `total_reacciones` ← reaction_count |
| `etiqueta` | `hashtag` | `nombre` ← tag |
| `publicacion_etiqueta` | `post_hashtag` | `publicacion_id`, `etiqueta_id` |
| `reaccion` | `reaction` | `publicacion_id`, `usuario_id`, `tipo` (`me_gusta` ← like, `util` ← useful) |
| `figura_publica` | `public_figure` | `nombre_completo` ← full_name, `cargo` ← office, `partido` ← party |
| `declaracion` | `declaration` | `figura_id`, `registrada_por` ← recorded_by, `texto`, `dicha_el` ← said_on, `tipo` (`declaracion` ← statement, `promesa` ← promise), `url_fuente` ← source_url, `estado_promesa` ← promise_status |
| `declaracion_etiqueta` | `declaration_hashtag` | `declaracion_id`, `etiqueta_id` |
| `mencion_figura` | `post_figure_mention` | `publicacion_id`, `figura_id` |
| `mencion_usuario` | `post_user_mention` | `publicacion_id`, `usuario_id` |
| `tendencia` | `trending_snapshot` | `ventana_inicio`, `ventana_fin`, `etiqueta_id`, `total_publicaciones`, `total_autores`, `diversidad` ← diversity_score, `puntaje` ← score, `posicion` ← rank, `calculada_en` ← computed_at |
| `bitacora_figura` | `figure_log` | `accion`, `cambios` ← changes (antes ← before, despues ← after), `motivo` |
| `propuesta_figura` | `figure_proposal` | `propuesta_por` ← proposed_by, `url_fuente`, `nota`, `estado` |
| `cambio_rol` | `role_change` | `usuario_id`, `rol_anterior` ← previous_role, `rol_nuevo` ← new_role, `actor_id` (nulo = consola), `motivo` ← reason |
| `comunidad` | `community` | `nombre`, `descripcion`, `reglas` ← rules, `privacidad` ← visibility (`publica`, `privada`), `imagen`, `creada_por`, `total_integrantes` ← member_count |
| `integrante` | `member` | `comunidad_id`, `usuario_id`, `papel` ← role (`integrante`, `moderador`, `gestor` ← member_manager, `administrador`), `desde` ← since |
| `solicitud_ingreso` | `join_request` | `estado` (`pendiente`, `aceptada`, `rechazada`, `retirada`), `resuelta_por`, `motivo` ← reason |
| `bitacora_comunidad` | `community_log` | `accion` ← action, `actor_id`, `afectado_id` ← target_id |
| `nombre_anterior` | `previous_handle` | `nombre` ← handle, `usuario_id`, `usado_hasta` ← used_until |
| `sesion` | `session` | `jti`, `usuario_id`, `agente` ← user_agent, `creada_en`, `vence_en` ← expires_at, `revocada_en` ← revoked_at |
| `intento_acceso` | `login_attempt` | `correo`, `origen` ← origin_hash, `exito` ← success |
| `evento_salida` | `outbox_event` | `tipo_entidad` ← aggregate_type, `entidad_id` ← aggregate_id, `tipo_evento` ← event_type, `datos` ← payload |
| `entrega_evento` | `event_delivery` | `evento_id`, `consumidor` ← consumer (`grafo`, `verificacion`), `entregado_en` ← delivered_at |

## Esquema `verificacion`

| Tabla | Inglés | Columnas |
| --- | --- | --- |
| `afirmacion` | `claim` | `publicacion_id`, `declaracion_id`, `declaracion_reportada_id` ← reported_statement_id, `fragmento_enlace_id` ← link_fragment_id, `posicion` ← position, `texto_citado` ← quoted_text, `codigo_indicador`, `variante` (`anual`, `mensual`, `anio_corrido` ← year_to_date, `tasa`, `conteo`, `nominal`), `periodo_desde`, `periodo_hasta`, `territorio`, `valor_dicho` ← stated_value, `unidad_dicha` ← stated_unit, `comparacion` (`nivel`, `variacion_porcentual`, `variacion_puntos`), `confianza_extraccion`, `trabajo_ia_id`, `estado` (`extraida`, `no_verificable`, `verificada`, `requiere_revision`) |
| `verificacion` | `verification` | `afirmacion_id`, `version`, `codigo_serie`, `conclusion` (`se_sostiene` ← holds, `se_debilita` ← weakened, `se_invierte` ← reversed, `sin_dato_comparable`), `explicacion`, `explicacion_validada`, `version_motor` ← engine_version |
| `evidencia` | `evidence` | `verificacion_id`, `observacion_id`, `rol` (`citada`, `completa`, `contraste`) |
| `prueba_robustez` | `robustness_check` | `codigo`, `nombre`, `descripcion` |
| `resultado_prueba` | `verification_check` | `verificacion_id`, `codigo_prueba`, `resultado` (`sin_brecha`, `con_brecha`, `no_aplica`), `detalle` |
| `revision_humana` | `human_review` | `verificacion_id`, `revisor_id`, `decision` (`confirmada`, `corregida`), `motivo` |
| `evento_salida`, `entrega_evento` | `outbox_event`, `event_delivery` | Igual que en `social` |
| `palabra_clave` | `indicator_keyword` | `codigo_indicador`, `palabra` ← word |
| `enlace` | `link` | `url`, `dominio` ← domain, `titulo` ← title, `sitio` ← site, `autor_declarado` ← declared_author, `publicado_declarado` ← declared_published, `fecha_referencia` ← reference_date, `huella` ← fingerprint, `solicitado_por` ← requested_by, `estado` (`con_cifras`, `sin_cifras`) |
| `fragmento_enlace` | `link_fragment` | `enlace_id`, `posicion` ← position, `texto` ← text |
| `procesamiento` | `processing` | `origen_tipo` ← source_type, `origen_id`, `resultado` ← outcome (`sin_cifras`, `sin_afirmaciones`, `con_afirmaciones`, `fallido`), `procesado_en` |

## Esquema `ia`

| Tabla | Inglés | Columnas |
| --- | --- | --- |
| `credencial` | `credential` | `alias`, `proveedor` ← provider, `habilitada` ← enabled, `pausada_hasta` ← paused_until |
| `trabajo` | `job` | `tipo` ← kind (`extraer_afirmaciones`, `redactar_explicacion`, `agrupar_temas` ← group_topics, `extraer_declaraciones` ← extract_statements), `version_prompt`, `entrada` ← input, `huella_entrada` ← input_sha256, `estado` (`en_cola` ← queued, `en_curso` ← running, `terminado` ← done, `fallido` ← failed), `salida` ← output, `proximo_intento_en` ← next_attempt_at, `terminado_en` ← finished_at |
| `intento` | `job_attempt` | `trabajo_id`, `numero` ← attempt, `credencial_alias`, `modelo`, `resultado` ← outcome (`ok`, `limite_alcanzado` ← rate_limited, `error_proveedor`, `salida_invalida`), `tokens_entrada`, `tokens_salida`, `error`, `iniciado_en`, `terminado_en` |

## Esquema `temas`

| Tabla | Inglés | Columnas |
| --- | --- | --- |
| `medio` | `outlet` | `nombre`, `url_sitio` ← site_url, `canal` ← channel (`rss`, `gdelt`), `url_canal` ← channel_url, `habilitado` ← enabled |
| `articulo` | `article` | `medio_id`, `url`, `titulo` ← title, `resumen` ← summary, `texto` ← body, `publicado_en` ← published_at, `huella` ← sha256 |
| `tema` | `topic` | `ventana_inicio`, `ventana_fin`, `titulo`, `etiqueta` ← hashtag, `total_articulos`, `total_medios` ← outlet_count, `posicion` ← rank, `trabajo_ia_id` |
| `tema_articulo` | `topic_article` | `tema_id`, `articulo_id` |
| `declaracion_reportada` | `reported_statement` | `articulo_id`, `actor`, `figura_id`, `texto_citado` ← quoted_text, `trabajo_ia_id` |
| `evento_salida`, `entrega_evento` | `outbox_event`, `event_delivery` | Igual que en `social` |

## Procedimientos, funciones y triggers

| Español | Inglés |
| --- | --- |
| `util.prohibir_cambios()` | `forbid_update_delete()` |
| `util.marcar_actualizado()` | `touch_updated_at()` |
| `util.validar_transicion()` | `guard_transition()` |
| `oficial.observaciones_vigentes()` | `current_observations()` |
| `oficial.observacion_en()` | `observation_at()` |
| `oficial.esta_aceptada()` | `is_accepted()` |
| `oficial.serie_aprobada()` | `series_is_approved()` |
| `oficial.alertas_abiertas()` | `open_alerts()` |
| `oficial.cerrar_alerta` / `reabrir_alerta` | `close_alert` / `reopen_alert` |
| `social.registrar_usuario` | `register_user` |
| `social.publicar` | `publish_post` |
| `social.retirar_publicacion` | `remove_post` |
| `social.seguir` / `dejar_de_seguir` | `follow_user` / `unfollow_user` |
| `social.reaccionar` / `quitar_reaccion` | `react` / `remove_reaction` |
| `social.registrar_tendencias` | `record_trending` |
| `social.registrar_declaracion` | `record_declaration` |
| `social.eventos_pendientes()` / `marcar_entregados` | `pending_events()` / `mark_delivered` |
| `social.publicacion_existe()`, `declaracion_existe()`, `figura_existe()`, `rol_usuario()`, `texto_para_verificar()` | `post_exists()`, `declaration_exists()`, `figure_exists()`, `user_role()`, `text_to_verify()` |
| `social.emitir_evento()` / `avisar_evento()` | `emit_event()` / `notify_event()` |
| `social.contenido_tendencia()` | `trending_content()` |
| `verificacion.resumen_conclusiones()` | `conclusion_summary()` |
| `social.extraer_etiquetas()` / `extraer_menciones()` | `extract_hashtags()` / `extract_mentions()` |
| `social.hilo()` | `post_thread()` |
| `social.iniciar_sesion` / `cerrar_sesion` / `sesion_activa()` | `start_session` / `end_session` / `active_session()` |
| `social.actualizar_perfil` / `fijar_foto` / `cambiar_correo` / `cambiar_clave` / `desactivar_cuenta` | `update_profile` / `set_avatar` / `change_email` / `change_password` / `deactivate_account` |
| `social.buscar_usuarios()` / `nombre_usuario_disponible()` / `resolver_nombre()` | `search_users()` / `handle_available()` / `resolve_handle()` |
| `social.registrar_intento_acceso` / `acceso_bloqueado()` | `record_login_attempt` / `login_blocked()` |
| `social.estadisticas_usuario()` | `user_stats()` |
| `social.tendencias_basicas()` | `trending_hashtags_basic()` |
| `verificacion.registrar_afirmaciones` | `record_claims` |
| `verificacion.registrar_verificacion` | `record_verification` |
| `verificacion.registrar_revision` | `record_human_review` |
| `verificacion.verificacion_vigente()` | `current_verification()` |
| `verificacion.estado_publicacion()` | `post_verification_status()` |
| `util.cifras_en_texto()` | `numbers_in_text()` |
| `util.texto_plano()` | `plain_text()` |
| `verificacion.requiere_extraccion()` | `needs_extraction()` |
| `verificacion.registrar_procesamiento` / `resumen_conclusiones()` | `record_processing` / `conclusion_summary()` |
| `verificacion.normalizar_lectura()` / `lecturas_coinciden()` / `registrar_afirmaciones_consenso` | `normalize_reading()` / `readings_agree()` / `record_consensus_claims` |
| `verificacion.clave_afirmacion()` | `claim_key()` |
| `temas.imagen_tema` / `temas_sin_imagen()` / `registrar_imagen_tema` / `imagen_vigente()` | `topic_image` / `topics_without_image()` / `record_topic_image` / `current_image()` |
| `oficial.series_publicas()` | `public_series()` |
| `verificacion.motivo_sin_dato` / `consejo` / `guia_redactada` / `consulta_externa` / `verificacion_externa` / `prompt_vigente` | `no_data_reason` / `reading_tip` / `written_guide` / `external_lookup` / `external_check` / `current_prompt` |
| `oficial.consulta_fuente` | `source_lookup_page` |
| `verificacion.guia_de()` / `afirmaciones_sin_guia()` / `registrar_consulta_externa` | `guide_for()` / `claims_without_guide()` / `record_external_lookup` |
| `verificacion.registrar_enlace` / `estado_enlace()` / `texto_fragmento()` / `fragmento_verificable()` | `register_link` / `link_status()` / `fragment_text()` / `verifiable_fragment()` |
| `temas.registrar_articulos` / `registrar_temas` / `registrar_declaraciones` | `record_articles` / `record_topics` / `record_statements` |
| `temas.articulos_ventana()` / `buscar_figura()` / `pagina_tema()` / `temas_actuales()` | `window_articles()` / `match_figure()` / `topic_page()` / `current_topics()` |
| `temas.cobertura_tema()` / `actividad_tema()` | `topic_coverage()` / `topic_activity()` |
| `temas.configurar_medio` / `validar_declaracion()` | `set_outlet` / `validate_statement()` |
| `verificacion.cifras_permitidas()` | `allowed_numbers()` |
| `ia.encolar_trabajo` | `enqueue_job` |
| `ia.tomar_trabajo()` | `claim_next_job()` |
| `ia.elegir_credencial()` | `pick_credential()` |
| `ia.registrar_intento` | `record_attempt` |
| `ia.configurar_credencial` | `set_credential` |
| `ia.resultado_trabajo()` | `job_result()` |
| `ia.estado_cola()` / `calcular_huella()` | `queue_status()` / `compute_input_hash()` |
| `ia.prioridad_trabajo()` / `primer_proveedor_habilitado()` | `job_priority()` / `first_enabled_provider()` |
| `social.asignar_rol` / `asignar_rol_consola` / `equipo` (vista) | `assign_role` / `assign_role_console` / `staff` |
| `social.rol_solo_por_procedimiento()` / `conservar_un_admin()` | `role_only_via_procedure()` / `keep_one_admin()` |

Triggers: `<tabla>_solo_insercion` ← `_append_only`, `<tabla>_actualizado` ← `_touch`, `<tabla>_salida` ← `outbox_*`, `<tabla>_contadores` ← `_counters`, `<tabla>_transicion` ← `_status`.

Roles: `svc_oficial`, `svc_social`, `svc_verificacion`, `svc_ia`, `svc_grafo`, `svc_temas`.

## Neo4j

| Español | Inglés |
| --- | --- |
| `Usuario` (`id`, `nombre_usuario`, `estado`, `creado_en`) | `User` |
| `Publicacion` (`id`, `estado`, `creado_en`) | `Post` |
| `Etiqueta` (`nombre`) | `Hashtag` |
| `Figura` (`id`, `nombre_completo`) | `Figure` |
| `Serie` (`codigo`, `indicador`) | `Series` |
| `SIGUE` | `FOLLOWS` |
| `PUBLICO` | `POSTED` |
| `RESPONDE_A` | `REPLY_TO` |
| `COMPARTE` | `REPOST_OF` |
| `REACCIONO` (`tipo`, `en`) | `REACTED` |
| `ETIQUETADA_CON` | `TAGGED` |
| `MENCIONA` | `MENTIONS` |
| `VERIFICADA_CON` (`conclusion`) | `VERIFIED_WITH` |

Eventos del outbox: `usuario_creado`, `usuario_cambio_estado`, `seguimiento_creado`, `seguimiento_borrado`, `publicacion_creada`, `publicacion_etiquetada`, `publicacion_menciona`, `publicacion_retirada`, `reaccion_puesta`, `reaccion_quitada`, `verificacion_publicada`, `figura_creada`, `declaracion_creada`, `declaracion_reportada_creada`, `fragmento_enlace_creado` ← link_fragment_created. Consumidores: `grafo`, `verificacion`.
