-- 0002: esquemas util y oficial. Datos oficiales en español (decisiones 1, 2, 9 y 14).
--
-- Qué hace, en una sola transacción:
--   1. Crea el esquema util con las funciones genéricas de trigger.
--   2. Mueve las 14 tablas de la migración 0001 (public, en inglés) al esquema oficial
--      y las renombra al español, con sus columnas, restricciones e índices.
--   3. Traduce los valores guardados (estados, niveles, marcas). Si aparece un valor
--      desconocido, la traducción da NULL, una restricción NOT NULL o CHECK falla y la
--      migración completa se deshace: no se pierde ningún dato.
--   4. Crea las restricciones CHECK con nombre, los triggers y las funciones y
--      procedimientos del esquema oficial.
--
-- Equivalencias español <-> inglés: docs/diseno/glosario_codigo.md.
-- Los códigos del catálogo (series, indicadores, fuentes, territorios) no se traducen:
-- vienen de fichas aprobadas con su huella.

-- =============================================================================
-- PARTE 1 · Esquemas y funciones genéricas
-- =============================================================================

CREATE SCHEMA util;
COMMENT ON SCHEMA util IS 'Funciones genéricas de trigger que usan todos los esquemas; no tiene tablas';

CREATE SCHEMA oficial;
COMMENT ON SCHEMA oficial IS 'Datos oficiales: fuentes, series, descargas, observaciones, contrastes y alertas';

-- Los triggers de 0001 se quitan aquí y se vuelven a crear en la parte 5 con sus
-- nombres en español. Así la traducción de valores (parte 3) no choca con ellos.
DROP TRIGGER download_append_only ON public.download;
DROP TRIGGER raw_file_append_only ON public.raw_file;
DROP TRIGGER observation_append_only ON public.observation;
DROP TRIGGER contrast_check_append_only ON public.contrast_check;
DROP TRIGGER alert_event_append_only ON public.alert_event;
DROP TRIGGER series_approval_append_only ON public.series_approval;
DROP TRIGGER evidence_file_append_only ON public.evidence_file;
DROP TRIGGER source_touch ON public.source;
DROP TRIGGER indicator_touch ON public.indicator;
DROP TRIGGER series_touch ON public.series;
DROP TRIGGER series_note_touch ON public.series_note;
DROP TRIGGER known_version_difference_touch ON public.known_version_difference;
DROP TRIGGER context_gap_touch ON public.context_gap;
DROP TRIGGER alert_touch ON public.alert;
DROP TRIGGER alert_only_status ON public.alert;
DROP TRIGGER alert_no_delete ON public.alert;
DROP FUNCTION public.forbid_update_delete();
DROP FUNCTION public.touch_updated_at();
DROP FUNCTION public.alert_only_status_changes();

-- Tablas de solo inserción: cualquier UPDATE o DELETE es un error.
CREATE FUNCTION util.prohibir_cambios() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '%.% es de solo inserción: no se permite %', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP;
END;
$$;
COMMENT ON FUNCTION util.prohibir_cambios() IS 'Trigger de las tablas de solo inserción (historial y evidencia)';

-- actualizado_en siempre refleja la última modificación.
CREATE FUNCTION util.marcar_actualizado() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.actualizado_en := now();
    RETURN NEW;
END;
$$;
COMMENT ON FUNCTION util.marcar_actualizado() IS 'Trigger que pone actualizado_en = now() en cada UPDATE';

-- Transiciones de estado permitidas. Recibe en TG_ARGV[0] un JSON como
-- {"en_cola": ["en_curso"], "en_curso": ["en_cola", "terminado", "fallido"]}
-- y rechaza cualquier otro cambio de la columna estado.
CREATE FUNCTION util.validar_transicion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    permitidas jsonb := TG_ARGV[0]::jsonb;
    anterior   text  := to_jsonb(OLD) ->> 'estado';
    nuevo      text  := to_jsonb(NEW) ->> 'estado';
BEGIN
    IF anterior IS DISTINCT FROM nuevo AND NOT coalesce((permitidas -> anterior) ? nuevo, false) THEN
        RAISE EXCEPTION '%.%: no se permite pasar de % a %', TG_TABLE_SCHEMA, TG_TABLE_NAME, anterior, nuevo;
    END IF;
    RETURN NEW;
END;
$$;
COMMENT ON FUNCTION util.validar_transicion() IS 'Trigger genérico de máquina de estados: solo permite las transiciones que recibe como argumento';

-- =============================================================================
-- PARTE 2 · Mover y renombrar las tablas de 0001
-- =============================================================================

-- source -> oficial.fuente
ALTER TABLE public.source SET SCHEMA oficial;
ALTER TABLE oficial.source RENAME TO fuente;
ALTER TABLE oficial.fuente RENAME COLUMN code TO codigo;
ALTER TABLE oficial.fuente RENAME COLUMN name TO nombre;
ALTER TABLE oficial.fuente RENAME COLUMN role TO rol;
ALTER TABLE oficial.fuente RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.fuente RENAME COLUMN updated_at TO actualizado_en;

