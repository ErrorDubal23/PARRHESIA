-- 0026 · Corrige 0025 con noticias reales (21 nov 2026): en una nota de Infobae pasaban 7 fragmentos (14
-- lecturas de IA) y varios solo tenían un año ("el salario mínimo para 2027"). En un enlace, un fragmento
-- necesita además una cifra que NO sea un año: un año solo fecha lo que se dice, no es el valor de un
-- indicador. Las publicaciones no cambian (requiere_extraccion sigue igual).

CREATE FUNCTION verificacion.fragmento_verificable(p_texto text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT verificacion.requiere_extraccion(p_texto)
       AND EXISTS (SELECT 1 FROM unnest(util.cifras_en_texto(p_texto)) AS c
                   WHERE NOT (c = trunc(c) AND c BETWEEN 1900 AND 2100));
$$;
COMMENT ON FUNCTION verificacion.fragmento_verificable(text)
    IS 'Filtro previo de enlaces: cifra + palabra de los 8 indicadores, y al menos una cifra que no sea un año';

CREATE OR REPLACE PROCEDURE verificacion.registrar_enlace(
    p_usuario uuid, p_url text, p_metadatos jsonb, p_fecha_referencia date, p_huella text, p_candidatos text[],
    INOUT p_enlace_id uuid, INOUT p_reutilizado boolean)
LANGUAGE plpgsql AS $$
DECLARE
    v_dominio text := lower(substring(p_url FROM '^https?://([^/:?#]+)'));
    v_recientes int;
    v_fragmentos text[];
    i int;
BEGIN
    -- Serializa las peticiones de una misma persona: el límite no se salta con pedidos simultáneos.
    PERFORM pg_advisory_xact_lock(hashtext('enlace:' || p_usuario::text));

    -- Mismo contenido (y misma URL, o ambos pegados) en los últimos 30 días: se devuelve ese análisis.
    SELECT id INTO p_enlace_id FROM verificacion.enlace
    WHERE huella = p_huella AND url IS NOT DISTINCT FROM p_url AND creado_en > now() - interval '30 days'
    ORDER BY creado_en LIMIT 1;
    IF p_enlace_id IS NOT NULL THEN
        p_reutilizado := true;
        RETURN;
    END IF;
    p_reutilizado := false;

    SELECT count(*) INTO v_recientes FROM verificacion.enlace
    WHERE solicitado_por = p_usuario AND creado_en > now() - interval '1 hour';
    IF v_recientes >= 10 THEN
        RAISE EXCEPTION 'limite_enlaces: máximo 10 análisis por hora' USING ERRCODE = 'P0001';
    END IF;

    -- Filtro previo de enlaces en la base (0026), sin duplicados y en el orden del texto; como máximo 20 fragmentos.
    SELECT array_agg(f ORDER BY n) INTO v_fragmentos FROM (
        SELECT f, min(n) AS n FROM unnest(coalesce(p_candidatos, '{}')) WITH ORDINALITY AS c(f, n)
        WHERE length(trim(f)) BETWEEN 5 AND 600 AND verificacion.fragmento_verificable(f)
        GROUP BY f ORDER BY min(n) LIMIT 20) AS x;

    INSERT INTO verificacion.enlace (url, dominio, titulo, sitio, autor_declarado, publicado_declarado,
                                     fecha_referencia, huella, solicitado_por, estado)
    VALUES (p_url, v_dominio, left(p_metadatos->>'titulo', 300), left(p_metadatos->>'sitio', 120),
            left(p_metadatos->>'autor', 200), left(p_metadatos->>'publicado', 40), p_fecha_referencia, p_huella,
            p_usuario, CASE WHEN cardinality(v_fragmentos) > 0 THEN 'con_cifras' ELSE 'sin_cifras' END)
    RETURNING id INTO p_enlace_id;

    FOR i IN 1 .. coalesce(cardinality(v_fragmentos), 0) LOOP
        WITH nuevo AS (
            INSERT INTO verificacion.fragmento_enlace (enlace_id, posicion, texto)
            VALUES (p_enlace_id, i, trim(v_fragmentos[i])) RETURNING id)
        -- Cada fragmento entra a la cola de verificación por el outbox, en la misma transacción.
        INSERT INTO verificacion.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
        SELECT 'fragmento_enlace', id::text, 'fragmento_enlace_creado',
               jsonb_build_object('id', id, 'enlace', p_enlace_id, 'creado_en', p_fecha_referencia)
        FROM nuevo;
    END LOOP;
END;
$$;
COMMENT ON PROCEDURE verificacion.registrar_enlace(uuid, text, jsonb, date, text, text[], uuid, boolean)
    IS 'Decisión 29: guarda metadatos declarados y fragmentos verificables (nunca el cuerpo); límite de 10 por hora; reutiliza análisis idénticos';
GRANT EXECUTE ON FUNCTION verificacion.fragmento_verificable(text) TO svc_verificacion;
