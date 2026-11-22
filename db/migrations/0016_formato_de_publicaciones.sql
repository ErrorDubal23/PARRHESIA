-- 0016 · Formato en las publicaciones: **negrita**, *cursiva* y [texto](https://enlace) (segunda etapa, T8).
--
-- El texto se guarda con estas marcas, nunca como HTML: la app lo dibuja con su propio intérprete
-- (no se puede inyectar código). Todo lo que lee la base o la verificación usa el texto plano:
--   - el límite de 500 caracteres cuenta solo lo visible (las marcas tienen un tope técnico de 1.500);
--   - etiquetas y menciones salen del texto visible (un # dentro de un enlace no crea una etiqueta);
--   - la verificación y la IA leen el texto plano (las cifras de una dirección web no son afirmaciones).
-- Las mismas reglas están en web/src/formato.ts; las pruebas comparan ambos.

-- El texto como se lee, sin marcas. Los enlaces dejan su texto visible; solo se aceptan https.
CREATE FUNCTION util.texto_plano(p_texto text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = '' AS $$
    SELECT regexp_replace(
               regexp_replace(
                   regexp_replace(coalesce(p_texto, ''),
                       '\[([^\]\n]{1,200})\]\((https://[^\s)]+)\)', '\1', 'g'),   -- [texto](https://...)
                   '(^|[^[:alnum:]*])\*\*([^*\s]|[^*\s][^*\n]*[^*\s])\*\*(?![[:alnum:]*])', '\1\2', 'g'),  -- **negrita**
               '(^|[^[:alnum:]*])\*([^*\s]|[^*\s][^*\n]*[^*\s])\*(?![[:alnum:]*])', '\1\2', 'g');          -- *cursiva*
-- Una marca no empieza ni termina con espacio y no va pegada a letras o números por fuera: así
-- "5 * 3" o "2*4*5" quedan intactos (las cifras nunca se juntan por culpa del formato).
$$;
COMMENT ON FUNCTION util.texto_plano(text) IS 'Texto sin las marcas de formato: lo que se cuenta, se busca y se verifica';
GRANT EXECUTE ON FUNCTION util.texto_plano(text) TO svc_social, svc_verificacion, svc_grafo;

-- Límite sobre lo visible y tope técnico para las marcas.
ALTER TABLE social.publicacion DROP CONSTRAINT publicacion_texto_valido;
ALTER TABLE social.publicacion
    ADD CONSTRAINT publicacion_texto_valido CHECK (length(trim(util.texto_plano(texto))) BETWEEN 1 AND 500),
    ADD CONSTRAINT publicacion_formato_valido CHECK (length(texto) <= 1500);

-- Etiquetas y menciones, del texto visible (mismas reglas que 0003).
CREATE OR REPLACE FUNCTION social.extraer_etiquetas(p_texto text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(array_agg(etiqueta ORDER BY posicion), '{}')
    FROM (
        SELECT etiqueta, min(posicion) AS posicion
        FROM (
            SELECT lower(m[1]) AS etiqueta, n AS posicion
            FROM regexp_matches(util.texto_plano(p_texto), '#([[:alnum:]_]+)', 'g') WITH ORDINALITY AS r(m, n)
        ) AS todas
        WHERE etiqueta ~ '^[a-z0-9_áéíóúñü]{1,50}$'
        GROUP BY etiqueta
        ORDER BY min(posicion)
        LIMIT 10
    ) AS primeras;
$$;

CREATE OR REPLACE FUNCTION social.extraer_menciones(p_texto text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(array_agg(nombre ORDER BY posicion), '{}')
    FROM (
        SELECT nombre, min(posicion) AS posicion
        FROM (
            SELECT lower(m[1]) AS nombre, n AS posicion
            FROM regexp_matches(util.texto_plano(p_texto), '(?:^|[^[:alnum:]_])@([A-Za-z0-9_]{3,30})', 'g')
                 WITH ORDINALITY AS r(m, n)
        ) AS todas
        GROUP BY nombre
        ORDER BY min(posicion)
        LIMIT 10
    ) AS primeras;
$$;

-- La verificación lee el texto plano de las publicaciones.
CREATE OR REPLACE FUNCTION social.texto_para_verificar(p_tipo text, p_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT CASE p_tipo
        WHEN 'publicacion' THEN (SELECT util.texto_plano(texto) FROM social.publicacion WHERE id = p_id AND estado = 'visible')
        WHEN 'declaracion' THEN (SELECT texto FROM social.declaracion WHERE id = p_id)
    END;
$$;