-- indicator -> oficial.indicador
ALTER TABLE public.indicator SET SCHEMA oficial;
ALTER TABLE oficial.indicator RENAME TO indicador;
ALTER TABLE oficial.indicador RENAME COLUMN code TO codigo;
ALTER TABLE oficial.indicador RENAME COLUMN category TO categoria;
ALTER TABLE oficial.indicador RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.indicador RENAME COLUMN updated_at TO actualizado_en;

-- series -> oficial.serie
ALTER TABLE public.series SET SCHEMA oficial;
ALTER TABLE oficial.series RENAME TO serie;
ALTER TABLE oficial.serie RENAME COLUMN code TO codigo;
ALTER TABLE oficial.serie RENAME COLUMN indicator_id TO indicador_id;
ALTER TABLE oficial.serie RENAME COLUMN producer_source_id TO fuente_productora_id;
ALTER TABLE oficial.serie RENAME COLUMN access_channel_source_id TO fuente_canal_id;
ALTER TABLE oficial.serie RENAME COLUMN variant TO variante;
ALTER TABLE oficial.serie RENAME COLUMN name TO nombre;
ALTER TABLE oficial.serie RENAME COLUMN unit TO unidad;
ALTER TABLE oficial.serie RENAME COLUMN unit_label TO etiqueta_unidad;
ALTER TABLE oficial.serie RENAME COLUMN frequency TO frecuencia;
ALTER TABLE oficial.serie RENAME COLUMN geography TO geografia;
ALTER TABLE oficial.serie RENAME COLUMN content_sha256 TO huella_contenido;
ALTER TABLE oficial.serie RENAME COLUMN approved TO aprobada;
ALTER TABLE oficial.serie RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.serie RENAME COLUMN updated_at TO actualizado_en;

-- series_approval -> oficial.aprobacion_serie
ALTER TABLE public.series_approval SET SCHEMA oficial;
ALTER TABLE oficial.series_approval RENAME TO aprobacion_serie;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN series_id TO serie_id;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN status TO estado;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN content_sha256 TO huella_contenido;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN approved_by TO aprobada_por;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN approved_on TO aprobada_el;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN comments TO comentarios;
ALTER TABLE oficial.aprobacion_serie RENAME COLUMN created_at TO creado_en;

-- series_note -> oficial.nota_serie
ALTER TABLE public.series_note SET SCHEMA oficial;
ALTER TABLE oficial.series_note RENAME TO nota_serie;
ALTER TABLE oficial.nota_serie RENAME COLUMN series_id TO serie_id;
ALTER TABLE oficial.nota_serie RENAME COLUMN note_key TO clave_nota;
ALTER TABLE oficial.nota_serie RENAME COLUMN type TO tipo;
ALTER TABLE oficial.nota_serie RENAME COLUMN valid_from TO vigente_desde;
ALTER TABLE oficial.nota_serie RENAME COLUMN valid_to TO vigente_hasta;
ALTER TABLE oficial.nota_serie RENAME COLUMN status TO estado;
ALTER TABLE oficial.nota_serie RENAME COLUMN body TO contenido;
ALTER TABLE oficial.nota_serie RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.nota_serie RENAME COLUMN updated_at TO actualizado_en;

-- known_version_difference -> oficial.diferencia_version
ALTER TABLE public.known_version_difference SET SCHEMA oficial;
ALTER TABLE oficial.known_version_difference RENAME TO diferencia_version;
ALTER TABLE oficial.diferencia_version RENAME COLUMN series_id TO serie_id;
ALTER TABLE oficial.diferencia_version RENAME COLUMN period TO periodo;
ALTER TABLE oficial.diferencia_version RENAME COLUMN level TO nivel;
ALTER TABLE oficial.diferencia_version RENAME COLUMN source TO fuente;
ALTER TABLE oficial.diferencia_version RENAME COLUMN source_value TO valor_fuente;
ALTER TABLE oficial.diferencia_version RENAME COLUMN series_value TO valor_serie;
ALTER TABLE oficial.diferencia_version RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.diferencia_version RENAME COLUMN updated_at TO actualizado_en;

-- evidence_file -> oficial.archivo_evidencia
ALTER TABLE public.evidence_file SET SCHEMA oficial;
ALTER TABLE oficial.evidence_file RENAME TO archivo_evidencia;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN manifest TO manifiesto;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN source TO fuente;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN downloaded_at TO descargado_en;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN size TO tamano;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN location TO ubicacion;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN changed TO cambio;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN last_modified TO ultima_modificacion;
ALTER TABLE oficial.archivo_evidencia RENAME COLUMN created_at TO creado_en;

-- context_gap -> oficial.brecha_contexto
ALTER TABLE public.context_gap SET SCHEMA oficial;
ALTER TABLE oficial.context_gap RENAME TO brecha_contexto;
ALTER TABLE oficial.brecha_contexto RENAME COLUMN code TO codigo;
ALTER TABLE oficial.brecha_contexto RENAME COLUMN name TO nombre;
ALTER TABLE oficial.brecha_contexto RENAME COLUMN explanation TO explicacion;
ALTER TABLE oficial.brecha_contexto RENAME COLUMN check_name TO prueba;
ALTER TABLE oficial.brecha_contexto RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.brecha_contexto RENAME COLUMN updated_at TO actualizado_en;

