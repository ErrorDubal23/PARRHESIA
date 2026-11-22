-- 0017 · Corrige 0016: un texto nulo sigue siendo nulo.
--
-- Al compartir una publicación sin comentario, el texto es NULL. En 0016, util.texto_plano lo convertía
-- en '' y la restricción publicacion_texto_valido (1 a 500 visibles) rechazaba el compartido. Con STRICT,
-- NULL entra y sale como NULL y la restricción vuelve a aceptarlo, como antes de 0016.

CREATE OR REPLACE FUNCTION util.texto_plano(p_texto text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = '' AS $$
    SELECT regexp_replace(
               regexp_replace(
                   regexp_replace(p_texto,
                       '\[([^\]\n]{1,200})\]\((https://[^\s)]+)\)', '\1', 'g'),   -- [texto](https://...)
                   '(^|[^[:alnum:]*])\*\*([^*\s]|[^*\s][^*\n]*[^*\s])\*\*(?![[:alnum:]*])', '\1\2', 'g'),  -- **negrita**
               '(^|[^[:alnum:]*])\*([^*\s]|[^*\s][^*\n]*[^*\s])\*(?![[:alnum:]*])', '\1\2', 'g');          -- *cursiva*
$$;
