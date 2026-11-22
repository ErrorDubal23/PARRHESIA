-- 0033 · Qué versión de un prompt se publica lo decide la base.
--
-- Revisando las primeras guías (redactar_guia.v1) con datos reales, el juez aprobó algunas que decían de
-- dónde "proviene" la cifra (era una página de consulta, no el origen), que la llamaban "confiable" o que
-- repetían la frase citada como si fuera un hecho en un caso "se invierte". La versión v2 del prompt y del
-- juez lo corrige. Esta tabla fija la versión vigente: guia_de solo publica guías de esa versión, así una
-- versión retirada deja de mostrarse al instante, sin borrar nada (guia_redactada es de solo inserción).
CREATE TABLE verificacion.prompt_vigente (
    tipo     text NOT NULL,
    version  text NOT NULL,
    desde    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT prompt_vigente_pkey PRIMARY KEY (tipo),
    CONSTRAINT prompt_vigente_version_valida CHECK (version ~ ('^' || tipo || '\.v[0-9]+$'))
);
COMMENT ON TABLE verificacion.prompt_vigente IS 'Versión de cada prompt cuya salida se publica';
INSERT INTO verificacion.prompt_vigente (tipo, version) VALUES
    ('redactar_guia', 'redactar_guia.v2'), ('juzgar_neutralidad', 'juzgar_neutralidad.v2');

CREATE OR REPLACE FUNCTION verificacion.guia_de(p_afirmacion_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    WITH a AS (SELECT * FROM verificacion.afirmacion WHERE id = p_afirmacion_id),
    v AS (SELECT * FROM verificacion.verificacion WHERE afirmacion_id = p_afirmacion_id ORDER BY version DESC LIMIT 1),
    claves AS (
        SELECT 'estado' AS origen, 'en_revision' AS referencia, 0 AS orden FROM a WHERE a.estado = 'requiere_revision'
        UNION ALL SELECT 'motivo', v.motivo_sin_dato, 1 FROM v WHERE v.motivo_sin_dato IS NOT NULL
        UNION ALL SELECT 'conclusion', v.conclusion, 2 FROM v WHERE v.conclusion IN ('se_invierte', 'se_sostiene')
        UNION ALL SELECT 'prueba', r.codigo_prueba, 3 FROM v
                  JOIN verificacion.resultado_prueba r ON r.verificacion_id = v.id WHERE r.resultado = 'con_brecha'
        UNION ALL SELECT 'general', 'antes_de_compartir', 9)
    SELECT jsonb_build_object(
        'motivo', (SELECT m.descripcion FROM v JOIN verificacion.motivo_sin_dato m ON m.codigo = v.motivo_sin_dato),
        'consejos', coalesce((
            SELECT jsonb_agg(jsonb_build_object('origen', c.origen, 'codigo', c.referencia,
                                                'para_entenderlo', c.para_entenderlo, 'pasos', to_jsonb(c.pasos))
                             ORDER BY k.orden, c.referencia)
            FROM claves k JOIN verificacion.consejo c ON c.origen = k.origen AND c.referencia = k.referencia), '[]'),
        'fuentes', coalesce((
            SELECT jsonb_agg(jsonb_build_object('nombre', f.nombre, 'url', f.url, 'como_leer', f.como_leer) ORDER BY f.orden)
            FROM a JOIN oficial.consulta_fuente f ON f.codigo_indicador = a.codigo_indicador), '[]'),
        'redaccion', (SELECT g.texto FROM verificacion.guia_redactada g
                      JOIN verificacion.prompt_vigente p ON p.tipo = 'redactar_guia' AND p.version = g.version_prompt
                      WHERE g.afirmacion_id = p_afirmacion_id AND g.neutral ORDER BY g.creada_en DESC LIMIT 1),
        'otros_medios', coalesce((
            SELECT jsonb_agg(jsonb_build_object('medio', e.medio, 'titulo', e.titulo, 'url', e.url,
                                                'publicada_en', e.publicada_en) ORDER BY e.posicion)
            FROM verificacion.verificacion_externa e WHERE e.afirmacion_id = p_afirmacion_id), '[]'));
$$;
GRANT SELECT ON verificacion.prompt_vigente TO svc_verificacion;