-- download -> oficial.descarga
ALTER TABLE public.download SET SCHEMA oficial;
ALTER TABLE oficial.download RENAME TO descarga;
ALTER TABLE oficial.descarga RENAME COLUMN series_id TO serie_id;
ALTER TABLE oficial.descarga RENAME COLUMN channel TO canal;
ALTER TABLE oficial.descarga RENAME COLUMN downloaded_at TO descargado_en;
ALTER TABLE oficial.descarga RENAME COLUMN source_updated TO actualizado_fuente;
ALTER TABLE oficial.descarga RENAME COLUMN created_at TO creado_en;

-- raw_file -> oficial.archivo_original
ALTER TABLE public.raw_file SET SCHEMA oficial;
ALTER TABLE oficial.raw_file RENAME TO archivo_original;
ALTER TABLE oficial.archivo_original RENAME COLUMN download_id TO descarga_id;
ALTER TABLE oficial.archivo_original RENAME COLUMN name TO nombre;
ALTER TABLE oficial.archivo_original RENAME COLUMN location TO ubicacion;
ALTER TABLE oficial.archivo_original RENAME COLUMN created_at TO creado_en;

-- observation -> oficial.observacion
ALTER TABLE public.observation SET SCHEMA oficial;
ALTER TABLE oficial.observation RENAME TO observacion;
ALTER TABLE oficial.observacion RENAME COLUMN seq TO secuencia;
ALTER TABLE oficial.observacion RENAME COLUMN series_id TO serie_id;
ALTER TABLE oficial.observacion RENAME COLUMN download_id TO descarga_id;
ALTER TABLE oficial.observacion RENAME COLUMN period TO periodo;
ALTER TABLE oficial.observacion RENAME COLUMN territory TO territorio;
ALTER TABLE oficial.observacion RENAME COLUMN value TO valor;
ALTER TABLE oficial.observacion RENAME COLUMN status TO estado;
ALTER TABLE oficial.observacion RENAME COLUMN contrast_status TO estado_contraste;
ALTER TABLE oficial.observacion RENAME COLUMN contrast_level TO nivel_contraste;
ALTER TABLE oficial.observacion RENAME COLUMN flags TO marcas;
ALTER TABLE oficial.observacion RENAME COLUMN created_at TO creado_en;

-- contrast_check -> oficial.comparacion_contraste
ALTER TABLE public.contrast_check SET SCHEMA oficial;
ALTER TABLE oficial.contrast_check RENAME TO comparacion_contraste;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN observation_id TO observacion_id;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN source TO fuente;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN level TO nivel;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN compared_period TO periodo_comparado;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN source_value TO valor_fuente;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN series_value TO valor_serie;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN tolerance TO tolerancia;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN outcome TO resultado;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN known_difference TO diferencia_conocida;
ALTER TABLE oficial.comparacion_contraste RENAME COLUMN created_at TO creado_en;

-- alert -> oficial.alerta
ALTER TABLE public.alert SET SCHEMA oficial;
ALTER TABLE oficial.alert RENAME TO alerta;
ALTER TABLE oficial.alerta RENAME COLUMN series_id TO serie_id;
ALTER TABLE oficial.alerta RENAME COLUMN observation_id TO observacion_id;
ALTER TABLE oficial.alerta RENAME COLUMN period TO periodo;
ALTER TABLE oficial.alerta RENAME COLUMN territory TO territorio;
ALTER TABLE oficial.alerta RENAME COLUMN kind TO tipo;
ALTER TABLE oficial.alerta RENAME COLUMN value TO valor;
ALTER TABLE oficial.alerta RENAME COLUMN status TO estado;
ALTER TABLE oficial.alerta RENAME COLUMN created_at TO creado_en;
ALTER TABLE oficial.alerta RENAME COLUMN updated_at TO actualizado_en;

-- alert_event -> oficial.evento_alerta
ALTER TABLE public.alert_event SET SCHEMA oficial;
ALTER TABLE oficial.alert_event RENAME TO evento_alerta;
ALTER TABLE oficial.evento_alerta RENAME COLUMN alert_id TO alerta_id;
ALTER TABLE oficial.evento_alerta RENAME COLUMN event TO evento;
ALTER TABLE oficial.evento_alerta RENAME COLUMN reason TO motivo;
ALTER TABLE oficial.evento_alerta RENAME COLUMN created_at TO creado_en;

