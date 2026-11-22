-- 0013 · Cobertura y actividad de los temas del día (segunda etapa, T6).
--
-- La app muestra de cada tema qué medios lo cubren (la "huella de cobertura": los medios registrados,
-- encendidos los que lo cubren) y cómo se repartieron sus artículos en la ventana de 24 horas. Todo
-- sale de los artículos guardados: no hay nada estimado ni redactado por la IA.
--
-- Cobertura no es importancia ni veracidad: estas funciones solo cuentan.

BEGIN;

-- Medios que cubren un tema, con cuántos artículos y cuándo publicó cada uno el primero.
CREATE FUNCTION temas.cobertura_tema(p_tema_id uuid)
RETURNS TABLE (medio text, articulos integer, primero timestamptz)
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT m.nombre, count(*)::integer, min(a.publicado_en)
    FROM temas.tema_articulo ta
    JOIN temas.articulo a ON a.id = ta.articulo_id
    JOIN temas.medio m ON m.id = a.medio_id
    WHERE ta.tema_id = p_tema_id
    GROUP BY m.nombre
    ORDER BY min(a.publicado_en), m.nombre;
$$;
COMMENT ON FUNCTION temas.cobertura_tema(uuid)
    IS 'Medios que cubren un tema: artículos de cada uno y hora del primero';

-- Artículos de un tema por tramo de su ventana (por defecto 8 tramos de 3 horas). Los artículos
-- publicados antes de la ventana (los RSS traen algunos anteriores) cuentan en el primer tramo y los
-- posteriores en el último, para que la suma siempre sea el total del tema.
CREATE FUNCTION temas.actividad_tema(p_tema_id uuid, p_tramos integer DEFAULT 8)
RETURNS TABLE (tramo integer, desde timestamptz, articulos integer)
LANGUAGE sql STABLE SET search_path = '' AS $$
    WITH t AS (
        SELECT ventana_inicio, ventana_fin FROM temas.tema WHERE id = p_tema_id
    ), conteo AS (
        SELECT greatest(1, least(p_tramos, width_bucket(
                   extract(epoch FROM a.publicado_en),
                   extract(epoch FROM t.ventana_inicio), extract(epoch FROM t.ventana_fin), p_tramos))) AS tramo,
               count(*)::integer AS articulos
        FROM t
        JOIN temas.tema_articulo ta ON ta.tema_id = p_tema_id
        JOIN temas.articulo a ON a.id = ta.articulo_id
        GROUP BY 1
    )
    SELECT n, t.ventana_inicio + (t.ventana_fin - t.ventana_inicio) * (n - 1) / p_tramos, coalesce(c.articulos, 0)
    FROM t CROSS JOIN generate_series(1, p_tramos) AS n
    LEFT JOIN conteo c ON c.tramo = n
    WHERE p_tramos BETWEEN 1 AND 48
    ORDER BY n;
$$;
COMMENT ON FUNCTION temas.actividad_tema(uuid, integer)
    IS 'Artículos de un tema por tramo de su ventana; la suma es el total del tema';

-- Los permisos por defecto quitan EXECUTE a PUBLIC (0007): se dan solo al servicio de temas.
GRANT EXECUTE ON FUNCTION temas.cobertura_tema(uuid), temas.actividad_tema(uuid, integer) TO svc_temas;

COMMIT;
