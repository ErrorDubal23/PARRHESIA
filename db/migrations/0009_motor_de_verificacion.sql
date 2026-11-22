-- 0009: lo que el motor de verificación necesita leer de oficial, y la dirección de una afirmación.
--
-- El servicio de verificación no lee las tablas de oficial (decisión 13): usa estas
-- funciones SECURITY DEFINER. Y para decidir "se invierte" hace falta saber si el
-- texto dice que algo subió o bajó: la lectura de la IA ahora incluye la dirección.

-- =============================================================================
-- PARTE 1 · Funciones de oficial para el motor
-- =============================================================================

-- Series aprobadas de un indicador y una variante del catálogo, la del productor
-- primero (el DANE antes que SUAMECA): el valor oficial es el del productor.
CREATE FUNCTION oficial.series_candidatas(p_indicador text, p_variante text)
RETURNS TABLE (codigo text, nombre text, frecuencia text, fuente text, directa_del_productor boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT s.codigo, s.nombre, s.frecuencia, p.nombre, s.fuente_productora_id = s.fuente_canal_id
    FROM oficial.serie s
    JOIN oficial.indicador i ON i.id = s.indicador_id
    JOIN oficial.fuente p ON p.id = s.fuente_productora_id
    WHERE i.codigo = p_indicador AND s.variante = p_variante AND s.aprobada
    ORDER BY (s.fuente_productora_id = s.fuente_canal_id) DESC, s.codigo;
$$;
COMMENT ON FUNCTION oficial.series_candidatas(text, text)
    IS 'Series aprobadas para un indicador y una variante; primero la que viene directa del productor';

-- Notas de una serie que se cruzan con un periodo (cambio de metodología, ajuste, conflicto entre fuentes).
CREATE FUNCTION oficial.notas_en(p_codigo_serie text, p_periodo text)
RETURNS TABLE (clave_nota text, tipo text, estado text, contenido jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT n.clave_nota, n.tipo, n.estado, n.contenido
    FROM oficial.nota_serie n JOIN oficial.serie s ON s.id = n.serie_id
    WHERE s.codigo = p_codigo_serie
      AND (n.vigente_desde IS NULL OR n.vigente_desde <= p_periodo)
      AND (n.vigente_hasta IS NULL OR p_periodo <= n.vigente_hasta || '-99')
    ORDER BY n.clave_nota;
$$;
COMMENT ON FUNCTION oficial.notas_en(text, text) IS 'Notas de una serie vigentes en un periodo';

-- Detalle de observaciones para mostrar la evidencia de una verificación.
CREATE FUNCTION oficial.detalle_observaciones(p_ids uuid[])
RETURNS TABLE (observacion_id uuid, codigo_serie text, nombre_serie text, fuente text, periodo text,
               territorio text, valor numeric, marcas text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT o.id, s.codigo, s.nombre, p.nombre, o.periodo, o.territorio, o.valor, o.marcas
    FROM oficial.observacion o
    JOIN oficial.serie s ON s.id = o.serie_id
    JOIN oficial.fuente p ON p.id = s.fuente_productora_id
    WHERE o.id = ANY (p_ids);
$$;
COMMENT ON FUNCTION oficial.detalle_observaciones(uuid[]) IS 'Serie, fuente, periodo y valor de unas observaciones (evidencia)';

GRANT EXECUTE ON FUNCTION oficial.series_candidatas(text, text), oficial.notas_en(text, text),
                          oficial.detalle_observaciones(uuid[]) TO svc_verificacion;

-- =============================================================================
-- PARTE 2 · La dirección de una afirmación ("subió", "bajó")
-- =============================================================================

ALTER TABLE verificacion.afirmacion
    ADD COLUMN direccion text,
    ADD CONSTRAINT afirmacion_direccion_valida CHECK (direccion IN ('sube', 'baja'));
COMMENT ON COLUMN verificacion.afirmacion.direccion IS 'Si el texto dice que el indicador subió o bajó; nulo si no lo dice';

-- La dirección también cuenta para el consenso.
CREATE OR REPLACE FUNCTION verificacion.normalizar_lectura(p_lectura jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(jsonb_agg(f ORDER BY f::text), '[]'::jsonb)
    FROM (
        SELECT jsonb_build_object(
            'codigo_indicador', x->>'codigo_indicador',
            'variante', x->>'variante',
            'periodo_desde', x->>'periodo_desde',
            'periodo_hasta', x->>'periodo_hasta',
            'territorio', x->>'territorio',
            'valor_dicho', trim_scale((x->>'valor_dicho')::numeric),
            'direccion', x->>'direccion') AS f
        FROM jsonb_array_elements(coalesce(p_lectura, '[]'::jsonb)) AS x
    ) AS afirmaciones;
$$;

CREATE OR REPLACE PROCEDURE verificacion.registrar_afirmaciones_consenso(
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
        variante, periodo_desde, periodo_hasta, territorio, valor_dicho, unidad_dicha, comparacion, direccion,
        confianza_extraccion, trabajo_ia_id, trabajo_ia_2_id, consenso, estado)
    SELECT CASE WHEN p_origen_tipo = 'publicacion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion_reportada' THEN p_origen_id END,
           n, f->>'texto_citado', f->>'codigo_indicador', f->>'variante', f->>'periodo_desde', f->>'periodo_hasta',
           f->>'territorio', (f->>'valor_dicho')::numeric, f->>'unidad_dicha', f->>'comparacion', f->>'direccion',
           coalesce((f->>'confianza')::numeric, 0), p_trabajo_a, p_trabajo_b, p_consenso,
           CASE WHEN p_consenso = 'coinciden' THEN 'extraida' ELSE 'requiere_revision' END
    FROM jsonb_array_elements(coalesce(v_base, '[]')) WITH ORDINALITY AS x(f, n);
    GET DIAGNOSTICS p_guardadas = ROW_COUNT;

    CALL verificacion.registrar_procesamiento(p_origen_tipo, p_origen_id,
        CASE WHEN p_guardadas > 0 THEN 'con_afirmaciones' ELSE 'sin_afirmaciones' END);
END;
$$;
