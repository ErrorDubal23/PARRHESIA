-- 0010: un trabajo fallido es definitivo para esa entrada y esa versión del prompt.
--
-- Antes, volver a encolar una entrada cuyo trabajo había fallado creaba un trabajo
-- nuevo, y quien lo esperaba nunca se enteraba del fallo (lo encontró la prueba de
-- punta a punta). Ahora encolar devuelve el trabajo fallido: quien lo pidió usa su
-- respaldo (por ejemplo, la explicación armada por reglas) o deja el texto en
-- revisión. Para reintentar, se publica una versión nueva del prompt.

CREATE OR REPLACE PROCEDURE ia.encolar_trabajo(
    p_tipo text, p_version_prompt text, p_entrada jsonb, p_proveedor text,
    INOUT p_trabajo_id uuid, INOUT p_desde_cache boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_huella text := encode(sha256(convert_to(p_entrada::text, 'UTF8')), 'hex');
BEGIN
    -- Terminado (caché) o fallido (definitivo): se devuelve el que ya existe.
    SELECT id, estado = 'terminado' INTO p_trabajo_id, p_desde_cache FROM ia.trabajo
    WHERE tipo = p_tipo AND version_prompt = p_version_prompt AND huella_entrada = v_huella
      AND proveedor IS NOT DISTINCT FROM p_proveedor AND estado IN ('terminado', 'fallido')
    ORDER BY (estado = 'terminado') DESC, creado_en DESC
    LIMIT 1;
    IF FOUND THEN
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
    IS 'Encola un trabajo, o devuelve el ya resuelto (caché), el ya fallido (definitivo) o el ya pendiente';
