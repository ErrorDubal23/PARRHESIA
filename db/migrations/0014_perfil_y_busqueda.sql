-- 0014 · Perfil editable, foto, cuenta desactivada y búsqueda de personas (segunda etapa, T7; decisión 30).
--
-- Toda escritura sigue siendo un procedimiento: la API no actualiza la tabla directamente.
-- Solo cada persona cambia su perfil: los procedimientos reciben el id de la sesión, nunca otro.

-- Búsqueda por parecido de texto (trigramas). En el esquema util, junto a las demás utilidades.
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA util;

-- FOTO: nombre del archivo que guarda el servicio social (32 hex + .webp). La imagen nunca va en la base.
ALTER TABLE social.usuario
    ADD COLUMN foto text,
    ADD CONSTRAINT usuario_foto_valida CHECK (foto ~ '^[0-9a-f]{32}\.webp$');

-- Decisión 30: las cuentas se desactivan, no se borran (los hilos de otros quedan completos).
ALTER TABLE social.usuario DROP CONSTRAINT usuario_estado_valido;
ALTER TABLE social.usuario ADD CONSTRAINT usuario_estado_valido
    CHECK (estado IN ('activo', 'en_revision', 'suspendido', 'desactivada'));

CREATE INDEX usuario_nombre_usuario_trgm ON social.usuario USING gin (nombre_usuario util.gin_trgm_ops);
CREATE INDEX usuario_nombre_visible_trgm ON social.usuario USING gin (lower(nombre_visible) util.gin_trgm_ops);

-- ¿Se puede usar este nombre de usuario? 'disponible', 'invalido' o 'en_uso'.
CREATE FUNCTION social.nombre_usuario_disponible(p_nombre text) RETURNS text
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT CASE
        WHEN lower(trim(p_nombre)) !~ '^[a-z0-9_]{3,30}$' THEN 'invalido'
        WHEN EXISTS (SELECT 1 FROM social.usuario WHERE nombre_usuario = lower(trim(p_nombre))) THEN 'en_uso'
        ELSE 'disponible' END;
$$;
COMMENT ON FUNCTION social.nombre_usuario_disponible(text) IS 'Disponibilidad de un nombre de usuario, para validar mientras se escribe';

-- Buscar personas por nombre de usuario o nombre visible. Primero las que empiezan igual, luego por
-- parecido. Solo cuentas activas y solo datos públicos. p_yo (opcional) dice si ya las sigo.
CREATE FUNCTION social.buscar_usuarios(p_texto text, p_yo uuid DEFAULT NULL, p_limite integer DEFAULT 20)
RETURNS TABLE (id uuid, nombre_usuario text, nombre_visible text, foto text, biografia text,
               seguidores bigint, lo_sigo boolean)
LANGUAGE sql STABLE SET search_path = '' AS $$
    WITH q AS (SELECT lower(trim(both '@ ' FROM p_texto)) AS t)
    SELECT u.id, u.nombre_usuario, u.nombre_visible, u.foto, u.biografia,
           (SELECT count(*) FROM social.seguimiento s WHERE s.seguido_id = u.id),
           p_yo IS NOT NULL AND EXISTS (SELECT 1 FROM social.seguimiento s WHERE s.seguidor_id = p_yo AND s.seguido_id = u.id)
    FROM social.usuario u, q
    WHERE u.estado = 'activo' AND length(q.t) >= 2
      AND (u.nombre_usuario LIKE q.t || '%' OR lower(u.nombre_visible) LIKE '%' || q.t || '%'
           OR util.similarity(u.nombre_usuario, q.t) > 0.3 OR util.similarity(lower(u.nombre_visible), q.t) > 0.3)
    ORDER BY (u.nombre_usuario LIKE q.t || '%' OR lower(u.nombre_visible) LIKE q.t || '%') DESC,
             greatest(util.similarity(u.nombre_usuario, q.t), util.similarity(lower(u.nombre_visible), q.t)) DESC,
             u.nombre_usuario
    LIMIT least(greatest(p_limite, 1), 50);
$$;
COMMENT ON FUNCTION social.buscar_usuarios(text, uuid, integer) IS 'Personas por nombre, solo cuentas activas y datos públicos';

