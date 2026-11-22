-- 0025 · Análisis de enlaces externos (decisión 29, T12).
--
-- Una noticia vista en otra red o portal pasa por el mismo motor de verificación. El cuerpo de la página
-- se procesa en memoria y NO se guarda (derechos de autor): solo se guardan los metadatos que la página
-- declara y los FRAGMENTOS CORTOS que pasan el filtro previo (cifra + palabra de los 8 indicadores). Cada
-- fragmento es un origen más de la verificación: dos lecturas, consenso por afirmación, motor, validador y
-- revisión humana, sin cambios. Como la IA solo recibe fragmentos, el texto completo tampoco queda en
-- ia.trabajo.entrada.

-- ENLACE: lo que se pidió analizar. url NULL = la persona pegó el texto (redes que bloquean el acceso).
CREATE TABLE verificacion.enlace (
    id                   uuid        NOT NULL DEFAULT gen_random_uuid(),
    url                  text,
    dominio              text,
    titulo               text,        -- como lo declara la página (og:title o <title>); no se interpreta
    sitio                text,        -- og:site_name
    autor_declarado      text,        -- meta author / article:author
    publicado_declarado  text,        -- article:published_time tal como viene
    fecha_referencia     date        NOT NULL,   -- para "este año" / "el mes pasado" al leer las cifras
    huella               text        NOT NULL,   -- sha256 del texto procesado: el texto no se guarda
    solicitado_por       uuid        NOT NULL,   -- lógica -> social.usuario
    estado               text        NOT NULL,
    creado_en            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT enlace_pkey PRIMARY KEY (id),
    CONSTRAINT enlace_url_valida CHECK (url ~ '^https?://' AND length(url) <= 2000),
    CONSTRAINT enlace_dominio_con_url CHECK ((url IS NULL) = (dominio IS NULL)),
    CONSTRAINT enlace_metadatos_cortos CHECK (length(titulo) <= 300 AND length(sitio) <= 120
                                              AND length(autor_declarado) <= 200 AND length(publicado_declarado) <= 40),
    CONSTRAINT enlace_huella_valida CHECK (huella ~ '^[0-9a-f]{64}$'),
    CONSTRAINT enlace_estado_valido CHECK (estado IN ('con_cifras', 'sin_cifras'))
);
CREATE INDEX enlace_reuso_idx ON verificacion.enlace (huella, url);
CREATE INDEX enlace_solicitante_idx ON verificacion.enlace (solicitado_por, creado_en);
COMMENT ON TABLE verificacion.enlace IS 'Enlace o texto pegado que alguien pidió analizar: solo metadatos declarados y huella, nunca el cuerpo. Solo inserción';

-- FRAGMENTO_ENLACE: la cita corta con cifras (derecho de cita). Es lo único del texto que se guarda.
CREATE TABLE verificacion.fragmento_enlace (
    id         uuid        NOT NULL DEFAULT gen_random_uuid(),
    enlace_id  uuid        NOT NULL,
    posicion   smallint    NOT NULL,
    texto      text        NOT NULL,
    creado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fragmento_enlace_pkey PRIMARY KEY (id),
    CONSTRAINT fragmento_enlace_enlace_id_fkey FOREIGN KEY (enlace_id) REFERENCES verificacion.enlace (id),
    CONSTRAINT fragmento_enlace_posicion_key UNIQUE (enlace_id, posicion),
    CONSTRAINT fragmento_enlace_posicion_valida CHECK (posicion BETWEEN 1 AND 20),
    CONSTRAINT fragmento_enlace_corto CHECK (length(trim(texto)) BETWEEN 5 AND 600),
    -- Sin cifra no hay nada que verificar ni por qué citarlo. (La palabra de los 8 indicadores la exige el
    -- procedimiento: requiere_extraccion lee una tabla y no puede ir en un CHECK.)
    CONSTRAINT fragmento_enlace_con_cifras CHECK (cardinality(util.cifras_en_texto(texto)) > 0)
);
COMMENT ON TABLE verificacion.fragmento_enlace IS 'Cita corta con cifras de un enlace analizado: el único texto que se guarda. Solo inserción';

CREATE TRIGGER enlace_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.enlace
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER fragmento_enlace_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.fragmento_enlace
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- La afirmación puede salir de un fragmento: cuarto brazo del arco exclusivo, con clave foránea real
-- (mismo esquema; los otros tres orígenes viven en otros esquemas y los revisa un trigger).
ALTER TABLE verificacion.afirmacion ADD COLUMN fragmento_enlace_id uuid;
ALTER TABLE verificacion.afirmacion
    ADD CONSTRAINT afirmacion_fragmento_enlace_id_fkey FOREIGN KEY (fragmento_enlace_id) REFERENCES verificacion.fragmento_enlace (id),
    ADD CONSTRAINT afirmacion_fragmento_posicion_key UNIQUE (fragmento_enlace_id, posicion),
    DROP CONSTRAINT afirmacion_un_solo_origen,
    ADD CONSTRAINT afirmacion_un_solo_origen
        CHECK (num_nonnulls(publicacion_id, declaracion_id, declaracion_reportada_id, fragmento_enlace_id) = 1);
CREATE INDEX afirmacion_fragmento_idx ON verificacion.afirmacion (fragmento_enlace_id) WHERE fragmento_enlace_id IS NOT NULL;

ALTER TABLE verificacion.procesamiento
    DROP CONSTRAINT procesamiento_origen_valido,
    ADD CONSTRAINT procesamiento_origen_valido
        CHECK (origen_tipo IN ('publicacion', 'declaracion', 'declaracion_reportada', 'fragmento_enlace'));

