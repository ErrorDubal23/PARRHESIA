-- 0011: la explicación puede mostrar el valor oficial redondeado (decisión 27, por confirmar).
--
-- Algunas fuentes publican el valor sin redondear (el anexo de la GEIH: 9,3636797…).
-- La explicación puede mostrarlo con 0, 1 o 2 decimales (como "9,4 %"): es el mismo
-- dato publicado, redondeado para leerse, no una cifra nueva. La evidencia guarda y
-- la API devuelve siempre el valor exacto. Cualquier otra cifra se sigue rechazando.

CREATE OR REPLACE FUNCTION verificacion.cifras_permitidas(p_verificacion_id uuid) RETURNS numeric[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(array_agg(DISTINCT n), '{}') FROM (
        SELECT o.valor AS n
        FROM verificacion.evidencia e JOIN oficial.observacion o ON o.id = e.observacion_id
        WHERE e.verificacion_id = p_verificacion_id AND o.valor IS NOT NULL
        UNION ALL
        SELECT round(o.valor, d)
        FROM verificacion.evidencia e JOIN oficial.observacion o ON o.id = e.observacion_id,
             generate_series(0, 2) AS d
        WHERE e.verificacion_id = p_verificacion_id AND o.valor IS NOT NULL
        UNION ALL
        SELECT parte::numeric
        FROM verificacion.evidencia e JOIN oficial.observacion o ON o.id = e.observacion_id,
             LATERAL unnest(string_to_array(o.periodo, '-')) AS parte
        WHERE e.verificacion_id = p_verificacion_id
        UNION ALL
        SELECT a.valor_dicho
        FROM verificacion.verificacion v JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id
        WHERE v.id = p_verificacion_id AND a.valor_dicho IS NOT NULL
        UNION ALL
        SELECT parte::numeric
        FROM verificacion.verificacion v JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id,
             LATERAL unnest(string_to_array(concat_ws('-', a.periodo_desde, a.periodo_hasta), '-')) AS parte
        WHERE v.id = p_verificacion_id AND parte <> ''
    ) AS permitidas;
$$;
