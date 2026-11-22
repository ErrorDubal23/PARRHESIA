-- 0027 · Una persona comparte (sin comentario) una misma publicación una sola vez.
--
-- Cada clic en "Compartir" creaba una compartida nueva: en la base de desarrollo una cuenta había compartido
-- la misma publicación 90 veces, y los contadores y el feed lo reflejaban. Como en cualquier red, compartir
-- es una sola vez; volver a pulsar deshace (retira la compartida). Compartir CON comentario (cita) sigue
-- siendo libre: cada comentario es una publicación distinta.

-- Duplicados que ya existían: se conserva la primera compartida y se retiran las demás. Se hace con el
-- UPDATE de siempre, así los triggers ajustan los contadores y el outbox lleva el retiro al grafo.
UPDATE social.publicacion p SET estado = 'retirada_por_autor'
WHERE p.texto IS NULL AND p.comparte_id IS NOT NULL AND p.estado = 'visible'
  AND EXISTS (SELECT 1 FROM social.publicacion q
              WHERE q.autor_id = p.autor_id AND q.comparte_id = p.comparte_id AND q.texto IS NULL
                AND q.estado = 'visible' AND (q.creado_en, q.id) < (p.creado_en, p.id));

CREATE UNIQUE INDEX publicacion_una_compartida_idx ON social.publicacion (autor_id, comparte_id)
    WHERE texto IS NULL AND estado = 'visible';
COMMENT ON INDEX social.publicacion_una_compartida_idx
    IS 'Una sola compartida sin comentario, visible, por persona y publicación (retirarla permite compartir otra vez)';