-- Llaves primarias, únicas y foráneas: los nombres siguen la convención de
-- PostgreSQL (<tabla>_pkey, <tabla>_<columna>_key, <tabla>_<columna>_fkey).
ALTER TABLE oficial.fuente RENAME CONSTRAINT source_pkey TO fuente_pkey;
ALTER TABLE oficial.fuente RENAME CONSTRAINT source_code_key TO fuente_codigo_key;
ALTER TABLE oficial.indicador RENAME CONSTRAINT indicator_pkey TO indicador_pkey;
ALTER TABLE oficial.indicador RENAME CONSTRAINT indicator_code_key TO indicador_codigo_key;
ALTER TABLE oficial.serie RENAME CONSTRAINT series_pkey TO serie_pkey;
ALTER TABLE oficial.serie RENAME CONSTRAINT series_code_key TO serie_codigo_key;
ALTER TABLE oficial.serie RENAME CONSTRAINT series_indicator_id_fkey TO serie_indicador_id_fkey;
ALTER TABLE oficial.serie RENAME CONSTRAINT series_producer_source_id_fkey TO serie_fuente_productora_id_fkey;
ALTER TABLE oficial.serie RENAME CONSTRAINT series_access_channel_source_id_fkey TO serie_fuente_canal_id_fkey;
ALTER TABLE oficial.aprobacion_serie RENAME CONSTRAINT series_approval_pkey TO aprobacion_serie_pkey;
ALTER TABLE oficial.aprobacion_serie RENAME CONSTRAINT series_approval_series_id_fkey TO aprobacion_serie_serie_id_fkey;
ALTER TABLE oficial.aprobacion_serie RENAME CONSTRAINT series_approval_series_id_status_content_sha256_approved_by_key TO aprobacion_serie_unica;
ALTER TABLE oficial.nota_serie RENAME CONSTRAINT series_note_pkey TO nota_serie_pkey;
ALTER TABLE oficial.nota_serie RENAME CONSTRAINT series_note_series_id_fkey TO nota_serie_serie_id_fkey;
ALTER TABLE oficial.nota_serie RENAME CONSTRAINT series_note_series_id_note_key_key TO nota_serie_serie_id_clave_nota_key;
ALTER TABLE oficial.diferencia_version RENAME CONSTRAINT known_version_difference_pkey TO diferencia_version_pkey;
ALTER TABLE oficial.diferencia_version RENAME CONSTRAINT known_version_difference_series_id_fkey TO diferencia_version_serie_id_fkey;
ALTER TABLE oficial.diferencia_version RENAME CONSTRAINT known_version_difference_series_id_period_level_source_key TO diferencia_version_unica;
ALTER TABLE oficial.archivo_evidencia RENAME CONSTRAINT evidence_file_pkey TO archivo_evidencia_pkey;
ALTER TABLE oficial.archivo_evidencia RENAME CONSTRAINT evidence_file_manifest_source_sha256_downloaded_at_key TO archivo_evidencia_unico;
ALTER TABLE oficial.brecha_contexto RENAME CONSTRAINT context_gap_pkey TO brecha_contexto_pkey;
ALTER TABLE oficial.brecha_contexto RENAME CONSTRAINT context_gap_code_key TO brecha_contexto_codigo_key;
ALTER TABLE oficial.descarga RENAME CONSTRAINT download_pkey TO descarga_pkey;
ALTER TABLE oficial.descarga RENAME CONSTRAINT download_series_id_fkey TO descarga_serie_id_fkey;
ALTER TABLE oficial.archivo_original RENAME CONSTRAINT raw_file_pkey TO archivo_original_pkey;
ALTER TABLE oficial.archivo_original RENAME CONSTRAINT raw_file_download_id_fkey TO archivo_original_descarga_id_fkey;
ALTER TABLE oficial.observacion RENAME CONSTRAINT observation_pkey TO observacion_pkey;
ALTER TABLE oficial.observacion RENAME CONSTRAINT observation_seq_key TO observacion_secuencia_key;
ALTER TABLE oficial.observacion RENAME CONSTRAINT observation_series_id_fkey TO observacion_serie_id_fkey;
ALTER TABLE oficial.observacion RENAME CONSTRAINT observation_download_id_fkey TO observacion_descarga_id_fkey;
ALTER TABLE oficial.comparacion_contraste RENAME CONSTRAINT contrast_check_pkey TO comparacion_contraste_pkey;
ALTER TABLE oficial.comparacion_contraste RENAME CONSTRAINT contrast_check_observation_id_fkey TO comparacion_contraste_observacion_id_fkey;
ALTER TABLE oficial.alerta RENAME CONSTRAINT alert_pkey TO alerta_pkey;
ALTER TABLE oficial.alerta RENAME CONSTRAINT alert_series_id_fkey TO alerta_serie_id_fkey;
ALTER TABLE oficial.alerta RENAME CONSTRAINT alert_observation_id_fkey TO alerta_observacion_id_fkey;
ALTER TABLE oficial.evento_alerta RENAME CONSTRAINT alert_event_pkey TO evento_alerta_pkey;
ALTER TABLE oficial.evento_alerta RENAME CONSTRAINT alert_event_alert_id_fkey TO evento_alerta_alerta_id_fkey;

ALTER INDEX oficial.alert_event_alert_idx RENAME TO evento_alerta_alerta_idx;
ALTER INDEX oficial.contrast_check_observation_idx RENAME TO comparacion_contraste_observacion_idx;
ALTER INDEX oficial.download_series_idx RENAME TO descarga_serie_idx;
ALTER INDEX oficial.observation_latest_idx RENAME TO observacion_vigente_idx;
ALTER SEQUENCE oficial.observation_seq_seq RENAME TO observacion_secuencia_seq;

