-- 0012: sesiones revocables e intentos de acceso.
--
-- Antes, la sesión era solo un token firmado: cerrar sesión lo borraba del navegador,
-- pero un token copiado seguía sirviendo hasta vencer. Ahora cada sesión existe en la
-- base: cerrar sesión la revoca en el servidor, y una cuenta suspendida pierde el acceso
-- al instante (social.sesion_activa revisa las dos cosas en cada petición).
-- Además se registran los intentos de acceso para frenar a quien prueba contraseñas.

CREATE TABLE social.sesion (
    jti          uuid        NOT NULL DEFAULT gen_random_uuid(),   -- identificador que va dentro del token
    usuario_id   uuid        NOT NULL,
    agente       text,                                              -- navegador, para que el usuario reconozca la sesión
    creada_en    timestamptz NOT NULL DEFAULT now(),
    vence_en     timestamptz NOT NULL,
    revocada_en  timestamptz,
    CONSTRAINT sesion_pkey PRIMARY KEY (jti),
    CONSTRAINT sesion_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id),
    CONSTRAINT sesion_vence_despues CHECK (vence_en > creada_en),
    CONSTRAINT sesion_agente_valido CHECK (length(agente) <= 300)
);
CREATE INDEX sesion_usuario_idx ON social.sesion (usuario_id) WHERE revocada_en IS NULL;
COMMENT ON TABLE social.sesion IS 'Sesiones iniciadas. Solo cambia revocada_en, una vez (al cerrar sesión)';

-- Intentos de acceso. El origen se guarda como huella (sha256 de la IP), no la IP.
CREATE TABLE social.intento_acceso (
    id         bigint      GENERATED ALWAYS AS IDENTITY,
    correo     text        NOT NULL,
    origen     text        NOT NULL,
    exito      boolean     NOT NULL,
    creado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT intento_acceso_pkey PRIMARY KEY (id),
    CONSTRAINT intento_acceso_origen_es_huella CHECK (origen ~ '^[0-9a-f]{64}$')
);
CREATE INDEX intento_acceso_correo_idx ON social.intento_acceso (correo, creado_en DESC);
CREATE INDEX intento_acceso_origen_idx ON social.intento_acceso (origen, creado_en DESC);
COMMENT ON TABLE social.intento_acceso IS 'Intentos de inicio de sesión, para limitar los fallos. Solo inserción';

-- Una sesión solo puede pasar de abierta a revocada, una vez; nada más cambia.
CREATE FUNCTION social.sesion_solo_se_revoca() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.revocada_en IS NOT NULL OR NEW.revocada_en IS NULL
       OR (to_jsonb(NEW) - 'revocada_en') IS DISTINCT FROM (to_jsonb(OLD) - 'revocada_en') THEN
        RAISE EXCEPTION 'social.sesion: una sesión solo se puede revocar, una vez';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sesion_solo_se_revoca BEFORE UPDATE ON social.sesion
    FOR EACH ROW EXECUTE FUNCTION social.sesion_solo_se_revoca();
CREATE TRIGGER sesion_sin_borrado BEFORE DELETE ON social.sesion
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER intento_acceso_solo_insercion BEFORE UPDATE OR DELETE ON social.intento_acceso
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- ¿Está bloqueado el acceso? 5 fallos de un correo, o 20 de un mismo origen, en 15 minutos.
CREATE FUNCTION social.acceso_bloqueado(p_correo text, p_origen text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT (SELECT count(*) FROM social.intento_acceso
            WHERE correo = lower(trim(p_correo)) AND NOT exito AND creado_en > now() - interval '15 minutes') >= 5
        OR (SELECT count(*) FROM social.intento_acceso
            WHERE origen = p_origen AND NOT exito AND creado_en > now() - interval '15 minutes') >= 20;
$$;
COMMENT ON FUNCTION social.acceso_bloqueado(text, text) IS 'Verdadero tras 5 fallos de un correo o 20 de un origen en 15 minutos';

CREATE PROCEDURE social.registrar_intento_acceso(p_correo text, p_origen text, p_exito boolean)
LANGUAGE sql AS $$
    INSERT INTO social.intento_acceso (correo, origen, exito) VALUES (lower(trim(p_correo)), p_origen, p_exito);
$$;

CREATE PROCEDURE social.iniciar_sesion(p_usuario_id uuid, p_agente text, p_duracion interval,
                                       INOUT p_jti uuid, INOUT p_vence_en timestamptz)
LANGUAGE plpgsql AS $$
BEGIN
    IF social.rol_usuario(p_usuario_id) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    INSERT INTO social.sesion (usuario_id, agente, vence_en)
    VALUES (p_usuario_id, left(p_agente, 300), now() + p_duracion)
    RETURNING jti, vence_en INTO p_jti, p_vence_en;
END;
$$;

CREATE PROCEDURE social.cerrar_sesion(p_jti uuid)
LANGUAGE sql AS $$
    UPDATE social.sesion SET revocada_en = now() WHERE jti = p_jti AND revocada_en IS NULL;
$$;

-- La revisan todos los servicios en cada petición con sesión: devuelve el rol vigente
-- del usuario, o nada si la sesión venció, fue revocada o la cuenta no está activa.
-- Así un cambio de rol o una suspensión aplica de inmediato, sin esperar a que el token venza.
CREATE FUNCTION social.sesion_activa(p_jti uuid) RETURNS TABLE (usuario_id uuid, nombre_usuario text, rol text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT u.id, u.nombre_usuario, u.rol
    FROM social.sesion s JOIN social.usuario u ON u.id = s.usuario_id
    WHERE s.jti = p_jti AND s.revocada_en IS NULL AND s.vence_en > now() AND u.estado = 'activo';
$$;
COMMENT ON FUNCTION social.sesion_activa(uuid) IS 'Usuario y rol de una sesión vigente; nada si venció, se revocó o la cuenta no está activa';

GRANT SELECT, INSERT, UPDATE ON social.sesion, social.intento_acceso TO svc_social;
GRANT EXECUTE ON FUNCTION social.acceso_bloqueado(text, text) TO svc_social;
GRANT EXECUTE ON PROCEDURE social.registrar_intento_acceso(text, text, boolean), social.iniciar_sesion(uuid, text, interval, uuid, timestamptz),
                           social.cerrar_sesion(uuid) TO svc_social;
GRANT EXECUTE ON FUNCTION social.sesion_activa(uuid) TO svc_social, svc_verificacion, svc_temas, svc_oficial;
GRANT USAGE ON SCHEMA social TO svc_oficial;
