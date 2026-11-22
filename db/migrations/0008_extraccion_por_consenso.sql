-- 0008: extracción por consenso (decisión 26).
--
-- Cada texto que pasa el filtro previo lo leen dos modelos de proveedores distintos.
-- En ia: un trabajo puede exigir un proveedor, y la caché distingue por proveedor.
-- En verificacion: la base compara las dos lecturas; si coinciden, la afirmación
-- sigue al motor de reglas; si difieren, queda en "requiere revisión".

-- =============================================================================
-- PARTE 1 · ia: un trabajo puede exigir un proveedor
-- =============================================================================

ALTER TABLE ia.trabajo
    ADD COLUMN proveedor text,
    ADD CONSTRAINT trabajo_proveedor_valido CHECK (proveedor ~ '^[a-z0-9_]{2,30}$');
COMMENT ON COLUMN ia.trabajo.proveedor IS 'Proveedor exigido (consenso); nulo si cualquiera sirve';

-- La caché y el "no encolar dos veces" ahora distinguen el proveedor.
DROP INDEX ia.trabajo_resultado_unico_idx;
DROP INDEX ia.trabajo_pendiente_unico_idx;
CREATE UNIQUE INDEX trabajo_resultado_unico_idx ON ia.trabajo (tipo, version_prompt, coalesce(proveedor, ''), huella_entrada)
    WHERE estado = 'terminado';
CREATE UNIQUE INDEX trabajo_pendiente_unico_idx ON ia.trabajo (tipo, version_prompt, coalesce(proveedor, ''), huella_entrada)
    WHERE estado IN ('en_cola', 'en_curso');

-- El proveedor exigido tampoco cambia después de encolar.
CREATE OR REPLACE FUNCTION ia.trabajo_cambios_permitidos() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id, NEW.tipo, NEW.version_prompt, NEW.entrada, NEW.huella_entrada, NEW.proveedor, NEW.creado_en)
       IS DISTINCT FROM (OLD.id, OLD.tipo, OLD.version_prompt, OLD.entrada, OLD.huella_entrada, OLD.proveedor, OLD.creado_en) THEN
        RAISE EXCEPTION 'ia.trabajo: el tipo, la versión del prompt, la entrada y el proveedor no cambian';
    END IF;
    RETURN NEW;
END;
$$;