-- Registrar un análisis: todo o nada. La base decide qué fragmentos se guardan (filtro previo), aplica el
-- límite por persona y reutiliza un análisis idéntico reciente sin gastar IA otra vez.
CREATE PROCEDURE verificacion.registrar_enlace(
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

    -- Filtro previo en la base, sin duplicados y en el orden del texto; como máximo 20 fragmentos.
    SELECT array_agg(f ORDER BY n) INTO v_fragmentos FROM (
        SELECT f, min(n) AS n FROM unnest(coalesce(p_candidatos, '{}')) WITH ORDINALITY AS c(f, n)
        WHERE length(trim(f)) BETWEEN 5 AND 600 AND verificacion.requiere_extraccion(f)
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
    IS 'Decisión 29: guarda metadatos declarados y fragmentos con cifras (nunca el cuerpo); límite de 10 por hora; reutiliza análisis idénticos';

CREATE FUNCTION verificacion.texto_fragmento(p_id uuid) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT texto FROM verificacion.fragmento_enlace WHERE id = p_id;
$$;

-- Estado de un análisis completo, con la misma escala que una publicación.
CREATE FUNCTION verificacion.estado_enlace(p_enlace_id uuid) RETURNS text
LANGUAGE sql STABLE AS $$
    WITH f AS (
        SELECT fe.id, p.resultado,
               EXISTS (SELECT 1 FROM verificacion.afirmacion a WHERE a.fragmento_enlace_id = fe.id
                       AND a.estado = 'requiere_revision') AS en_revision,
               EXISTS (SELECT 1 FROM verificacion.afirmacion a WHERE a.fragmento_enlace_id = fe.id
                       AND a.estado = 'extraida') AS por_verificar
        FROM verificacion.fragmento_enlace fe
        LEFT JOIN verificacion.procesamiento p ON p.origen_tipo = 'fragmento_enlace' AND p.origen_id = fe.id
        WHERE fe.enlace_id = p_enlace_id)
    SELECT CASE
        WHEN NOT EXISTS (SELECT 1 FROM f) THEN 'sin_cifras'
        WHEN EXISTS (SELECT 1 FROM f WHERE resultado IS NULL OR por_verificar) THEN 'pendiente'
        WHEN EXISTS (SELECT 1 FROM f WHERE resultado = 'fallido' OR en_revision) THEN 'requiere_revision'
        WHEN NOT EXISTS (SELECT 1 FROM f WHERE resultado = 'con_afirmaciones') THEN 'sin_cifras'
        ELSE 'lista' END;
$$;
COMMENT ON FUNCTION verificacion.estado_enlace(uuid) IS 'pendiente, requiere_revision, sin_cifras o lista, a partir de sus fragmentos';

-- El consenso guarda también afirmaciones de un fragmento (misma lógica que 0023, un origen más).
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
            filas := filas || jsonb_build_array(jsonb_build_object('f', f, 'consenso', 'coinciden', 'origen', 'a'));
            coinciden := coinciden + 1;
        ELSE
            filas := filas || jsonb_build_array(jsonb_build_object('f', f, 'consenso', 'difieren', 'origen', 'a'));
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
            WHERE r->>'consenso' = 'difieren' AND r->>'origen' = 'a'   -- solo contra lo que dejó la lectura A
              AND r->'f'->>'codigo_indicador' IS NOT DISTINCT FROM g->>'codigo_indicador'
              AND (trim_scale((r->'f'->>'valor_dicho')::numeric) = trim_scale((g->>'valor_dicho')::numeric)
                   OR (r->'f'->>'periodo_hasta' IS NOT DISTINCT FROM g->>'periodo_hasta'
                       AND r->'f'->>'variante' IS NOT DISTINCT FROM g->>'variante'
                       AND coalesce(r->'f'->>'comparacion', 'nivel') = coalesce(g->>'comparacion', 'nivel')))) THEN
            filas := filas || jsonb_build_array(jsonb_build_object('f', g, 'consenso', 'difieren', 'origen', 'b'));
        END IF;
    END LOOP;

    p_consenso := CASE WHEN jsonb_array_length(filas) = 0 OR coinciden = jsonb_array_length(filas) THEN 'coinciden'
                       WHEN coinciden = 0 THEN 'difieren' ELSE 'parcial' END;

    INSERT INTO verificacion.afirmacion (
        publicacion_id, declaracion_id, declaracion_reportada_id, fragmento_enlace_id, posicion, texto_citado, codigo_indicador,
        variante, periodo_desde, periodo_hasta, territorio, valor_dicho, unidad_dicha, comparacion, direccion,
        confianza_extraccion, trabajo_ia_id, trabajo_ia_2_id, consenso, estado)
    SELECT CASE WHEN p_origen_tipo = 'publicacion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion_reportada' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'fragmento_enlace' THEN p_origen_id END,
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
    IS 'Decisión 33: consenso por afirmación; lo que coincide sigue al motor, lo demás va a revisión humana. Orígenes: publicación, declaración, declaración reportada y fragmento de enlace';

GRANT SELECT, INSERT ON verificacion.enlace, verificacion.fragmento_enlace TO svc_verificacion;
GRANT EXECUTE ON PROCEDURE verificacion.registrar_enlace(uuid, text, jsonb, date, text, text[], uuid, boolean)
    TO svc_verificacion;
GRANT EXECUTE ON FUNCTION verificacion.texto_fragmento(uuid), verificacion.estado_enlace(uuid) TO svc_verificacion;
