-- 0028 · Imagen de cada tema del día (Unsplash), buscada una sola vez y guardada con su crédito.
--
-- La imagen acompaña; no informa: no se usa para decir nada del tema y siempre lleva el nombre del
-- fotógrafo (lo exigen las condiciones de Unsplash). Se guarda la DIRECCIÓN de la imagen (Unsplash pide
-- enlazarla, no copiarla) y una fila sin imagen cuando la búsqueda no encuentra nada, para no repetirla.
-- Un tema nuevo con la misma etiqueta que uno anterior reutiliza su imagen sin buscar otra vez.

CREATE TABLE temas.imagen_tema (
    tema_id      uuid        NOT NULL,
    consulta     text        NOT NULL,          -- lo que se buscó (palabras del título)
    proveedor_id text,                          -- id de la foto en Unsplash
    url          text,                          -- NULL = no se encontró una imagen adecuada
    autor        text,
    url_autor    text,
    url_foto     text,
    color        text,                          -- color dominante: fondo mientras carga
    buscada_en   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT imagen_tema_pkey PRIMARY KEY (tema_id),
    CONSTRAINT imagen_tema_tema_id_fkey FOREIGN KEY (tema_id) REFERENCES temas.tema (id),
    CONSTRAINT imagen_tema_url_unsplash CHECK (url ~ '^https://images\.unsplash\.com/'),
    CONSTRAINT imagen_tema_credito CHECK ((url IS NULL) = (autor IS NULL) AND (url IS NULL) = (url_foto IS NULL)),
    CONSTRAINT imagen_tema_enlaces CHECK (url_autor ~ '^https://unsplash\.com/' AND url_foto ~ '^https://unsplash\.com/'),
    CONSTRAINT imagen_tema_color CHECK (color ~ '^#[0-9a-fA-F]{6}$')
);
COMMENT ON TABLE temas.imagen_tema IS 'Imagen de Unsplash de un tema del día, con su crédito; fila sin url si no se encontró. Solo inserción';
CREATE TRIGGER imagen_tema_solo_insercion BEFORE UPDATE OR DELETE ON temas.imagen_tema
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- Temas actuales que todavía no tienen búsqueda, con la imagen de un tema anterior de la misma etiqueta.
CREATE FUNCTION temas.temas_sin_imagen()
RETURNS TABLE (tema_id uuid, titulo text, etiqueta text, reutilizable jsonb)
LANGUAGE sql STABLE AS $$
    SELECT t.tema_id, t.titulo, t.etiqueta,
           (SELECT to_jsonb(i) - 'tema_id' - 'buscada_en' FROM temas.imagen_tema i JOIN temas.tema o ON o.id = i.tema_id
            WHERE o.etiqueta = t.etiqueta AND i.url IS NOT NULL ORDER BY i.buscada_en DESC LIMIT 1)
    FROM temas.temas_actuales() t
    WHERE NOT EXISTS (SELECT 1 FROM temas.imagen_tema i WHERE i.tema_id = t.tema_id);
$$;

CREATE PROCEDURE temas.registrar_imagen_tema(p_tema_id uuid, p_datos jsonb)
LANGUAGE sql AS $$
    INSERT INTO temas.imagen_tema (tema_id, consulta, proveedor_id, url, autor, url_autor, url_foto, color)
    VALUES (p_tema_id, p_datos->>'consulta', p_datos->>'proveedor_id', p_datos->>'url', p_datos->>'autor',
            p_datos->>'url_autor', p_datos->>'url_foto', p_datos->>'color')
    ON CONFLICT (tema_id) DO NOTHING;
$$;
COMMENT ON PROCEDURE temas.registrar_imagen_tema(uuid, jsonb) IS 'Guarda la imagen (o la búsqueda sin resultado) de un tema; idempotente';

GRANT SELECT, INSERT ON temas.imagen_tema TO svc_temas;
GRANT EXECUTE ON FUNCTION temas.temas_sin_imagen() TO svc_temas;
GRANT EXECUTE ON PROCEDURE temas.registrar_imagen_tema(uuid, jsonb) TO svc_temas;