-- Las restricciones CHECK y el índice de "una alerta abierta" mencionan los valores
-- en inglés: se quitan aquí y se vuelven a crear en la parte 4, ya traducidos.
DROP INDEX oficial.alert_one_open_idx;
ALTER TABLE oficial.fuente DROP CONSTRAINT source_role_check;
ALTER TABLE oficial.indicador DROP CONSTRAINT indicator_category_check;
ALTER TABLE oficial.serie DROP CONSTRAINT series_frequency_check;
ALTER TABLE oficial.aprobacion_serie DROP CONSTRAINT series_approval_status_check;
ALTER TABLE oficial.diferencia_version DROP CONSTRAINT known_version_difference_level_check;
ALTER TABLE oficial.observacion DROP CONSTRAINT observation_period_check;
ALTER TABLE oficial.observacion DROP CONSTRAINT observation_status_check;
ALTER TABLE oficial.observacion DROP CONSTRAINT observation_contrast_status_check;
ALTER TABLE oficial.observacion DROP CONSTRAINT observation_contrast_level_check;
ALTER TABLE oficial.comparacion_contraste DROP CONSTRAINT contrast_check_level_check;
ALTER TABLE oficial.comparacion_contraste DROP CONSTRAINT contrast_check_outcome_check;
ALTER TABLE oficial.alerta DROP CONSTRAINT alert_status_check;
ALTER TABLE oficial.alerta ALTER COLUMN estado DROP DEFAULT;
ALTER TABLE oficial.evento_alerta DROP CONSTRAINT alert_event_event_check;

-- =============================================================================
-- PARTE 3 · Traducir los valores guardados
-- =============================================================================

