-- 0035 · Quién administra y quién verifica lo decide un procedimiento, con bitácora pública.
--
-- Hasta aquí el rol de una cuenta (usuario, verificador, admin) solo se cambiaba con un UPDATE directo y sin
-- registro, y no había ningún administrador (22 nov 2026: un verificador, @prueba_editor, puesto a mano).
-- Los verificadores registran figuras y declaraciones y hacen las revisiones humanas: quién tiene ese permiso
-- tiene que ser tan trazable como lo que hace.
--
-- 1. social.cambio_rol: bitácora de solo inserción (quién, de qué rol a cuál, quién lo decidió y por qué).
-- 2. social.asignar_rol: lo usa un administrador desde la app.
-- 3. social.asignar_rol_consola: sin actor, para el primer administrador y para las pruebas. No se le da permiso
--    a ningún servicio: solo lo ejecuta el dueño de la base (consola o migración), nunca la web.
-- 4. Un trigger impide cambiar el rol por fuera de esos procedimientos y otro impide quedarse sin administrador.
-- 5. El rol que @prueba_editor ya tenía queda en la bitácora como anterior a ella (no se inventa quién lo dio).

-- 1 · Bitácora ---------------------------------------------------------------------------------------------------
CREATE TABLE social.cambio_rol (
    id             bigint      GENERATED ALWAYS AS IDENTITY,
    usuario_id     uuid        NOT NULL,
    rol_anterior   text        NOT NULL,
    rol_nuevo      text        NOT NULL,
    actor_id       uuid,                       -- nulo: desde la consola (primer administrador) o anterior a la bitácora
    motivo         text        NOT NULL,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT cambio_rol_pkey PRIMARY KEY (id),
    CONSTRAINT cambio_rol_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id),
    CONSTRAINT cambio_rol_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES social.usuario (id),
    CONSTRAINT cambio_rol_roles_validos CHECK (rol_anterior IN ('usuario', 'verificador', 'admin')
                                               AND rol_nuevo IN ('usuario', 'verificador', 'admin')),
    CONSTRAINT cambio_rol_es_cambio CHECK (rol_anterior <> rol_nuevo),
    CONSTRAINT cambio_rol_motivo_valido CHECK (length(trim(motivo)) >= 10)
);
CREATE INDEX cambio_rol_usuario_idx ON social.cambio_rol (usuario_id, id DESC);
CREATE TRIGGER cambio_rol_solo_insercion BEFORE UPDATE OR DELETE ON social.cambio_rol
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
COMMENT ON TABLE social.cambio_rol IS 'Cambios de rol de cada cuenta: de qué a qué, quién lo decidió y por qué. Solo inserción';

