-- 0015 · El nombre de usuario se puede cambiar, sin romper menciones ni permitir suplantaciones.
--
-- Hasta ahora (0003) el nombre de usuario no cambiaba. La segunda etapa (T7) permite cambiarlo, con
-- tres reglas que guarda la base:
--   1. El nombre anterior queda reservado para su dueño: las menciones viejas (@ana) siguen llevando a
--      su perfil y nadie más puede registrarse con ese nombre para quedarse con ellas.
--   2. Un cambio cada 30 días como máximo (evita usar el cambio para confundir).
--   3. El id y la fecha de creación siguen sin cambiar.

CREATE TABLE social.nombre_anterior (
    nombre       text        NOT NULL,
    usuario_id   uuid        NOT NULL,
    usado_hasta  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT nombre_anterior_pkey PRIMARY KEY (nombre),
    CONSTRAINT nombre_anterior_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id),
    CONSTRAINT nombre_anterior_valido CHECK (nombre ~ '^[a-z0-9_]{3,30}$')
);
CREATE INDEX nombre_anterior_usuario_idx ON social.nombre_anterior (usuario_id, usado_hasta DESC);
COMMENT ON TABLE social.nombre_anterior IS 'Nombres de usuario que alguien dejó de usar: siguen siendo suyos';

-- Reemplaza la regla de 0003: ahora el nombre puede cambiar, con las reglas de arriba.
CREATE OR REPLACE FUNCTION social.usuario_normalizar() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    NEW.correo := lower(trim(NEW.correo));
    NEW.nombre_usuario := lower(trim(NEW.nombre_usuario));
    IF TG_OP = 'UPDATE' AND (NEW.id, NEW.creado_en) IS DISTINCT FROM (OLD.id, OLD.creado_en) THEN
        RAISE EXCEPTION 'social.usuario: el id y la fecha de creación no cambian';
    END IF;
    IF TG_OP = 'INSERT' OR NEW.nombre_usuario IS DISTINCT FROM OLD.nombre_usuario THEN
        -- Un nombre reservado solo lo puede volver a tomar su dueño.
        IF EXISTS (SELECT 1 FROM social.nombre_anterior a WHERE a.nombre = NEW.nombre_usuario AND a.usuario_id <> NEW.id) THEN
            RAISE EXCEPTION 'nombre_reservado: ese nombre de usuario perteneció a otra cuenta';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.nombre_usuario IS DISTINCT FROM OLD.nombre_usuario THEN
        IF EXISTS (SELECT 1 FROM social.nombre_anterior a
                   WHERE a.usuario_id = NEW.id AND a.usado_hasta > now() - interval '30 days') THEN
            RAISE EXCEPTION 'cambio_nombre_reciente: el nombre de usuario se puede cambiar una vez cada 30 días';
        END IF;
        INSERT INTO social.nombre_anterior (nombre, usuario_id, usado_hasta) VALUES (OLD.nombre_usuario, NEW.id, now())
        ON CONFLICT (nombre) DO UPDATE SET usado_hasta = EXCLUDED.usado_hasta;
        DELETE FROM social.nombre_anterior WHERE nombre = NEW.nombre_usuario AND usuario_id = NEW.id;  -- vuelve a ser el actual
    END IF;
    RETURN NEW;
END;
$$;

-- La cuenta a la que lleva un nombre, actual o anterior (para que las menciones viejas sigan sirviendo).
CREATE FUNCTION social.resolver_nombre(p_nombre text) RETURNS uuid
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(
        (SELECT id FROM social.usuario WHERE nombre_usuario = lower(trim(p_nombre))),
        (SELECT usuario_id FROM social.nombre_anterior WHERE nombre = lower(trim(p_nombre))));
$$;
COMMENT ON FUNCTION social.resolver_nombre(text) IS 'Id de la cuenta de un nombre de usuario actual o anterior';

-- La disponibilidad también tiene en cuenta los nombres reservados.
CREATE OR REPLACE FUNCTION social.nombre_usuario_disponible(p_nombre text) RETURNS text
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT CASE
        WHEN lower(trim(p_nombre)) !~ '^[a-z0-9_]{3,30}$' THEN 'invalido'
        WHEN social.resolver_nombre(p_nombre) IS NOT NULL THEN 'en_uso'
        ELSE 'disponible' END;
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON social.nombre_anterior TO svc_social;
GRANT EXECUTE ON FUNCTION social.resolver_nombre(text) TO svc_social;