-- Actualiza el perfil público. NULL deja el campo como está; una biografía vacía la borra.
CREATE PROCEDURE social.actualizar_perfil(p_usuario_id uuid, p_nombre_visible text, p_nombre_usuario text, p_biografia text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    UPDATE social.usuario SET
        nombre_visible = coalesce(trim(p_nombre_visible), nombre_visible),
        nombre_usuario = coalesce(lower(trim(p_nombre_usuario)), nombre_usuario),
        biografia = CASE WHEN p_biografia IS NULL THEN biografia ELSE nullif(trim(p_biografia), '') END,
        actualizado_en = now()
    WHERE id = p_usuario_id AND estado = 'activo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
END;
$$;
COMMENT ON PROCEDURE social.actualizar_perfil(uuid, text, text, text) IS 'Cambia nombre visible, nombre de usuario y biografía de la propia cuenta';

-- Cambia la foto y devuelve el archivo anterior para que el servicio lo borre del disco.
CREATE PROCEDURE social.fijar_foto(p_usuario_id uuid, p_foto text, INOUT p_anterior text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    SELECT foto INTO p_anterior FROM social.usuario WHERE id = p_usuario_id AND estado = 'activo' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    UPDATE social.usuario SET foto = p_foto, actualizado_en = now() WHERE id = p_usuario_id;
END;
$$;
COMMENT ON PROCEDURE social.fijar_foto(uuid, text, text) IS 'Pone o quita (NULL) la foto; devuelve la anterior';

CREATE PROCEDURE social.cambiar_correo(p_usuario_id uuid, p_correo text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    UPDATE social.usuario SET correo = lower(trim(p_correo)), actualizado_en = now()
    WHERE id = p_usuario_id AND estado = 'activo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
END;
$$;
COMMENT ON PROCEDURE social.cambiar_correo(uuid, text) IS 'Cambia el correo (la API exige antes la contraseña actual)';

-- Nueva contraseña y cierre de todas las demás sesiones abiertas (la actual sigue).
CREATE PROCEDURE social.cambiar_clave(p_usuario_id uuid, p_clave_hash text, p_jti_actual uuid, INOUT p_cerradas integer)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    UPDATE social.usuario SET clave_hash = p_clave_hash, actualizado_en = now()
    WHERE id = p_usuario_id AND estado = 'activo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    UPDATE social.sesion SET revocada_en = now()
    WHERE usuario_id = p_usuario_id AND jti <> p_jti_actual AND revocada_en IS NULL;
    GET DIAGNOSTICS p_cerradas = ROW_COUNT;
END;
$$;
COMMENT ON PROCEDURE social.cambiar_clave(uuid, text, uuid, integer) IS 'Cambia la contraseña y cierra las otras sesiones';

-- Decisión 30: desactivar es definitivo para la persona (no puede volver a entrar) y cierra todas
-- sus sesiones. Sus publicaciones se conservan para que los hilos de otros no queden rotos.
CREATE PROCEDURE social.desactivar_cuenta(p_usuario_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    UPDATE social.usuario SET estado = 'desactivada', actualizado_en = now()
    WHERE id = p_usuario_id AND estado = 'activo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    UPDATE social.sesion SET revocada_en = now() WHERE usuario_id = p_usuario_id AND revocada_en IS NULL;
END;
$$;
COMMENT ON PROCEDURE social.desactivar_cuenta(uuid) IS 'Desactiva la propia cuenta y cierra todas sus sesiones';

-- Una cuenta desactivada no vuelve a activarse por la app (solo un administrador, directamente).
CREATE FUNCTION social.desactivada_es_final() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF OLD.estado = 'desactivada' AND NEW.estado <> 'desactivada' AND current_setting('parrhesia.admin', true) IS DISTINCT FROM 'si' THEN
        RAISE EXCEPTION 'cuenta_desactivada: una cuenta desactivada no se reactiva desde la aplicación';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER usuario_desactivada_es_final BEFORE UPDATE OF estado ON social.usuario
    FOR EACH ROW EXECUTE FUNCTION social.desactivada_es_final();

-- Outbox: el grafo guarda el nombre de usuario, así que se le avisa cuando cambia (misma transacción).
CREATE FUNCTION social.emitir_perfil_actualizado() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    INSERT INTO social.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
    VALUES ('usuario', NEW.id::text, 'usuario_actualizado',
            jsonb_build_object('id', NEW.id, 'nombre_usuario', NEW.nombre_usuario));
    RETURN NULL;
END;
$$;
COMMENT ON FUNCTION social.emitir_perfil_actualizado() IS 'Evento usuario_actualizado cuando cambia el nombre de usuario';
CREATE TRIGGER usuario_perfil_salida AFTER UPDATE OF nombre_usuario ON social.usuario
    FOR EACH ROW WHEN (OLD.nombre_usuario IS DISTINCT FROM NEW.nombre_usuario)
    EXECUTE FUNCTION social.emitir_perfil_actualizado();

-- Permisos (0007 quita EXECUTE a PUBLIC por defecto): solo el servicio social.
GRANT EXECUTE ON FUNCTION social.nombre_usuario_disponible(text), social.buscar_usuarios(text, uuid, integer) TO svc_social;
GRANT EXECUTE ON PROCEDURE social.actualizar_perfil(uuid, text, text, text), social.fijar_foto(uuid, text, text),
    social.cambiar_correo(uuid, text), social.cambiar_clave(uuid, text, uuid, integer), social.desactivar_cuenta(uuid)
    TO svc_social;