-- Tablas de traducción temporales: desaparecen al terminar la migración.
CREATE FUNCTION pg_temp.nivel(v text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE v WHEN 'monthly' THEN 'mensual' WHEN 'annual' THEN 'anual' END
$$;
CREATE FUNCTION pg_temp.contraste(v text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE v WHEN 'passed' THEN 'paso' WHEN 'pending' THEN 'pendiente' WHEN 'not_applicable' THEN 'no_aplica'
                  WHEN 'unavailable' THEN 'no_disponible' WHEN 'failed' THEN 'fallo' END
$$;
CREATE FUNCTION pg_temp.marca(v text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE v
        WHEN 'missing_value' THEN 'valor_faltante'
        WHEN 'out_of_range' THEN 'fuera_de_rango'
        WHEN 'gap_before' THEN 'hueco_anterior'
        WHEN 'duplicate' THEN 'duplicada'
        WHEN 'jump' THEN 'salto'
        WHEN 'not_increasing' THEN 'no_creciente'
        WHEN 'contrast_pending' THEN 'contraste_pendiente'
        WHEN 'contrast_mismatch' THEN 'contraste_no_coincide'
        WHEN 'no_second_source' THEN 'sin_segunda_fuente'
        WHEN 'contrast_unavailable' THEN 'contraste_no_disponible'
        WHEN 'known_version_difference' THEN 'diferencia_version_conocida'
        WHEN 'producer_value_used' THEN 'valor_productor_usado'
        WHEN 'history_changed' THEN 'historia_cambio'
    END
$$;

UPDATE oficial.fuente SET rol = CASE rol WHEN 'producer' THEN 'productor' WHEN 'access_channel' THEN 'canal_acceso' END;
UPDATE oficial.indicador SET categoria = CASE categoria WHEN 'economy' THEN 'economia' WHEN 'security' THEN 'seguridad' END;
UPDATE oficial.serie SET frecuencia = pg_temp.nivel(frecuencia);
UPDATE oficial.aprobacion_serie
   SET estado = CASE estado WHEN 'pending' THEN 'pendiente' WHEN 'approved' THEN 'aprobada' WHEN 'rejected' THEN 'rechazada' END;
UPDATE oficial.diferencia_version SET nivel = pg_temp.nivel(nivel);
UPDATE oficial.observacion
   SET estado = CASE estado WHEN 'quarantined' THEN 'en_cuarentena' WHEN 'accepted' THEN 'aceptada' END,
       estado_contraste = pg_temp.contraste(estado_contraste),
       nivel_contraste = pg_temp.nivel(nivel_contraste),
       marcas = ARRAY(SELECT pg_temp.marca(m) FROM unnest(marcas) AS m ORDER BY 1);
UPDATE oficial.comparacion_contraste SET nivel = pg_temp.nivel(nivel), resultado = pg_temp.contraste(resultado);
UPDATE oficial.alerta
   SET tipo = pg_temp.marca(tipo),
       estado = CASE estado WHEN 'open' THEN 'abierta' WHEN 'closed' THEN 'cerrada' END;
UPDATE oficial.evento_alerta
   SET evento = CASE evento WHEN 'opened' THEN 'abierta' WHEN 'commented' THEN 'comentada'
                            WHEN 'closed' THEN 'cerrada' WHEN 'reopened' THEN 'reabierta' END,
       actor = CASE actor WHEN 'system' THEN 'sistema' ELSE actor END;

-- array_position(..., NULL) encuentra una marca que no se pudo traducir.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM oficial.observacion WHERE array_position(marcas, NULL) IS NOT NULL) THEN
        RAISE EXCEPTION 'observacion: hay una marca sin traducción';
    END IF;
END;
$$;

-- =============================================================================
-- PARTE 4 · Restricciones CHECK con nombre
-- =============================================================================

ALTER TABLE oficial.fuente ADD CONSTRAINT fuente_rol_valido CHECK (rol IN ('productor', 'canal_acceso'));
ALTER TABLE oficial.indicador ADD CONSTRAINT indicador_categoria_valida CHECK (categoria IN ('economia', 'seguridad'));
ALTER TABLE oficial.serie ADD CONSTRAINT serie_frecuencia_valida CHECK (frecuencia IN ('mensual', 'anual'));
ALTER TABLE oficial.aprobacion_serie
    ADD CONSTRAINT aprobacion_serie_estado_valido CHECK (estado IN ('pendiente', 'aprobada', 'rechazada'));
ALTER TABLE oficial.diferencia_version ADD CONSTRAINT diferencia_version_nivel_valido CHECK (nivel IN ('mensual', 'anual'));
ALTER TABLE oficial.observacion
    ADD CONSTRAINT observacion_periodo_valido CHECK (periodo ~ '^\d{4}(-\d{2}(-\d{2})?)?$'),
    ADD CONSTRAINT observacion_estado_valido CHECK (estado IN ('en_cuarentena', 'aceptada')),
    ADD CONSTRAINT observacion_estado_contraste_valido
        CHECK (estado_contraste IN ('paso', 'pendiente', 'no_aplica', 'no_disponible', 'fallo')),
    ADD CONSTRAINT observacion_nivel_contraste_valido CHECK (nivel_contraste IN ('mensual', 'anual')),
    ADD CONSTRAINT observacion_marcas_validas CHECK (marcas <@ ARRAY[
        'valor_faltante', 'fuera_de_rango', 'hueco_anterior', 'duplicada', 'salto', 'no_creciente',
        'contraste_pendiente', 'contraste_no_coincide', 'sin_segunda_fuente', 'contraste_no_disponible',
        'diferencia_version_conocida', 'valor_productor_usado', 'historia_cambio']::text[]);
ALTER TABLE oficial.comparacion_contraste
    ADD CONSTRAINT comparacion_contraste_nivel_valido CHECK (nivel IN ('mensual', 'anual')),
    ADD CONSTRAINT comparacion_contraste_resultado_valido CHECK (resultado IN ('paso', 'pendiente', 'fallo'));
ALTER TABLE oficial.alerta
    ALTER COLUMN estado SET DEFAULT 'abierta',
    ADD CONSTRAINT alerta_estado_valido CHECK (estado IN ('abierta', 'cerrada')),
    ADD CONSTRAINT alerta_tipo_valido CHECK (tipo IN (
        'valor_faltante', 'fuera_de_rango', 'hueco_anterior', 'duplicada', 'salto', 'no_creciente',
        'contraste_no_coincide', 'valor_productor_usado', 'historia_cambio'));
ALTER TABLE oficial.evento_alerta
    ADD CONSTRAINT evento_alerta_evento_valido CHECK (evento IN ('abierta', 'comentada', 'cerrada', 'reabierta'));

-- Una sola alerta abierta por serie, periodo, territorio, tipo y valor.
CREATE UNIQUE INDEX alerta_una_abierta_idx ON oficial.alerta (serie_id, periodo, territorio, tipo, valor)
    NULLS NOT DISTINCT WHERE estado = 'abierta';

-- =============================================================================
-- PARTE 5 · Triggers
-- =============================================================================

-- Historial y evidencia: solo inserción.
CREATE TRIGGER aprobacion_serie_solo_insercion BEFORE UPDATE OR DELETE ON oficial.aprobacion_serie
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER archivo_evidencia_solo_insercion BEFORE UPDATE OR DELETE ON oficial.archivo_evidencia
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER descarga_solo_insercion BEFORE UPDATE OR DELETE ON oficial.descarga
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER archivo_original_solo_insercion BEFORE UPDATE OR DELETE ON oficial.archivo_original
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER observacion_solo_insercion BEFORE UPDATE OR DELETE ON oficial.observacion
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER comparacion_contraste_solo_insercion BEFORE UPDATE OR DELETE ON oficial.comparacion_contraste
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER evento_alerta_solo_insercion BEFORE UPDATE OR DELETE ON oficial.evento_alerta
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- Copia del catálogo y alertas: se pueden modificar y registran cuándo.
CREATE TRIGGER fuente_actualizado BEFORE UPDATE ON oficial.fuente
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER indicador_actualizado BEFORE UPDATE ON oficial.indicador
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER serie_actualizado BEFORE UPDATE ON oficial.serie
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER nota_serie_actualizado BEFORE UPDATE ON oficial.nota_serie
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER diferencia_version_actualizado BEFORE UPDATE ON oficial.diferencia_version
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER brecha_contexto_actualizado BEFORE UPDATE ON oficial.brecha_contexto
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER alerta_actualizado BEFORE UPDATE ON oficial.alerta
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();

-- Una alerta solo puede cambiar de estado; nunca se borra.
CREATE FUNCTION oficial.alerta_solo_cambia_estado() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.serie_id, NEW.observacion_id, NEW.periodo, NEW.territorio, NEW.tipo, NEW.valor, NEW.creado_en)
       IS DISTINCT FROM (OLD.serie_id, OLD.observacion_id, OLD.periodo, OLD.territorio, OLD.tipo, OLD.valor, OLD.creado_en) THEN
        RAISE EXCEPTION 'oficial.alerta: solo puede cambiar el estado';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER alerta_solo_cambia_estado BEFORE UPDATE ON oficial.alerta
    FOR EACH ROW EXECUTE FUNCTION oficial.alerta_solo_cambia_estado();
CREATE TRIGGER alerta_transicion BEFORE UPDATE OF estado ON oficial.alerta
    FOR EACH ROW EXECUTE FUNCTION util.validar_transicion('{"abierta": ["cerrada"], "cerrada": ["abierta"]}');
CREATE TRIGGER alerta_sin_borrado BEFORE DELETE ON oficial.alerta
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- Todo cambio de estado de una alerta debe dejar su evento (quién y por qué) en la
-- misma transacción. Es diferido: se revisa al confirmar, cuando el evento ya existe.
-- evento_alerta.creado_en vale now(), que es la hora de inicio de la transacción.
CREATE FUNCTION oficial.alerta_cambio_con_evento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM oficial.evento_alerta e
        WHERE e.alerta_id = NEW.id
          AND e.evento = CASE NEW.estado WHEN 'cerrada' THEN 'cerrada' ELSE 'reabierta' END
          AND e.creado_en = now()
    ) THEN
        RAISE EXCEPTION 'oficial.alerta: el cambio a % no tiene su evento en evento_alerta', NEW.estado;
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER alerta_cambio_con_evento AFTER UPDATE OF estado ON oficial.alerta
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW WHEN (OLD.estado IS DISTINCT FROM NEW.estado)
    EXECUTE FUNCTION oficial.alerta_cambio_con_evento();

