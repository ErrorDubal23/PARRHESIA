-- 0022 · Corrige 0021: cuando las dos lecturas traen la misma afirmación con cifras distintas
-- ("8,2 %" frente a "8,9 %" del mismo indicador y periodo), se guarda UNA afirmación en revisión, no dos.

CREATE OR REPLACE PROCEDURE verificacion.registrar_afirmaciones_consenso(
    p_origen_tipo text, p_origen_id uuid, p_trabajo_a uuid, p_trabajo_b uuid,
    p_lectura_a jsonb, p_lectura_b jsonb, INOUT p_guardadas int, INOUT p_consenso text)
LANGUAGE plpgsql AS $$
DECLARE
    a jsonb := coalesce(p_lectura_a, '[]');
    b jsonb := coalesce(p_lectura_b, '[]');
    usadas_b int[] := '{}';
    filas jsonb := '[]';      -- cada elemento: {"f": afirmación, "consenso": coinciden|difieren}
    f jsonb;
    g jsonb;
    j int;
    encontrada int;
    coinciden int := 0;
BEGIN
    -- 1. Cada afirmación de la lectura A busca su pareja idéntica en B.
    FOR f IN SELECT x FROM jsonb_array_elements(a) AS x LOOP
        encontrada := NULL;
        FOR j IN 0 .. jsonb_array_length(b) - 1 LOOP
            IF NOT j = ANY (usadas_b)
               AND verificacion.clave_afirmacion(b->j) = verificacion.clave_afirmacion(f) THEN
                encontrada := j;
                EXIT;
            END IF;
        END LOOP;
        IF encontrada IS NOT NULL THEN
            usadas_b := usadas_b || encontrada;
            filas := filas || jsonb_build_array(jsonb_build_object('f', f, 'consenso', 'coinciden'));
            coinciden := coinciden + 1;
        ELSE
            filas := filas || jsonb_build_array(jsonb_build_object('f', f, 'consenso', 'difieren'));
        END IF;
    END LOOP;
    -- 2. Lo que solo leyó B va a revisión, salvo que sea la MISMA afirmación que A ya dejó en revisión
    --    (mismo indicador y misma cifra, o mismo indicador, periodo, variante y comparación con otra cifra).
    FOR j IN 0 .. jsonb_array_length(b) - 1 LOOP
        IF j = ANY (usadas_b) THEN
            CONTINUE;
        END IF;
        g := b->j;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(filas) AS r
            WHERE r->>'consenso' = 'difieren'
              AND r->'f'->>'codigo_indicador' IS NOT DISTINCT FROM g->>'codigo_indicador'
              AND (trim_scale((r->'f'->>'valor_dicho')::numeric) = trim_scale((g->>'valor_dicho')::numeric)
                   OR (r->'f'->>'periodo_hasta' IS NOT DISTINCT FROM g->>'periodo_hasta'
                       AND r->'f'->>'variante' IS NOT DISTINCT FROM g->>'variante'
                       AND coalesce(r->'f'->>'comparacion', 'nivel') = coalesce(g->>'comparacion', 'nivel')))) THEN
            filas := filas || jsonb_build_array(jsonb_build_object('f', g, 'consenso', 'difieren'));
        END IF;
    END LOOP;

    p_consenso := CASE WHEN jsonb_array_length(filas) = 0 OR coinciden = jsonb_array_length(filas) THEN 'coinciden'
                       WHEN coinciden = 0 THEN 'difieren' ELSE 'parcial' END;

    INSERT INTO verificacion.afirmacion (
        publicacion_id, declaracion_id, declaracion_reportada_id, posicion, texto_citado, codigo_indicador,
        variante, periodo_desde, periodo_hasta, territorio, valor_dicho, unidad_dicha, comparacion, direccion,
        confianza_extraccion, trabajo_ia_id, trabajo_ia_2_id, consenso, estado)
    SELECT CASE WHEN p_origen_tipo = 'publicacion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion_reportada' THEN p_origen_id END,
           n, r->'f'->>'texto_citado', r->'f'->>'codigo_indicador', r->'f'->>'variante', r->'f'->>'periodo_desde',
           r->'f'->>'periodo_hasta', r->'f'->>'territorio', (r->'f'->>'valor_dicho')::numeric, r->'f'->>'unidad_dicha',
           r->'f'->>'comparacion', r->'f'->>'direccion', coalesce((r->'f'->>'confianza')::numeric, 0),
           p_trabajo_a, p_trabajo_b, r->>'consenso',
           CASE WHEN r->>'consenso' = 'coinciden' THEN 'extraida' ELSE 'requiere_revision' END
    FROM jsonb_array_elements(filas) WITH ORDINALITY AS x(r, n);
    GET DIAGNOSTICS p_guardadas = ROW_COUNT;

    CALL verificacion.registrar_procesamiento(p_origen_tipo, p_origen_id,
        CASE WHEN p_guardadas > 0 THEN 'con_afirmaciones' ELSE 'sin_afirmaciones' END);
END;
$$;
COMMENT ON PROCEDURE verificacion.registrar_afirmaciones_consenso(text, uuid, uuid, uuid, jsonb, jsonb, int, text)
    IS 'Decisión 33: consenso por afirmación; lo que coincide sigue al motor, lo demás va a revisión humana';
