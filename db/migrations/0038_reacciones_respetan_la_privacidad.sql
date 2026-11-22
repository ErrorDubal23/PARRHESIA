-- 0038 · Reaccionar respeta la privacidad de las comunidades (auditoría PR-07, 22 nov 2026).
--
-- Hallazgo: quien no es integrante de una comunidad privada podía reaccionar a una de sus publicaciones si
-- conocía su id: social.reaccionar solo comprobaba que estuviera visible. La reacción se guardaba y el contador
-- subía (la API luego fallaba al no poder mostrarla). Responder y compartir ya lo impedían.
-- Corrección: la misma regla que el resto, social.puede_ver_publicacion; si no puede verla, para esa persona la
-- publicación no existe (mismo error que una retirada). Mismo cuerpo que en la 0037 salvo esa comprobación.
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
    IF NOT FOUND OR NOT coalesce(social.puede_ver_publicacion(p_publicacion_id, p_usuario_id), false) THEN
        RAISE EXCEPTION 'publicacion_no_visible: la publicación no existe o fue retirada';
    END IF;
    -- Cambiar de "me gusta" a "útil" actualiza la misma fila: no suma dos reacciones.
    INSERT INTO social.reaccion (publicacion_id, usuario_id, tipo) VALUES (p_publicacion_id, p_usuario_id, p_tipo)
    ON CONFLICT (publicacion_id, usuario_id) DO UPDATE SET tipo = EXCLUDED.tipo
        WHERE social.reaccion.tipo IS DISTINCT FROM EXCLUDED.tipo;
END;
$procedure$;
