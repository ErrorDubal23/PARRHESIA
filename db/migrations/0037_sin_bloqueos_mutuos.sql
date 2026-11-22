-- 0037 · Acciones simultáneas sobre la misma publicación sin bloqueos mutuos (auditoría BD-11, 22 nov 2026).
--
-- Prueba de la auditoría: 12 respuestas (o 12 reacciones, o 12 compartidas) a la misma publicación al mismo
-- tiempo. Resultado: 11 de 12 fallaban con "deadlock detected" (los contadores quedaban bien, pero las
-- respuestas se perdían y la persona veía un error). Causa: publicar y reaccionar tomaban la publicación de
-- destino con un bloqueo compartido (para que no la retiren a mitad de camino) y al final el trigger de
-- contadores la actualiza; dos transacciones con el bloqueo compartido intentaban subirlo a uno de escritura a
-- la vez. Corrección: tomarla desde el principio con FOR NO KEY UPDATE. Las acciones simultáneas sobre la misma
-- publicación esperan su turno en vez de chocar; FOR NO KEY UPDATE no bloquea a quien solo la lee ni a las
-- llaves foráneas que apuntan a ella. Mismo cuerpo que antes salvo esa línea.

CREATE OR REPLACE PROCEDURE social.publicar(IN p_autor_id uuid, IN p_texto text, IN p_responde_a_id uuid, IN p_comparte_id uuid, IN p_figuras_ids uuid[], INOUT p_publicacion_id uuid)
 LANGUAGE plpgsql
AS $procedure$
DECLARE
    v_etiqueta text;
BEGIN
    PERFORM 1 FROM social.usuario WHERE id = p_autor_id AND estado = 'activo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'autor_inactivo: la cuenta no existe o no está activa';
    END IF;

    -- No se responde ni se comparte una publicación retirada. El bloqueo impide que la retiren mientras esta
    -- transacción la usa. Es de escritura (FOR NO KEY UPDATE, 0037) porque el contador de la publicación de destino
    -- se actualiza al final: con un bloqueo compartido, dos respuestas simultáneas se bloqueaban mutuamente.
    IF p_responde_a_id IS NOT NULL OR p_comparte_id IS NOT NULL THEN
        PERFORM 1 FROM social.publicacion
        WHERE id = coalesce(p_responde_a_id, p_comparte_id) AND estado = 'visible'
        FOR NO KEY UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'publicacion_destino_no_visible: la publicación no existe o fue retirada';
        END IF;
    END IF;

    INSERT INTO social.publicacion (autor_id, texto, responde_a_id, comparte_id)
    VALUES (p_autor_id, nullif(trim(p_texto), ''), p_responde_a_id, p_comparte_id)
    RETURNING id INTO p_publicacion_id;

    FOREACH v_etiqueta IN ARRAY social.extraer_etiquetas(p_texto) LOOP
        INSERT INTO social.etiqueta (nombre) VALUES (v_etiqueta) ON CONFLICT (nombre) DO NOTHING;
        INSERT INTO social.publicacion_etiqueta (publicacion_id, etiqueta_id)
        SELECT p_publicacion_id, e.id FROM social.etiqueta e WHERE e.nombre = v_etiqueta;
    END LOOP;

    -- Solo se guardan menciones de cuentas que existen.
    INSERT INTO social.mencion_usuario (publicacion_id, usuario_id)
    SELECT p_publicacion_id, u.id FROM social.usuario u
    WHERE u.nombre_usuario = ANY (social.extraer_menciones(p_texto));

    -- Las figuras se eligen de una lista en la app; la llave foránea rechaza una que no exista.
    INSERT INTO social.mencion_figura (publicacion_id, figura_id)
    SELECT DISTINCT p_publicacion_id, f FROM unnest(coalesce(p_figuras_ids, '{}')) AS f;
END;
$procedure$
;

CREATE OR REPLACE PROCEDURE social.reaccionar(IN p_publicacion_id uuid, IN p_usuario_id uuid, IN p_tipo text)
 LANGUAGE plpgsql
AS $procedure$
BEGIN
    IF social.rol_usuario(p_usuario_id) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    -- Bloqueo de escritura desde el inicio (0037): el contador de reacciones de esta publicación se actualiza al
    -- final, y con un bloqueo compartido dos reacciones simultáneas se bloqueaban mutuamente (deadlock).
    PERFORM 1 FROM social.publicacion WHERE id = p_publicacion_id AND estado = 'visible' FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'publicacion_no_visible: la publicación no existe o fue retirada';
    END IF;
    -- Cambiar de "me gusta" a "útil" actualiza la misma fila: no suma dos reacciones.
    INSERT INTO social.reaccion (publicacion_id, usuario_id, tipo) VALUES (p_publicacion_id, p_usuario_id, p_tipo)
    ON CONFLICT (publicacion_id, usuario_id) DO UPDATE SET tipo = EXCLUDED.tipo
        WHERE social.reaccion.tipo IS DISTINCT FROM EXCLUDED.tipo;
END;
$procedure$
;

