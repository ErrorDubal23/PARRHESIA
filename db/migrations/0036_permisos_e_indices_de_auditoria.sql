-- 0036 · Auditoría de la base (22 nov 2026, plan de pruebas PR-03, BD-03 y BD-02b).
--
-- 1. PERMISOS (hallazgo crítico PR-03). La 0007 quitó a PUBLIC el permiso de ejecutar rutinas con
--    "ALTER DEFAULT PRIVILEGES IN SCHEMA ... REVOKE", pero en PostgreSQL los permisos por defecto por esquema solo
--    se SUMAN a los globales: no pueden quitar el EXECUTE que toda rutina nueva le da a PUBLIC. Resultado: las 58
--    rutinas creadas después de la 0007 las podía ejecutar cualquier rol con acceso al esquema. Por ejemplo,
--    svc_temas, svc_oficial y svc_grafo (que solo leen en social) podían llamar social.cambiar_clave o
--    social.asignar_rol pasando como actor el id de un administrador.
--    Corrección: se quita EXECUTE a PUBLIC en todas, se quita también el permiso por defecto GLOBAL (así las
--    rutinas futuras nacen cerradas) y cada servicio recibe solo lo suyo: todas las rutinas de su esquema y, de
--    otros esquemas, exactamente las que su código llama (lista sacada del código de cada servicio).
-- 2. ÍNDICES (BD-03): las 22 llaves foráneas sin índice lo reciben (joins y borrados en cascada sin recorrer
--    la tabla completa).
-- 3. COMENTARIOS (BD-02b): las 10 tablas sin comentario lo reciben.
-- Sin cambios en datos.

-- 1 · Permisos de ejecución --------------------------------------------------------------------------------
REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA oficial, social, verificacion, ia, temas FROM PUBLIC;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON ROUTINES FROM PUBLIC;

-- Cada servicio, todo su esquema.
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA oficial TO svc_oficial;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA social TO svc_social;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA verificacion TO svc_verificacion;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA ia TO svc_ia;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA temas TO svc_temas;
-- ...menos lo que es solo de la consola del dueño (0035): ningún servicio cambia roles sin un administrador.
REVOKE EXECUTE ON PROCEDURE social.asignar_rol_consola(uuid, text, text) FROM svc_social;
REVOKE EXECUTE ON FUNCTION social._cambiar_rol(uuid, uuid, text, text) FROM svc_social;

-- Todos los servicios validan la sesión de quien llama.
GRANT EXECUTE ON FUNCTION social.sesion_activa(uuid) TO svc_oficial, svc_verificacion, svc_temas, svc_grafo;

-- De otros esquemas, solo lo que cada servicio llama.
GRANT EXECUTE ON FUNCTION verificacion.estado_publicacion(uuid),
                          verificacion.resumen_conclusiones(uuid[], uuid[], uuid[]) TO svc_social;
GRANT EXECUTE ON FUNCTION social.eventos_pendientes(text, text[], integer), social.texto_para_verificar(text, uuid),
                          social.puede_ver_publicacion(uuid, uuid),
                          temas.eventos_pendientes(text, text[], integer), temas.texto_para_verificar(uuid),
                          oficial.detalle_observaciones(uuid[]), oficial.notas_en(text, text),
                          oficial.observacion_en(text, text, text), oficial.series_candidatas(text, text),
                          ia.resultado_trabajo(uuid), ia.primer_proveedor_habilitado(text[]) TO svc_verificacion;
GRANT EXECUTE ON PROCEDURE social.marcar_entregados(text, bigint[]), temas.marcar_entregados(text, bigint[]),
                           ia.encolar_trabajo(text, text, jsonb, text, uuid, boolean) TO svc_verificacion;
GRANT EXECUTE ON FUNCTION ia.resultado_trabajo(uuid) TO svc_temas;
GRANT EXECUTE ON PROCEDURE ia.encolar_trabajo(text, text, jsonb, text, uuid, boolean) TO svc_temas;
GRANT EXECUTE ON FUNCTION social.eventos_pendientes(text, text[], integer),
                          verificacion.eventos_pendientes(text, text[], integer) TO svc_grafo;
