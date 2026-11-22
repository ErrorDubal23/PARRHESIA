-- 0029 · Una serie por dato en la página de datos oficiales.
--
-- La inflación anual y la tasa de desempleo aparecían dos veces: las dos son del DANE, una leída
-- directamente del DANE y otra a través del Banco de la República (SUAMECA). La segunda no es otro dato:
-- es el canal que sirve de contraste (filtro 5). La lista muestra una serie por indicador, variante y
-- territorio, con la misma prioridad que usa el motor (oficial.series_candidatas: primero la que viene
-- directa del productor), y dice por qué otros canales llega la misma serie.

CREATE FUNCTION oficial.series_publicas()
RETURNS TABLE (codigo text, otros_canales jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    WITH ordenadas AS (
        SELECT s.codigo, s.indicador_id, s.variante, s.geografia, c.nombre AS canal,
               row_number() OVER (PARTITION BY s.indicador_id, s.variante, s.geografia
                                  ORDER BY (s.fuente_productora_id = s.fuente_canal_id) DESC, s.codigo) AS orden
        FROM oficial.serie s JOIN oficial.fuente c ON c.id = s.fuente_canal_id
        WHERE s.aprobada)
    SELECT p.codigo,
           coalesce((SELECT jsonb_agg(jsonb_build_object('codigo', o.codigo, 'canal', o.canal) ORDER BY o.codigo)
                     FROM ordenadas o
                     WHERE o.indicador_id = p.indicador_id AND o.variante = p.variante
                       AND o.geografia = p.geografia AND o.orden > 1), '[]')
    FROM ordenadas p WHERE p.orden = 1;
$$;
COMMENT ON FUNCTION oficial.series_publicas()
    IS 'Una serie por indicador, variante y territorio (la directa del productor primero) y los otros canales de la misma serie';
GRANT EXECUTE ON FUNCTION oficial.series_publicas() TO svc_oficial;
