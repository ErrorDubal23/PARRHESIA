-- 0030 · Las búsquedas de imagen se versionan, como los prompts.
--
-- La primera versión (0028) buscaba con palabras del título y falló con datos reales (22 nov 2026):
-- "Escándalo Verónica Estrada" trajo una flor llamada verónica y "Capturas del Clan del Golfo", unas
-- cataratas. Con nombres propios, además, podría traer la foto de una persona real cualquiera. La versión
-- "categoria-1" nunca busca con nombres: unas reglas fijas convierten el tema en una búsqueda genérica
-- (una ciudad, el edificio del Congreso, nubes de tormenta). La tabla sigue siendo de solo inserción: una
-- versión nueva vuelve a buscar sin borrar lo anterior, y la app muestra la última versión.

ALTER TABLE temas.imagen_tema ADD COLUMN version text NOT NULL DEFAULT 'titulo-1';
ALTER TABLE temas.imagen_tema ALTER COLUMN version DROP DEFAULT;
ALTER TABLE temas.imagen_tema DROP CONSTRAINT imagen_tema_pkey,
    ADD CONSTRAINT imagen_tema_pkey PRIMARY KEY (tema_id, version),
    ADD CONSTRAINT imagen_tema_version_valida CHECK (version ~ '^[a-z]+-[0-9]+$');

DROP FUNCTION temas.temas_sin_imagen();
CREATE FUNCTION temas.temas_sin_imagen(p_version text)
RETURNS TABLE (tema_id uuid, titulo text, etiqueta text, reutilizable jsonb)
LANGUAGE sql STABLE AS $$
    SELECT t.tema_id, t.titulo, t.etiqueta,
           (SELECT to_jsonb(i) - 'tema_id' - 'buscada_en' - 'version' FROM temas.imagen_tema i
            JOIN temas.tema o ON o.id = i.tema_id
            WHERE o.etiqueta = t.etiqueta AND i.version = p_version AND i.url IS NOT NULL
            ORDER BY i.buscada_en DESC LIMIT 1)
    FROM temas.temas_actuales() t
    WHERE NOT EXISTS (SELECT 1 FROM temas.imagen_tema i WHERE i.tema_id = t.tema_id AND i.version = p_version);
$$;

DROP PROCEDURE temas.registrar_imagen_tema(uuid, jsonb);
CREATE PROCEDURE temas.registrar_imagen_tema(p_tema_id uuid, p_version text, p_datos jsonb)
LANGUAGE sql AS $$
    INSERT INTO temas.imagen_tema (tema_id, version, consulta, proveedor_id, url, autor, url_autor, url_foto, color)
    VALUES (p_tema_id, p_version, p_datos->>'consulta', p_datos->>'proveedor_id', p_datos->>'url', p_datos->>'autor',
            p_datos->>'url_autor', p_datos->>'url_foto', p_datos->>'color')
    ON CONFLICT (tema_id, version) DO NOTHING;
$$;
COMMENT ON PROCEDURE temas.registrar_imagen_tema(uuid, text, jsonb)
    IS 'Guarda la imagen (o la búsqueda sin resultado) de un tema para una versión de la búsqueda; idempotente';

-- La imagen vigente de un tema: la de la búsqueda más reciente.
CREATE FUNCTION temas.imagen_vigente(p_tema_id uuid)
RETURNS TABLE (url text, autor text, url_autor text, url_foto text, color text)
LANGUAGE sql STABLE AS $$
    SELECT url, autor, url_autor, url_foto, color FROM temas.imagen_tema
    WHERE tema_id = p_tema_id ORDER BY buscada_en DESC LIMIT 1;
$$;

GRANT EXECUTE ON FUNCTION temas.temas_sin_imagen(text), temas.imagen_vigente(uuid) TO svc_temas;
GRANT EXECUTE ON PROCEDURE temas.registrar_imagen_tema(uuid, text, jsonb) TO svc_temas;