-- =============================================================================
-- PARTE 6 · Funciones y procedimientos del esquema oficial
-- =============================================================================

-- Valor vigente de cada periodo: la última versión (mayor secuencia) de una serie
-- aprobada, solo si está aceptada. Si la última versión está en cuarentena, ese
-- periodo no aparece: nunca se devuelve un valor anterior en su lugar.
CREATE FUNCTION oficial.observaciones_vigentes(p_codigo_serie text, p_desde text, p_hasta text)
RETURNS TABLE (observacion_id uuid, periodo text, territorio text, valor numeric, marcas text[])
LANGUAGE sql STABLE
SET search_path = ''
AS $$
    SELECT ultima.id, ultima.periodo, ultima.territorio, ultima.valor, ultima.marcas
    FROM (
        SELECT DISTINCT ON (o.periodo, o.territorio) o.*
        FROM oficial.observacion o
        JOIN oficial.serie s ON s.id = o.serie_id
        WHERE s.codigo = p_codigo_serie AND s.aprobada
          AND o.periodo BETWEEN p_desde AND p_hasta
        ORDER BY o.periodo, o.territorio, o.secuencia DESC
    ) AS ultima
    WHERE ultima.estado = 'aceptada'
    ORDER BY ultima.periodo, ultima.territorio;
$$;
COMMENT ON FUNCTION oficial.observaciones_vigentes(text, text, text)
    IS 'Valor vigente y aceptado de cada periodo de una serie aprobada, entre dos periodos';

CREATE FUNCTION oficial.observacion_en(p_codigo_serie text, p_periodo text, p_territorio text)
RETURNS TABLE (observacion_id uuid, periodo text, territorio text, valor numeric, marcas text[])
LANGUAGE sql STABLE
SET search_path = ''
AS $$
    SELECT * FROM oficial.observaciones_vigentes(p_codigo_serie, p_periodo, p_periodo) v
    WHERE v.territorio = p_territorio;
$$;
COMMENT ON FUNCTION oficial.observacion_en(text, text, text)
    IS 'El valor vigente de un periodo y territorio, o nada (y entonces no hay dato comparable)';

-- Para la evidencia de una verificación: la observación existe, está aceptada y es
-- la versión vigente de su periodo. SECURITY DEFINER porque la usan triggers de
-- otros esquemas sin permiso de leer las tablas de oficial.
CREATE FUNCTION oficial.esta_aceptada(p_observacion_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM oficial.observacion o
        WHERE o.id = p_observacion_id
          AND o.estado = 'aceptada'
          AND NOT EXISTS (
              SELECT 1 FROM oficial.observacion n
              WHERE n.serie_id = o.serie_id AND n.periodo = o.periodo
                AND n.territorio = o.territorio AND n.secuencia > o.secuencia)
    );
$$;
COMMENT ON FUNCTION oficial.esta_aceptada(uuid) IS 'Verdadero si la observación es la versión vigente de su periodo y está aceptada';

