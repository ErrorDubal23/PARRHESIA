-- 0007: un rol de PostgreSQL por microservicio (decisión 13).
--
-- Cada servicio escribe solo en su esquema. Lo que necesita de otro servicio lo
-- pide a través de funciones (SECURITY DEFINER), nunca leyendo sus tablas.
-- Los roles se crean sin poder iniciar sesión: la contraseña de cada uno se pone
-- al montar el servicio, desde el .env, y nunca queda en git:
--     ALTER ROLE svc_social LOGIN PASSWORD '...';
-- Los roles existen en todo el servidor; los permisos son de esta base.

-- =============================================================================
-- PARTE 1 · Roles
-- =============================================================================

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['svc_oficial', 'svc_social', 'svc_verificacion', 'svc_ia', 'svc_temas', 'svc_grafo'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', r);
        END IF;
    END LOOP;
END;
$$;

COMMENT ON ROLE svc_oficial IS 'Conectores de datos oficiales: escriben en oficial';
COMMENT ON ROLE svc_social IS 'Servicio social: escribe en social';
COMMENT ON ROLE svc_verificacion IS 'Servicio de verificación: escribe en verificacion';
COMMENT ON ROLE svc_ia IS 'Servicio de IA: escribe en ia';
COMMENT ON ROLE svc_temas IS 'Servicio de temas del día: escribe en temas';
COMMENT ON ROLE svc_grafo IS 'Servicio de grafo: lee los outbox y guarda las tendencias';

-- =============================================================================
-- PARTE 2 · Funciones que cruzan servicios: se ejecutan con los permisos de su dueño
-- =============================================================================

ALTER FUNCTION oficial.observaciones_vigentes(text, text, text) SECURITY DEFINER;
ALTER FUNCTION oficial.observacion_en(text, text, text) SECURITY DEFINER;
ALTER FUNCTION verificacion.estado_publicacion(uuid) SECURITY DEFINER SET search_path = '';
ALTER FUNCTION verificacion.resumen_conclusiones(uuid[], uuid[], uuid[]) SECURITY DEFINER SET search_path = '';
ALTER PROCEDURE ia.encolar_trabajo(text, text, jsonb, uuid, boolean) SECURITY DEFINER SET search_path = '';

-- Para que verificación y temas lean el resultado de su trabajo sin ver la cola completa.
CREATE FUNCTION ia.resultado_trabajo(p_trabajo_id uuid) RETURNS TABLE (estado text, salida jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT estado, salida FROM ia.trabajo WHERE id = p_trabajo_id;
$$;
COMMENT ON FUNCTION ia.resultado_trabajo(uuid) IS 'Estado y salida de un trabajo, para quien lo encoló';

-- =============================================================================
-- PARTE 3 · Nadie ejecuta nada por defecto (salvo util, que es inofensivo)
-- =============================================================================

REVOKE ALL ON SCHEMA oficial, social, verificacion, ia, temas FROM PUBLIC;
REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA oficial, social, verificacion, ia, temas FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA oficial, social, verificacion, ia, temas REVOKE EXECUTE ON ROUTINES FROM PUBLIC;
GRANT USAGE ON SCHEMA util TO svc_oficial, svc_social, svc_verificacion, svc_ia, svc_temas, svc_grafo;

-- =============================================================================
-- PARTE 4 · Permisos de cada servicio
-- =============================================================================

-- svc_oficial: conectores. Escriben datos y copia del catálogo; cierran alertas.
GRANT USAGE ON SCHEMA oficial TO svc_oficial;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA oficial TO svc_oficial;
GRANT UPDATE ON oficial.fuente, oficial.indicador, oficial.serie, oficial.nota_serie, oficial.diferencia_version,
                oficial.brecha_contexto, oficial.alerta TO svc_oficial;
GRANT DELETE ON oficial.nota_serie, oficial.diferencia_version TO svc_oficial;     -- copia de git: se reescribe
GRANT USAGE ON ALL SEQUENCES IN SCHEMA oficial TO svc_oficial;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA oficial TO svc_oficial;

-- svc_social: la red social.
GRANT USAGE ON SCHEMA social TO svc_social;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA social TO svc_social;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA social TO svc_social;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA social TO svc_social;
GRANT USAGE ON SCHEMA verificacion TO svc_social;
GRANT EXECUTE ON FUNCTION verificacion.estado_publicacion(uuid),
                          verificacion.resumen_conclusiones(uuid[], uuid[], uuid[]) TO svc_social;

-- svc_verificacion: su esquema, más lo que necesita leer de los demás por funciones.
GRANT USAGE ON SCHEMA verificacion TO svc_verificacion;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA verificacion TO svc_verificacion;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA verificacion TO svc_verificacion;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA verificacion TO svc_verificacion;
GRANT USAGE ON SCHEMA oficial, social, temas, ia TO svc_verificacion;
GRANT EXECUTE ON FUNCTION oficial.observaciones_vigentes(text, text, text), oficial.observacion_en(text, text, text),
                          oficial.esta_aceptada(uuid), oficial.serie_aprobada(text),
                          social.publicacion_existe(uuid), social.declaracion_existe(uuid),
                          social.rol_usuario(uuid), social.texto_para_verificar(text, uuid),
                          social.eventos_pendientes(text, text[], int),
                          temas.declaracion_existe(uuid), temas.texto_para_verificar(uuid),
                          temas.eventos_pendientes(text, text[], int),
                          ia.resultado_trabajo(uuid) TO svc_verificacion;
GRANT EXECUTE ON PROCEDURE social.marcar_entregados(text, bigint[]), temas.marcar_entregados(text, bigint[]),
                           ia.encolar_trabajo(text, text, jsonb, uuid, boolean) TO svc_verificacion;
-- Leer los outbox que consume y marcar lo procesado.
GRANT SELECT ON social.evento_salida, social.entrega_evento, temas.evento_salida, temas.entrega_evento TO svc_verificacion;
GRANT INSERT ON social.entrega_evento, temas.entrega_evento TO svc_verificacion;

-- svc_ia: la cola.
GRANT USAGE ON SCHEMA ia TO svc_ia;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ia TO svc_ia;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA ia TO svc_ia;

-- svc_temas: su esquema; encola trabajos y liga actores a figuras.
GRANT USAGE ON SCHEMA temas TO svc_temas;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA temas TO svc_temas;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA temas TO svc_temas;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA temas TO svc_temas;
GRANT USAGE ON SCHEMA social, ia TO svc_temas;
GRANT EXECUTE ON FUNCTION social.figura_existe(uuid), ia.resultado_trabajo(uuid) TO svc_temas;
GRANT EXECUTE ON PROCEDURE ia.encolar_trabajo(text, text, jsonb, uuid, boolean) TO svc_temas;

-- svc_grafo: lee los outbox de social y verificación, marca lo aplicado y guarda tendencias.
GRANT USAGE ON SCHEMA social, verificacion TO svc_grafo;
GRANT SELECT ON social.evento_salida, social.entrega_evento, social.etiqueta,
                verificacion.evento_salida, verificacion.entrega_evento TO svc_grafo;
GRANT INSERT ON social.entrega_evento, verificacion.entrega_evento, social.tendencia TO svc_grafo;
GRANT EXECUTE ON FUNCTION social.eventos_pendientes(text, text[], int),
                          verificacion.eventos_pendientes(text, text[], int) TO svc_grafo;
GRANT EXECUTE ON PROCEDURE social.marcar_entregados(text, bigint[]), verificacion.marcar_entregados(text, bigint[]),
                           social.registrar_tendencias(timestamptz, timestamptz, jsonb) TO svc_grafo;
