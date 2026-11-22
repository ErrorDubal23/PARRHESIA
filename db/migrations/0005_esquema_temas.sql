-- 0005: esquema temas. Temas del día: de qué hablan los medios y qué cifras se dijeron.
--
-- Diseño: docs/diseno/06_temas_del_dia.md (decisiones 17, 18 y 19).
-- La IA agrupa artículos en temas y extrae citas con cifras, pero la base es la que
-- cuenta los medios, ordena los temas y revisa que cada cita esté textual en el
-- artículo: la IA no puede inflar un tema ni atribuir una frase que no está en la fuente.

CREATE SCHEMA temas;
COMMENT ON SCHEMA temas IS 'Temas del día: medios, artículos, temas y declaraciones reportadas por los medios';

-- =============================================================================
-- PARTE 1 · Función compartida: cifras de un texto
-- =============================================================================

-- Las cifras de un texto en formato colombiano, en orden y sin repetir:
-- "1.234.567,5" -> 1234567.5 ; "9,28 %" -> 9.28 ; "2026" -> 2026.
-- El punto es separador de miles solo si separa grupos de tres dígitos.
CREATE FUNCTION util.cifras_en_texto(p_texto text) RETURNS numeric[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(array_agg(valor ORDER BY posicion), '{}')
    FROM (
        SELECT valor, min(posicion) AS posicion
        FROM (
            SELECT replace(replace(m[1], '.', ''), ',', '.')::numeric AS valor, n AS posicion
            FROM regexp_matches(coalesce(p_texto, ''), '(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)', 'g')
                 WITH ORDINALITY AS r(m, n)
        ) AS todas
        GROUP BY valor
    ) AS distintas;
$$;
COMMENT ON FUNCTION util.cifras_en_texto(text) IS 'Cifras de un texto en formato colombiano (1.234,5), en orden de aparición y sin repetir';

-- =============================================================================
-- PARTE 2 · Tablas
-- =============================================================================

-- MEDIO: fuente de noticias registrada (lista pública, de distintas líneas editoriales).
CREATE TABLE temas.medio (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    nombre          text        NOT NULL,
    url_sitio       text        NOT NULL,
    canal           text        NOT NULL,
    url_canal       text        NOT NULL,
    habilitado      boolean     NOT NULL DEFAULT true,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT medio_pkey PRIMARY KEY (id),
    CONSTRAINT medio_nombre_key UNIQUE (nombre),
    CONSTRAINT medio_canal_valido CHECK (canal IN ('rss', 'gdelt')),
    CONSTRAINT medio_urls_validas CHECK (url_sitio ~ '^https?://' AND url_canal ~ '^https?://')
);
COMMENT ON TABLE temas.medio IS 'Medios de noticias registrados, con su canal (RSS o GDELT)';

-- ARTICULO: lo que publicó un medio. El texto solo se guarda si el medio lo permite.
CREATE TABLE temas.articulo (
    id            uuid        NOT NULL DEFAULT gen_random_uuid(),
    medio_id      uuid        NOT NULL,
    url           text        NOT NULL,
    titulo        text        NOT NULL,
    resumen       text,
    texto         text,
    publicado_en  timestamptz NOT NULL,
    huella        text        NOT NULL,      -- sha256 de título, resumen y texto; la calcula un trigger
    creado_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT articulo_pkey PRIMARY KEY (id),
    CONSTRAINT articulo_url_key UNIQUE (url),
    CONSTRAINT articulo_medio_id_fkey FOREIGN KEY (medio_id) REFERENCES temas.medio (id),
    CONSTRAINT articulo_url_valida CHECK (url ~ '^https?://'),
    CONSTRAINT articulo_titulo_valido CHECK (length(trim(titulo)) >= 1)
);
CREATE INDEX articulo_publicado_idx ON temas.articulo (publicado_en);
CREATE INDEX articulo_medio_idx ON temas.articulo (medio_id);
COMMENT ON TABLE temas.articulo IS 'Artículo de un medio. Solo inserción';

-- TEMA: un grupo de artículos de una ventana de tiempo. Título y orden: ver triggers.
CREATE TABLE temas.tema (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    ventana_inicio   timestamptz NOT NULL,
    ventana_fin      timestamptz NOT NULL,
    titulo           text        NOT NULL,
    etiqueta         text        NOT NULL,
    total_articulos  integer     NOT NULL,
    total_medios     integer     NOT NULL,
    posicion         smallint    NOT NULL,
    trabajo_ia_id    uuid,                   -- lógica -> ia.trabajo (la agrupación)
    creado_en        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tema_pkey PRIMARY KEY (id),
    CONSTRAINT tema_ventana_posicion_key UNIQUE (ventana_inicio, ventana_fin, posicion),
    CONSTRAINT tema_ventana_valida CHECK (ventana_fin > ventana_inicio),
    -- Un título o una etiqueta con números podría colar un dato (decisión 19).
    CONSTRAINT tema_titulo_sin_cifras CHECK (titulo !~ '[0-9]' AND length(trim(titulo)) BETWEEN 3 AND 120),
    CONSTRAINT tema_etiqueta_valida CHECK (etiqueta ~ '^[a-z_áéíóúñü]{2,50}$'),
    CONSTRAINT tema_minimo_tres_medios CHECK (total_medios >= 3),
    CONSTRAINT tema_totales_coherentes CHECK (total_articulos >= total_medios),
    CONSTRAINT tema_posicion_valida CHECK (posicion BETWEEN 1 AND 7)
);
CREATE INDEX tema_ventana_idx ON temas.tema (ventana_fin DESC, posicion);
COMMENT ON TABLE temas.tema IS 'Tema del día de una ventana. Lo agrupa la IA; los conteos y el orden los pone la base. Solo inserción';

CREATE TABLE temas.tema_articulo (
    tema_id      uuid NOT NULL,
    articulo_id  uuid NOT NULL,
    CONSTRAINT tema_articulo_pkey PRIMARY KEY (tema_id, articulo_id),
    CONSTRAINT tema_articulo_tema_id_fkey FOREIGN KEY (tema_id) REFERENCES temas.tema (id),
    CONSTRAINT tema_articulo_articulo_id_fkey FOREIGN KEY (articulo_id) REFERENCES temas.articulo (id)
);
CREATE INDEX tema_articulo_articulo_idx ON temas.tema_articulo (articulo_id);

-- DECLARACION_REPORTADA: lo que un artículo dice que alguien dijo, con cifras.
CREATE TABLE temas.declaracion_reportada (
    id             uuid        NOT NULL DEFAULT gen_random_uuid(),
    articulo_id    uuid        NOT NULL,
    actor          text        NOT NULL,         -- como lo nombra el artículo
    figura_id      uuid,                         -- lógica -> social.figura_publica, si coincide exactamente
    texto_citado   text        NOT NULL,         -- textual en el artículo (trigger)
    trabajo_ia_id  uuid,                         -- lógica -> ia.trabajo (la extracción)
    creado_en      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT declaracion_reportada_pkey PRIMARY KEY (id),
    CONSTRAINT declaracion_reportada_cita_key UNIQUE (articulo_id, texto_citado),
    CONSTRAINT declaracion_reportada_articulo_id_fkey FOREIGN KEY (articulo_id) REFERENCES temas.articulo (id),
    CONSTRAINT declaracion_reportada_actor_valido CHECK (length(trim(actor)) BETWEEN 2 AND 120),
    CONSTRAINT declaracion_reportada_cita_valida CHECK (length(trim(texto_citado)) BETWEEN 5 AND 1000),
    -- Solo interesan las declaraciones con cifras (filtro previo, decisión 20).
    CONSTRAINT declaracion_reportada_con_cifras CHECK (cardinality(util.cifras_en_texto(texto_citado)) > 0)
);
CREATE INDEX declaracion_reportada_figura_idx ON temas.declaracion_reportada (figura_id);
COMMENT ON TABLE temas.declaracion_reportada IS 'Declaración con cifras como la reporta un medio, con la cita exacta. Solo inserción';

-- Outbox del esquema temas (decisiones 10 y 18)
CREATE TABLE temas.evento_salida (
    id            bigint      GENERATED ALWAYS AS IDENTITY,
    tipo_entidad  text        NOT NULL,
    entidad_id    text        NOT NULL,
    tipo_evento   text        NOT NULL,
    datos         jsonb       NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT evento_salida_pkey PRIMARY KEY (id)
);
CREATE INDEX evento_salida_tipo_idx ON temas.evento_salida (tipo_evento, id);

CREATE TABLE temas.entrega_evento (
    evento_id     bigint      NOT NULL,
    consumidor    text        NOT NULL,
    entregado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT entrega_evento_pkey PRIMARY KEY (evento_id, consumidor),
    CONSTRAINT entrega_evento_evento_id_fkey FOREIGN KEY (evento_id) REFERENCES temas.evento_salida (id),
    CONSTRAINT entrega_evento_consumidor_valido CHECK (consumidor IN ('grafo', 'verificacion'))
);

-- =============================================================================
-- PARTE 3 · Triggers
-- =============================================================================

CREATE FUNCTION temas.calcular_huella() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.huella := encode(sha256(convert_to(
        concat_ws(E'\n', NEW.titulo, NEW.resumen, NEW.texto), 'UTF8')), 'hex');
    RETURN NEW;
END;
$$;
CREATE TRIGGER articulo_huella BEFORE INSERT ON temas.articulo
    FOR EACH ROW EXECUTE FUNCTION temas.calcular_huella();

-- La cita debe aparecer tal cual en el título, el resumen o el texto guardado del
-- artículo (decisión 19). Si la IA la reescribe o la inventa, la base la rechaza.
CREATE FUNCTION temas.validar_declaracion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    a temas.articulo;
BEGIN
    SELECT * INTO a FROM temas.articulo WHERE id = NEW.articulo_id;
    IF position(NEW.texto_citado IN a.titulo) = 0
       AND position(NEW.texto_citado IN coalesce(a.resumen, '')) = 0
       AND position(NEW.texto_citado IN coalesce(a.texto, '')) = 0 THEN
        RAISE EXCEPTION 'cita_no_textual: la cita no aparece tal cual en el artículo %', NEW.articulo_id;
    END IF;
    IF NEW.figura_id IS NOT NULL AND NOT social.figura_existe(NEW.figura_id) THEN
        RAISE EXCEPTION 'figura_inexistente: la figura % no existe', NEW.figura_id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER declaracion_reportada_validar BEFORE INSERT ON temas.declaracion_reportada
    FOR EACH ROW EXECUTE FUNCTION temas.validar_declaracion();

-- Cada declaración nueva va al servicio de verificación por el outbox.
CREATE FUNCTION temas.emitir_declaracion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO temas.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
    VALUES ('declaracion_reportada', NEW.id::text, 'declaracion_reportada_creada',
            jsonb_build_object('id', NEW.id, 'articulo', NEW.articulo_id, 'actor', NEW.actor, 'figura', NEW.figura_id));
    RETURN NULL;
END;
$$;
CREATE TRIGGER declaracion_reportada_salida AFTER INSERT ON temas.declaracion_reportada
    FOR EACH ROW EXECUTE FUNCTION temas.emitir_declaracion();

CREATE FUNCTION temas.avisar_evento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('evento_salida', 'temas');
    RETURN NULL;
END;
$$;
CREATE TRIGGER evento_salida_aviso AFTER INSERT ON temas.evento_salida
    FOR EACH STATEMENT EXECUTE FUNCTION temas.avisar_evento();

CREATE TRIGGER medio_actualizado BEFORE UPDATE ON temas.medio
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER articulo_solo_insercion BEFORE UPDATE OR DELETE ON temas.articulo
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER tema_solo_insercion BEFORE UPDATE OR DELETE ON temas.tema
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER tema_articulo_solo_insercion BEFORE UPDATE OR DELETE ON temas.tema_articulo
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER declaracion_reportada_solo_insercion BEFORE UPDATE OR DELETE ON temas.declaracion_reportada
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER evento_salida_solo_insercion BEFORE UPDATE OR DELETE ON temas.evento_salida
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER entrega_evento_solo_insercion BEFORE UPDATE OR DELETE ON temas.entrega_evento
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- =============================================================================
-- PARTE 4 · Funciones
-- =============================================================================

-- La entrada del trabajo de agrupación: los artículos de la ventana.
CREATE FUNCTION temas.articulos_ventana(p_desde timestamptz, p_hasta timestamptz)
RETURNS TABLE (articulo_id uuid, medio text, titulo text, resumen text, publicado_en timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT a.id, m.nombre, a.titulo, a.resumen, a.publicado_en
    FROM temas.articulo a JOIN temas.medio m ON m.id = a.medio_id
    WHERE a.publicado_en >= p_desde AND a.publicado_en < p_hasta
    ORDER BY a.publicado_en;
$$;
COMMENT ON FUNCTION temas.articulos_ventana(timestamptz, timestamptz) IS 'Artículos de una ventana: la entrada de la agrupación en temas';

-- La figura registrada cuyo nombre coincide con el actor, sin distinguir
-- mayúsculas ni tildes. Solo si hay una coincidencia exacta: no adivina.
CREATE FUNCTION temas.buscar_figura(p_actor text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT CASE WHEN count(*) = 1 THEN min(f.id::text)::uuid END
    FROM social.figura_publica f
    WHERE translate(lower(f.nombre_completo), 'áéíóúüñ', 'aeiouun')
        = translate(lower(trim(p_actor)), 'áéíóúüñ', 'aeiouun');
$$;
COMMENT ON FUNCTION temas.buscar_figura(text) IS 'Liga un actor a una figura registrada solo si el nombre coincide exactamente';

-- Los temas de la ventana más reciente, en orden.
CREATE FUNCTION temas.temas_actuales()
RETURNS TABLE (tema_id uuid, posicion smallint, titulo text, etiqueta text, total_medios integer,
               total_articulos integer, ventana_inicio timestamptz, ventana_fin timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT t.id, t.posicion, t.titulo, t.etiqueta, t.total_medios, t.total_articulos, t.ventana_inicio, t.ventana_fin
    FROM temas.tema t
    WHERE (t.ventana_inicio, t.ventana_fin) = (
        SELECT ventana_inicio, ventana_fin FROM temas.tema ORDER BY ventana_fin DESC, ventana_inicio DESC LIMIT 1)
    ORDER BY t.posicion;
$$;
COMMENT ON FUNCTION temas.temas_actuales() IS 'Los temas del día de la última ventana calculada';

-- Lo que muestra la página de un tema: sus artículos y las declaraciones que reportan.
-- Las conclusiones de cada declaración las agrega el servicio de verificación.
CREATE FUNCTION temas.pagina_tema(p_tema_id uuid)
RETURNS TABLE (tipo text, id uuid, medio text, titulo text, url text, publicado_en timestamptz,
               actor text, figura_id uuid, texto_citado text)
LANGUAGE sql STABLE AS $$
    SELECT 'articulo', a.id, m.nombre, a.titulo, a.url, a.publicado_en, NULL, NULL::uuid, NULL
    FROM temas.tema_articulo ta
    JOIN temas.articulo a ON a.id = ta.articulo_id
    JOIN temas.medio m ON m.id = a.medio_id
    WHERE ta.tema_id = p_tema_id
    UNION ALL
    SELECT 'declaracion', d.id, m.nombre, a.titulo, a.url, a.publicado_en, d.actor, d.figura_id, d.texto_citado
    FROM temas.tema_articulo ta
    JOIN temas.declaracion_reportada d ON d.articulo_id = ta.articulo_id
    JOIN temas.articulo a ON a.id = d.articulo_id
    JOIN temas.medio m ON m.id = a.medio_id
    WHERE ta.tema_id = p_tema_id
    ORDER BY 1, 6 DESC;
$$;
COMMENT ON FUNCTION temas.pagina_tema(uuid) IS 'Artículos y declaraciones reportadas de un tema';

-- Para el servicio de verificación: la cita que debe revisar.
CREATE FUNCTION temas.texto_para_verificar(p_declaracion_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT texto_citado FROM temas.declaracion_reportada WHERE id = p_declaracion_id;
$$;
CREATE FUNCTION temas.declaracion_existe(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM temas.declaracion_reportada WHERE id = p_id);
$$;

CREATE FUNCTION temas.eventos_pendientes(p_consumidor text, p_tipos text[], p_limite int DEFAULT 100)
RETURNS SETOF temas.evento_salida
LANGUAGE sql STABLE AS $$
    SELECT e.* FROM temas.evento_salida e
    WHERE e.tipo_evento = ANY (p_tipos)
      AND NOT EXISTS (SELECT 1 FROM temas.entrega_evento d WHERE d.evento_id = e.id AND d.consumidor = p_consumidor)
    ORDER BY e.id
    LIMIT p_limite;
$$;

-- =============================================================================
-- PARTE 5 · Procedimientos
-- =============================================================================

CREATE PROCEDURE temas.configurar_medio(p_nombre text, p_url_sitio text, p_canal text, p_url_canal text,
                                        p_habilitado boolean)
LANGUAGE sql AS $$
    INSERT INTO temas.medio (nombre, url_sitio, canal, url_canal, habilitado)
    VALUES (p_nombre, p_url_sitio, p_canal, p_url_canal, p_habilitado)
    ON CONFLICT (nombre) DO UPDATE SET url_sitio = EXCLUDED.url_sitio, canal = EXCLUDED.canal,
                                       url_canal = EXCLUDED.url_canal, habilitado = EXCLUDED.habilitado;
$$;

-- Guarda los artículos leídos de un medio; los repetidos (misma URL) se ignoran.
-- articulos: [{"url": "...", "titulo": "...", "resumen": "...", "texto": null, "publicado_en": "..."}]
CREATE PROCEDURE temas.registrar_articulos(p_medio_id uuid, p_articulos jsonb, INOUT p_nuevos int)
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM temas.medio WHERE id = p_medio_id AND habilitado;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'medio_no_habilitado: el medio % no existe o no está habilitado', p_medio_id;
    END IF;
    INSERT INTO temas.articulo (medio_id, url, titulo, resumen, texto, publicado_en)
    SELECT p_medio_id, a->>'url', a->>'titulo', a->>'resumen', a->>'texto', (a->>'publicado_en')::timestamptz
    FROM jsonb_array_elements(p_articulos) AS a
    ON CONFLICT (url) DO NOTHING;
    GET DIAGNOSTICS p_nuevos = ROW_COUNT;
END;
$$;
COMMENT ON PROCEDURE temas.registrar_articulos(uuid, jsonb, int) IS 'Guarda los artículos nuevos de un medio, todos en una transacción';

-- Recibe los grupos que propuso la IA y decide la base: revisa los artículos,
-- cuenta los medios distintos, descarta los grupos de menos de 3 medios, ordena y
-- guarda los 7 primeros. Todo o nada.
-- grupos: [{"titulo": "...", "etiqueta": "...", "articulos": ["<uuid>", ...]}, ...]
CREATE PROCEDURE temas.registrar_temas(p_ventana_inicio timestamptz, p_ventana_fin timestamptz,
                                       p_trabajo_ia_id uuid, p_grupos jsonb, INOUT p_guardados int)
LANGUAGE plpgsql AS $$
DECLARE
    v_grupo  record;
    v_tema   uuid;
BEGIN
    CREATE TEMP TABLE grupo_articulo ON COMMIT DROP AS
    SELECT g.n AS grupo, g.valor->>'titulo' AS titulo, lower(g.valor->>'etiqueta') AS etiqueta,
           (art.id)::uuid AS articulo_id
    FROM jsonb_array_elements(p_grupos) WITH ORDINALITY AS g(valor, n)
    CROSS JOIN LATERAL jsonb_array_elements_text(g.valor->'articulos') AS art(id);

    -- Cada artículo debe existir, estar en la ventana y pertenecer a un solo grupo.
    IF EXISTS (SELECT 1 FROM grupo_articulo ga LEFT JOIN temas.articulo a ON a.id = ga.articulo_id
               WHERE a.id IS NULL OR a.publicado_en < p_ventana_inicio OR a.publicado_en >= p_ventana_fin) THEN
        RAISE EXCEPTION 'articulo_fuera_de_ventana: un grupo incluye un artículo que no existe o no es de la ventana';
    END IF;
    IF EXISTS (SELECT articulo_id FROM grupo_articulo GROUP BY articulo_id HAVING count(DISTINCT grupo) > 1) THEN
        RAISE EXCEPTION 'articulo_repetido: un artículo aparece en más de un grupo';
    END IF;

    p_guardados := 0;
    FOR v_grupo IN
        SELECT ga.grupo, min(ga.titulo) AS titulo, min(ga.etiqueta) AS etiqueta,
               count(DISTINCT ga.articulo_id) AS total_articulos, count(DISTINCT a.medio_id) AS total_medios
        FROM grupo_articulo ga JOIN temas.articulo a ON a.id = ga.articulo_id
        GROUP BY ga.grupo
        HAVING count(DISTINCT a.medio_id) >= 3
        ORDER BY count(DISTINCT a.medio_id) DESC, count(DISTINCT ga.articulo_id) DESC, min(ga.titulo)
        LIMIT 7
    LOOP
        p_guardados := p_guardados + 1;
        INSERT INTO temas.tema (ventana_inicio, ventana_fin, titulo, etiqueta, total_articulos, total_medios,
                                posicion, trabajo_ia_id)
        VALUES (p_ventana_inicio, p_ventana_fin, v_grupo.titulo, v_grupo.etiqueta, v_grupo.total_articulos,
                v_grupo.total_medios, p_guardados, p_trabajo_ia_id)
        RETURNING id INTO v_tema;
        INSERT INTO temas.tema_articulo (tema_id, articulo_id)
        SELECT DISTINCT v_tema, articulo_id FROM grupo_articulo WHERE grupo = v_grupo.grupo;
    END LOOP;
    DROP TABLE grupo_articulo;
END;
$$;
COMMENT ON PROCEDURE temas.registrar_temas(timestamptz, timestamptz, uuid, jsonb, int)
    IS 'Guarda los temas de una ventana: la base cuenta medios, descarta y ordena; todo o nada';

-- Guarda las declaraciones que extrajo la IA de un artículo. Si una cita no es
-- textual, el trigger la rechaza y no queda ninguna del lote.
-- declaraciones: [{"actor": "...", "texto_citado": "..."}]
CREATE PROCEDURE temas.registrar_declaraciones(p_articulo_id uuid, p_trabajo_ia_id uuid, p_declaraciones jsonb,
                                               INOUT p_guardadas int)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO temas.declaracion_reportada (articulo_id, actor, figura_id, texto_citado, trabajo_ia_id)
    SELECT p_articulo_id, d->>'actor', temas.buscar_figura(d->>'actor'), d->>'texto_citado', p_trabajo_ia_id
    FROM jsonb_array_elements(p_declaraciones) AS d
    ON CONFLICT (articulo_id, texto_citado) DO NOTHING;
    GET DIAGNOSTICS p_guardadas = ROW_COUNT;
END;
$$;
COMMENT ON PROCEDURE temas.registrar_declaraciones(uuid, uuid, jsonb, int)
    IS 'Guarda las declaraciones con cifras de un artículo; si una cita no es textual, no queda ninguna';

CREATE PROCEDURE temas.marcar_entregados(p_consumidor text, p_eventos bigint[])
LANGUAGE sql AS $$
    INSERT INTO temas.entrega_evento (evento_id, consumidor)
    SELECT unnest(p_eventos), p_consumidor
    ON CONFLICT DO NOTHING;
$$;