-- Encolar con proveedor (nulo = cualquiera).
DROP PROCEDURE ia.encolar_trabajo(text, text, jsonb, uuid, boolean);
CREATE PROCEDURE ia.encolar_trabajo(
    p_tipo text, p_version_prompt text, p_entrada jsonb, p_proveedor text,
    INOUT p_trabajo_id uuid, INOUT p_desde_cache boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_huella text := encode(sha256(convert_to(p_entrada::text, 'UTF8')), 'hex');
BEGIN
    SELECT id INTO p_trabajo_id FROM ia.trabajo
    WHERE tipo = p_tipo AND version_prompt = p_version_prompt AND huella_entrada = v_huella
      AND proveedor IS NOT DISTINCT FROM p_proveedor AND estado = 'terminado';
    IF FOUND THEN
        p_desde_cache := true;
        RETURN;
    END IF;
    p_desde_cache := false;
    INSERT INTO ia.trabajo (tipo, version_prompt, entrada, proveedor)
    VALUES (p_tipo, p_version_prompt, p_entrada, p_proveedor)
    ON CONFLICT (tipo, version_prompt, coalesce(proveedor, ''), huella_entrada) WHERE estado IN ('en_cola', 'en_curso')
    DO NOTHING
    RETURNING id INTO p_trabajo_id;
    IF p_trabajo_id IS NULL THEN
        SELECT id INTO p_trabajo_id FROM ia.trabajo
        WHERE tipo = p_tipo AND version_prompt = p_version_prompt AND huella_entrada = v_huella
          AND proveedor IS NOT DISTINCT FROM p_proveedor AND estado IN ('en_cola', 'en_curso');
    END IF;
END;
$$;
COMMENT ON PROCEDURE ia.encolar_trabajo(text, text, jsonb, text, uuid, boolean)
    IS 'Encola un trabajo (con proveedor exigido o no), o devuelve el ya resuelto (caché) o el ya pendiente';

-- Un trabajador solo toma trabajos que puede atender: sin proveedor exigido, o de
-- un proveedor que tiene alguna cuenta disponible.
DROP FUNCTION ia.tomar_trabajo(text[]);
CREATE FUNCTION ia.tomar_trabajo(p_tipos text[], p_proveedores text[]) RETURNS SETOF ia.trabajo
LANGUAGE sql VOLATILE AS $$
    UPDATE ia.trabajo t
    SET estado = 'en_curso',
        proximo_intento_en = now() + interval '5 minutes'
    WHERE t.id = (
        SELECT c.id FROM ia.trabajo c
        WHERE c.tipo = ANY (p_tipos)
          AND (c.proveedor IS NULL OR c.proveedor = ANY (p_proveedores))
          AND c.estado IN ('en_cola', 'en_curso')
          AND c.proximo_intento_en <= now()
        ORDER BY c.proximo_intento_en
        FOR UPDATE SKIP LOCKED
        LIMIT 1)
    RETURNING t.*;
$$;
COMMENT ON FUNCTION ia.tomar_trabajo(text[], text[])
    IS 'Toma un trabajo listo de un proveedor disponible, sin chocar con otros trabajadores (FOR UPDATE SKIP LOCKED)';

-- =============================================================================
-- PARTE 2 · verificacion: comparar las dos lecturas
-- =============================================================================

ALTER TABLE verificacion.afirmacion
    ADD COLUMN trabajo_ia_2_id uuid,       -- lógica -> ia.trabajo (la segunda lectura)
    ADD COLUMN consenso text,
    ADD CONSTRAINT afirmacion_consenso_valido CHECK (consenso IN ('coinciden', 'difieren')),
    -- Si las lecturas difieren, la afirmación no puede seguir sola al motor de reglas.
    ADD CONSTRAINT afirmacion_difieren_en_revision CHECK (consenso IS DISTINCT FROM 'difieren' OR estado <> 'extraida');
COMMENT ON COLUMN verificacion.afirmacion.consenso IS 'Resultado de comparar las dos lecturas (decisión 26)';

-- Una lectura en forma comparable: solo lo que el motor usa, en orden fijo, con las
-- cifras sin ceros sobrantes (8,20 y 8,2 son la misma cifra).
CREATE FUNCTION verificacion.normalizar_lectura(p_lectura jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(jsonb_agg(f ORDER BY f::text), '[]'::jsonb)
    FROM (
        SELECT jsonb_build_object(
            'codigo_indicador', x->>'codigo_indicador',
            'variante', x->>'variante',
            'periodo_desde', x->>'periodo_desde',
            'periodo_hasta', x->>'periodo_hasta',
            'territorio', x->>'territorio',
            'valor_dicho', trim_scale((x->>'valor_dicho')::numeric)) AS f
        FROM jsonb_array_elements(coalesce(p_lectura, '[]'::jsonb)) AS x
    ) AS afirmaciones;
$$;
COMMENT ON FUNCTION verificacion.normalizar_lectura(jsonb) IS 'Lectura de la IA en forma comparable (orden fijo, cifras sin ceros sobrantes)';

CREATE FUNCTION verificacion.lecturas_coinciden(p_a jsonb, p_b jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT verificacion.normalizar_lectura(p_a) = verificacion.normalizar_lectura(p_b);
$$;
COMMENT ON FUNCTION verificacion.lecturas_coinciden(jsonb, jsonb)
    IS 'Verdadero si dos lecturas dicen lo mismo: indicador, variante, periodo, territorio y valor';

-- Guarda el resultado de las dos lecturas en una transacción:
--   las dos vacías           -> el texto no tiene afirmaciones (es opinión)
--   coinciden                -> afirmaciones "extraida", siguen al motor de reglas
--   difieren                 -> afirmaciones "requiere_revision": las revisa una persona
CREATE PROCEDURE verificacion.registrar_afirmaciones_consenso(
    p_origen_tipo text, p_origen_id uuid, p_trabajo_a uuid, p_trabajo_b uuid,
    p_lectura_a jsonb, p_lectura_b jsonb, INOUT p_guardadas int, INOUT p_consenso text)
LANGUAGE plpgsql AS $$
DECLARE
    v_base jsonb;
BEGIN
    p_consenso := CASE WHEN verificacion.lecturas_coinciden(p_lectura_a, p_lectura_b) THEN 'coinciden' ELSE 'difieren' END;
    v_base := CASE WHEN jsonb_array_length(coalesce(p_lectura_a, '[]')) > 0 THEN p_lectura_a ELSE p_lectura_b END;

    INSERT INTO verificacion.afirmacion (
        publicacion_id, declaracion_id, declaracion_reportada_id, posicion, texto_citado, codigo_indicador,
        variante, periodo_desde, periodo_hasta, territorio, valor_dicho, unidad_dicha, comparacion,
        confianza_extraccion, trabajo_ia_id, trabajo_ia_2_id, consenso, estado)
    SELECT CASE WHEN p_origen_tipo = 'publicacion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion_reportada' THEN p_origen_id END,
           n, f->>'texto_citado', f->>'codigo_indicador', f->>'variante', f->>'periodo_desde', f->>'periodo_hasta',
           f->>'territorio', (f->>'valor_dicho')::numeric, f->>'unidad_dicha', f->>'comparacion',
           coalesce((f->>'confianza')::numeric, 0), p_trabajo_a, p_trabajo_b, p_consenso,
           CASE WHEN p_consenso = 'coinciden' THEN 'extraida' ELSE 'requiere_revision' END
    FROM jsonb_array_elements(coalesce(v_base, '[]')) WITH ORDINALITY AS x(f, n);
    GET DIAGNOSTICS p_guardadas = ROW_COUNT;

    CALL verificacion.registrar_procesamiento(p_origen_tipo, p_origen_id,
        CASE WHEN p_guardadas > 0 THEN 'con_afirmaciones' ELSE 'sin_afirmaciones' END);
END;
$$;
COMMENT ON PROCEDURE verificacion.registrar_afirmaciones_consenso(text, uuid, uuid, uuid, jsonb, jsonb, int, text)
    IS 'Compara las dos lecturas de la IA y guarda las afirmaciones: si difieren, quedan en revisión';

-- =============================================================================
-- PARTE 3 · Permisos de lo nuevo (0007 quitó el permiso por defecto)
-- =============================================================================

GRANT EXECUTE ON PROCEDURE ia.encolar_trabajo(text, text, jsonb, text, uuid, boolean) TO svc_verificacion, svc_temas;
GRANT EXECUTE ON FUNCTION ia.tomar_trabajo(text[], text[]) TO svc_ia;
GRANT EXECUTE ON FUNCTION verificacion.normalizar_lectura(jsonb), verificacion.lecturas_coinciden(jsonb, jsonb)
    TO svc_verificacion;
GRANT EXECUTE ON PROCEDURE verificacion.registrar_afirmaciones_consenso(text, uuid, uuid, uuid, jsonb, jsonb, int, text)
    TO svc_verificacion;