CREATE FUNCTION oficial.serie_aprobada(p_codigo text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT coalesce((SELECT s.aprobada FROM oficial.serie s WHERE s.codigo = p_codigo), false);
$$;
COMMENT ON FUNCTION oficial.serie_aprobada(text) IS 'Verdadero si la serie existe y su ficha está aprobada';

CREATE FUNCTION oficial.alertas_abiertas(p_codigo_serie text)
RETURNS TABLE (alerta_id uuid, periodo text, territorio text, tipo text, valor numeric, creado_en timestamptz)
LANGUAGE sql STABLE
SET search_path = ''
AS $$
    SELECT a.id, a.periodo, a.territorio, a.tipo, a.valor, a.creado_en
    FROM oficial.alerta a JOIN oficial.serie s ON s.id = a.serie_id
    WHERE s.codigo = p_codigo_serie AND a.estado = 'abierta'
    ORDER BY a.periodo, a.tipo;
$$;
COMMENT ON FUNCTION oficial.alertas_abiertas(text) IS 'Alertas abiertas de una serie, para mostrarlas junto a la cifra';

-- Cerrar y reabrir alertas: el estado y su evento van juntos, y FOR UPDATE impide
-- que dos revisores cambien la misma alerta al mismo tiempo.
CREATE PROCEDURE oficial.cerrar_alerta(p_alerta_id uuid, p_actor text, p_motivo text)
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF coalesce(trim(p_motivo), '') = '' THEN
        RAISE EXCEPTION 'alerta_sin_motivo: cerrar una alerta exige un motivo';
    END IF;
    PERFORM 1 FROM oficial.alerta WHERE id = p_alerta_id AND estado = 'abierta' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'alerta_no_abierta: la alerta % no existe o ya está cerrada', p_alerta_id;
    END IF;
    UPDATE oficial.alerta SET estado = 'cerrada' WHERE id = p_alerta_id;
    INSERT INTO oficial.evento_alerta (alerta_id, evento, actor, motivo)
    VALUES (p_alerta_id, 'cerrada', p_actor, p_motivo);
END;
$$;
COMMENT ON PROCEDURE oficial.cerrar_alerta(uuid, text, text) IS 'Cierra una alerta abierta y deja su evento con quién y por qué';

CREATE PROCEDURE oficial.reabrir_alerta(p_alerta_id uuid, p_actor text, p_motivo text)
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF coalesce(trim(p_motivo), '') = '' THEN
        RAISE EXCEPTION 'alerta_sin_motivo: reabrir una alerta exige un motivo';
    END IF;
    PERFORM 1 FROM oficial.alerta WHERE id = p_alerta_id AND estado = 'cerrada' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'alerta_no_cerrada: la alerta % no existe o ya está abierta', p_alerta_id;
    END IF;
    UPDATE oficial.alerta SET estado = 'abierta' WHERE id = p_alerta_id;
    INSERT INTO oficial.evento_alerta (alerta_id, evento, actor, motivo)
    VALUES (p_alerta_id, 'reabierta', p_actor, p_motivo);
END;
$$;
COMMENT ON PROCEDURE oficial.reabrir_alerta(uuid, text, text) IS 'Reabre una alerta cerrada y deja su evento con quién y por qué';

-- =============================================================================
-- PARTE 7 · Descripción de las tablas
-- =============================================================================

COMMENT ON TABLE oficial.fuente IS 'Productores (DANE, Policía…) y canales de acceso (SUAMECA, datos.gov.co). Copia de git';
COMMENT ON TABLE oficial.indicador IS 'Los 8 indicadores de la v1. Copia de git';
COMMENT ON TABLE oficial.serie IS 'Una ficha del catálogo: qué se mide, cómo y de dónde. Copia de git';
COMMENT ON TABLE oficial.aprobacion_serie IS 'Cada estado de aprobación visto en git, aunque la ficha cambie después. Solo inserción';
COMMENT ON TABLE oficial.nota_serie IS 'Notas de una serie (cambios de metodología, conflictos entre fuentes). Copia de git';
COMMENT ON TABLE oficial.diferencia_version IS 'Diferencias conocidas entre fuentes, con el valor exacto de cada una. Copia de git';
COMMENT ON TABLE oficial.archivo_evidencia IS 'Líneas de los manifiestos de evidencia (publicaciones oficiales descargadas). Solo inserción';
COMMENT ON TABLE oficial.brecha_contexto IS 'Catálogo de brechas de contexto que detectan las pruebas de robustez';
COMMENT ON TABLE oficial.descarga IS 'Una descarga de una serie desde su canal. Solo inserción';
COMMENT ON TABLE oficial.archivo_original IS 'Los archivos originales de una descarga, con su huella. Solo inserción';
COMMENT ON TABLE oficial.observacion IS 'Un valor oficial de un periodo; una versión nueva es una fila nueva. Solo inserción';
COMMENT ON TABLE oficial.comparacion_contraste IS 'Cada comparación contra una segunda fuente detrás del estado de contraste. Solo inserción';
COMMENT ON TABLE oficial.alerta IS 'Marca que pide revisión humana. Solo cambia de estado, y siempre con su evento';
COMMENT ON TABLE oficial.evento_alerta IS 'Historial de cada alerta: quién, cuándo y por qué. Solo inserción';
