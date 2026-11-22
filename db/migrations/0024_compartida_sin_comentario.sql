-- 0024 · Una publicación compartida sin comentario no tiene texto que verificar, y debe quedar resuelta.
--
-- social.texto_para_verificar devolvía NULL tanto para una publicación retirada como para una compartida
-- sin comentario (texto nulo). El trabajador de verificación trata NULL como "retirada: nada que revisar",
-- la marca como entregada y no registra procesamiento; la API ve una publicación sin procesamiento y la
-- muestra "pendiente" para siempre ("Uniendo la cifra a su dato oficial…" en una compartida sin cifras).
--
-- Ahora: visible y sin texto -> '' (no pasa el filtro previo, queda 'sin_cifras' sin gastar IA);
--        retirada o inexistente -> NULL, como antes.

CREATE OR REPLACE FUNCTION social.texto_para_verificar(p_tipo text, p_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT CASE p_tipo
        WHEN 'publicacion' THEN (SELECT coalesce(util.texto_plano(texto), '') FROM social.publicacion
                                 WHERE id = p_id AND estado = 'visible')
        WHEN 'declaracion' THEN (SELECT texto FROM social.declaracion WHERE id = p_id)
    END;
$$;
COMMENT ON FUNCTION social.texto_para_verificar(text, uuid)
    IS 'Texto plano que lee la verificación: vacío si la publicación visible no tiene texto (compartida sin comentario), NULL si fue retirada';

-- Las compartidas sin comentario que ya quedaron sin procesamiento.
INSERT INTO verificacion.procesamiento (origen_tipo, origen_id, resultado)
SELECT 'publicacion', p.id, 'sin_cifras'
FROM social.publicacion p
WHERE p.texto IS NULL AND p.estado = 'visible'
  AND NOT EXISTS (SELECT 1 FROM verificacion.procesamiento v
                  WHERE v.origen_tipo = 'publicacion' AND v.origen_id = p.id);