GRANT EXECUTE ON PROCEDURE social.marcar_entregados(text, bigint[]), verificacion.marcar_entregados(text, bigint[]),
                           social.registrar_tendencias(timestamptz, timestamptz, jsonb) TO svc_grafo;

-- 2 · Índices de las llaves foráneas ---------------------------------------------------------------------
CREATE INDEX alerta_observacion_id_idx ON oficial.alerta (observacion_id);
CREATE INDEX archivo_original_descarga_id_idx ON oficial.archivo_original (descarga_id);
CREATE INDEX observacion_descarga_id_idx ON oficial.observacion (descarga_id);
CREATE INDEX serie_fuente_canal_id_idx ON oficial.serie (fuente_canal_id);
CREATE INDEX serie_fuente_productora_id_idx ON oficial.serie (fuente_productora_id);
CREATE INDEX serie_indicador_id_idx ON oficial.serie (indicador_id);
CREATE INDEX bitacora_figura_actor_id_idx ON social.bitacora_figura (actor_id);
CREATE INDEX cambio_rol_actor_id_idx ON social.cambio_rol (actor_id);
CREATE INDEX comunidad_creada_por_idx ON social.comunidad (creada_por);
CREATE INDEX declaracion_registrada_por_idx ON social.declaracion (registrada_por);
CREATE INDEX figura_publica_creada_por_idx ON social.figura_publica (creada_por);
CREATE INDEX mencion_figura_figura_id_idx ON social.mencion_figura (figura_id);
CREATE INDEX mencion_usuario_usuario_id_idx ON social.mencion_usuario (usuario_id);
CREATE INDEX propuesta_figura_figura_id_idx ON social.propuesta_figura (figura_id);
CREATE INDEX propuesta_figura_propuesta_por_idx ON social.propuesta_figura (propuesta_por);
CREATE INDEX propuesta_figura_resuelta_por_idx ON social.propuesta_figura (resuelta_por);
CREATE INDEX solicitud_ingreso_resuelta_por_idx ON social.solicitud_ingreso (resuelta_por);
CREATE INDEX solicitud_ingreso_usuario_id_idx ON social.solicitud_ingreso (usuario_id);
CREATE INDEX tendencia_etiqueta_id_idx ON social.tendencia (etiqueta_id);
CREATE INDEX resultado_prueba_codigo_prueba_idx ON verificacion.resultado_prueba (codigo_prueba);
CREATE INDEX revision_humana_verificacion_id_idx ON verificacion.revision_humana (verificacion_id);
CREATE INDEX verificacion_motivo_sin_dato_idx ON verificacion.verificacion (motivo_sin_dato);

-- 3 · Comentarios ------------------------------------------------------------------------------------------
COMMENT ON TABLE social.mencion_figura IS 'Figuras públicas mencionadas en una publicación';
COMMENT ON TABLE social.mencion_usuario IS 'Personas mencionadas (@) en una publicación';
COMMENT ON TABLE social.publicacion_etiqueta IS 'Etiquetas (#) de cada publicación';
COMMENT ON TABLE social.reaccion IS 'Me gusta o Útil de una persona sobre una publicación (una por persona)';
COMMENT ON TABLE temas.evento_salida IS 'Outbox de temas: eventos que leen otros servicios (declaraciones reportadas)';
COMMENT ON TABLE temas.entrega_evento IS 'Qué consumidor ya procesó cada evento del outbox de temas';
COMMENT ON TABLE temas.tema_articulo IS 'Artículos que forman cada tema del día';
COMMENT ON TABLE verificacion.consulta_externa IS 'Consultas a verificaciones de otros medios (sin su calificación), una por afirmación';
COMMENT ON TABLE verificacion.evento_salida IS 'Outbox de verificación: verificaciones publicadas y fragmentos de enlaces';
COMMENT ON TABLE verificacion.entrega_evento IS 'Qué consumidor ya procesó cada evento del outbox de verificación';