-- 2 y 3 · Procedimientos (los dos pasan por el mismo cambio interno) ------------------------------------------
CREATE FUNCTION social._cambiar_rol(p_actor uuid, p_usuario uuid, p_rol text, p_motivo text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_anterior text;
BEGIN
    SELECT rol INTO v_anterior FROM social.usuario WHERE id = p_usuario AND estado = 'activo' FOR UPDATE;
    IF v_anterior IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    IF v_anterior = p_rol THEN
        RAISE EXCEPTION 'rol_sin_cambio: la cuenta ya tiene ese rol';
    END IF;
    PERFORM set_config('parrhesia.cambio_rol', 'procedimiento', true);   -- solo dentro de esta transacción
    UPDATE social.usuario SET rol = p_rol WHERE id = p_usuario;
    INSERT INTO social.cambio_rol (usuario_id, rol_anterior, rol_nuevo, actor_id, motivo)
    VALUES (p_usuario, v_anterior, p_rol, p_actor, p_motivo);
    PERFORM set_config('parrhesia.cambio_rol', '', true);
END;
$$;
COMMENT ON FUNCTION social._cambiar_rol(uuid, uuid, text, text) IS 'Cambio de rol con su registro; la usan solo los dos procedimientos';

-- SECURITY DEFINER: el servicio social puede llamar este procedimiento (que exige un administrador), pero no el
-- cambio interno, que no pide actor.
CREATE PROCEDURE social.asignar_rol(p_actor uuid, p_usuario uuid, p_rol text, p_motivo text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    IF coalesce(social.rol_usuario(p_actor), '') <> 'admin' THEN
        RAISE EXCEPTION 'sin_permiso: solo un administrador asigna roles';
    END IF;
    PERFORM social._cambiar_rol(p_actor, p_usuario, p_rol, p_motivo);
END;
$$;
COMMENT ON PROCEDURE social.asignar_rol(uuid, uuid, text, text) IS 'Un administrador cambia el rol de una cuenta, con motivo en la bitácora';

CREATE PROCEDURE social.asignar_rol_consola(p_usuario uuid, p_rol text, p_motivo text)
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM social._cambiar_rol(NULL, p_usuario, p_rol, p_motivo);
END;
$$;
COMMENT ON PROCEDURE social.asignar_rol_consola(uuid, text, text)
    IS 'Cambio de rol desde la consola del dueño de la base (primer administrador, pruebas). Ningún servicio tiene permiso';

-- 4 · Reglas en la tabla de cuentas ----------------------------------------------------------------------------
CREATE FUNCTION social.rol_solo_por_procedimiento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Solo dentro de los procedimientos (que marcan la transacción) y nunca con el rol de un servicio: un servicio
    -- que pusiera la marca por su cuenta igual quedaría por fuera, porque el procedimiento corre como dueño.
    IF NEW.rol IS DISTINCT FROM OLD.rol
       AND (coalesce(current_setting('parrhesia.cambio_rol', true), '') <> 'procedimiento' OR current_user LIKE 'svc\_%') THEN
        RAISE EXCEPTION 'rol_por_procedimiento: el rol solo cambia con social.asignar_rol (queda en la bitácora)';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER usuario_rol_por_procedimiento BEFORE UPDATE OF rol ON social.usuario
    FOR EACH ROW EXECUTE FUNCTION social.rol_solo_por_procedimiento();

-- Al terminar la sentencia, si había administradores, tiene que quedar al menos uno activo.
CREATE FUNCTION social.conservar_un_admin() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM antes WHERE rol = 'admin' AND estado = 'activo')
       AND NOT EXISTS (SELECT 1 FROM social.usuario WHERE rol = 'admin' AND estado = 'activo') THEN
        RAISE EXCEPTION 'ultimo_admin: Parrhesia debe conservar al menos un administrador';
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER usuario_conserva_un_admin AFTER UPDATE ON social.usuario
    REFERENCING OLD TABLE AS antes FOR EACH STATEMENT EXECUTE FUNCTION social.conservar_un_admin();
COMMENT ON FUNCTION social.conservar_un_admin() IS 'Impide quitar o desactivar al último administrador activo';

-- Para la página "Equipo": quiénes tienen un rol y la bitácora, legibles por el servicio social.
CREATE VIEW social.equipo AS
    SELECT u.id, u.nombre_usuario, u.nombre_visible, u.rol,
           (SELECT max(c.creado_en) FROM social.cambio_rol c WHERE c.usuario_id = u.id) AS desde
    FROM social.usuario u
    WHERE u.rol IN ('verificador', 'admin') AND u.estado = 'activo';
COMMENT ON VIEW social.equipo IS 'Cuentas activas con rol de verificador o administrador';

-- 5 · Lo que ya existía -----------------------------------------------------------------------------------------
INSERT INTO social.cambio_rol (usuario_id, rol_anterior, rol_nuevo, actor_id, motivo, creado_en)
SELECT id, 'usuario', rol, NULL, 'Rol asignado antes de existir la bitácora de roles (migración 0035).', creado_en
FROM social.usuario WHERE rol <> 'usuario';

-- Permisos. asignar_rol_consola y _cambiar_rol no se dan a ningún servicio; se quitan explícitamente a PUBLIC
-- (una rutina nueva lo trae por defecto) para que solo el dueño de la base pueda usarlas.
REVOKE EXECUTE ON PROCEDURE social.asignar_rol_consola(uuid, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION social._cambiar_rol(uuid, uuid, text, text) FROM PUBLIC;
REVOKE EXECUTE ON PROCEDURE social.asignar_rol(uuid, uuid, text, text) FROM PUBLIC;
GRANT SELECT ON social.cambio_rol, social.equipo TO svc_social;
GRANT EXECUTE ON PROCEDURE social.asignar_rol(uuid, uuid, text, text) TO svc_social;
