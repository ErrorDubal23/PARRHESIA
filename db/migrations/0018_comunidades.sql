-- 0018 · Comunidades (decisión 28, segunda etapa T10).
--
-- Una comunidad reúne a personas alrededor de un tema. Puede ser pública (cualquiera ve su contenido y
-- entra sin aprobación) o privada (su contenido solo lo ven sus integrantes y se entra con solicitud).
-- Las reglas de verificación son las mismas dentro y fuera de una comunidad: ninguna las cambia.
--
-- Papeles (no todos pueden lo mismo):
--   administrador          configura la comunidad, asigna papeles y puede todo lo demás
--   gestor                 acepta o rechaza solicitudes y expulsa (con motivo) a integrantes y moderadores
--   moderador              retira o fija publicaciones de la comunidad
--   integrante             publica, responde y ve el contenido
-- Una comunidad nunca se queda sin administrador (trigger con bloqueo de la fila de la comunidad).
-- Todo lo que hacen quienes administran queda en una bitácora de solo inserción.

-- COMUNIDAD -----------------------------------------------------------------------------------
CREATE TABLE social.comunidad (
    id                 uuid        NOT NULL DEFAULT gen_random_uuid(),
    nombre             text        NOT NULL,
    descripcion        text        NOT NULL,
    reglas             text,
    privacidad         text        NOT NULL DEFAULT 'publica',
    imagen             text,
    creada_por         uuid        NOT NULL,
    total_integrantes  integer     NOT NULL DEFAULT 0,   -- lo mantiene un trigger
    creada_en          timestamptz NOT NULL DEFAULT now(),
    actualizada_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT comunidad_pkey PRIMARY KEY (id),
    CONSTRAINT comunidad_creada_por_fkey FOREIGN KEY (creada_por) REFERENCES social.usuario (id),
    CONSTRAINT comunidad_nombre_valido CHECK (length(trim(nombre)) BETWEEN 3 AND 60),
    CONSTRAINT comunidad_descripcion_valida CHECK (length(trim(descripcion)) BETWEEN 10 AND 500),
    CONSTRAINT comunidad_reglas_validas CHECK (length(reglas) <= 2000),
    CONSTRAINT comunidad_privacidad_valida CHECK (privacidad IN ('publica', 'privada')),
    CONSTRAINT comunidad_imagen_valida CHECK (imagen ~ '^[0-9a-f]{32}\.webp$'),
    CONSTRAINT comunidad_total_valido CHECK (total_integrantes >= 0)
);
-- El nombre no se repite aunque cambien mayúsculas o espacios.
CREATE UNIQUE INDEX comunidad_nombre_key ON social.comunidad (lower(trim(nombre)));
CREATE INDEX comunidad_nombre_trgm ON social.comunidad USING gin (lower(nombre) util.gin_trgm_ops);
COMMENT ON TABLE social.comunidad IS 'Comunidad temática; no cambia las reglas de verificación';

-- INTEGRANTE ----------------------------------------------------------------------------------
CREATE TABLE social.integrante (
    comunidad_id  uuid        NOT NULL,
    usuario_id    uuid        NOT NULL,
    papel         text        NOT NULL DEFAULT 'integrante',
    desde         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT integrante_pkey PRIMARY KEY (comunidad_id, usuario_id),
    CONSTRAINT integrante_comunidad_id_fkey FOREIGN KEY (comunidad_id) REFERENCES social.comunidad (id),
    CONSTRAINT integrante_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id),
    CONSTRAINT integrante_papel_valido CHECK (papel IN ('integrante', 'moderador', 'gestor', 'administrador'))
);
CREATE INDEX integrante_usuario_idx ON social.integrante (usuario_id);
COMMENT ON TABLE social.integrante IS 'Quién pertenece a qué comunidad y con qué papel';

-- SOLICITUD DE INGRESO (comunidades privadas) ---------------------------------------------------
CREATE TABLE social.solicitud_ingreso (
    id            uuid        NOT NULL DEFAULT gen_random_uuid(),
    comunidad_id  uuid        NOT NULL,
    usuario_id    uuid        NOT NULL,
    mensaje       text,
    estado        text        NOT NULL DEFAULT 'pendiente',
    creada_en     timestamptz NOT NULL DEFAULT now(),
    resuelta_por  uuid,
    resuelta_en   timestamptz,
    motivo        text,
    CONSTRAINT solicitud_ingreso_pkey PRIMARY KEY (id),
    CONSTRAINT solicitud_ingreso_comunidad_id_fkey FOREIGN KEY (comunidad_id) REFERENCES social.comunidad (id),
    CONSTRAINT solicitud_ingreso_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id),
    CONSTRAINT solicitud_ingreso_resuelta_por_fkey FOREIGN KEY (resuelta_por) REFERENCES social.usuario (id),
    CONSTRAINT solicitud_ingreso_estado_valido CHECK (estado IN ('pendiente', 'aceptada', 'rechazada', 'retirada')),
    CONSTRAINT solicitud_ingreso_mensaje_valido CHECK (length(mensaje) <= 280),
    CONSTRAINT solicitud_ingreso_resolucion_coherente CHECK ((estado = 'pendiente') = (resuelta_en IS NULL))
);
-- Una sola solicitud pendiente por persona y comunidad.
CREATE UNIQUE INDEX solicitud_ingreso_pendiente_key ON social.solicitud_ingreso (comunidad_id, usuario_id) WHERE estado = 'pendiente';
CREATE TRIGGER solicitud_ingreso_transicion BEFORE UPDATE OF estado ON social.solicitud_ingreso
    FOR EACH ROW EXECUTE FUNCTION util.validar_transicion('{"pendiente": ["aceptada", "rechazada", "retirada"]}');
COMMENT ON TABLE social.solicitud_ingreso IS 'Solicitud para entrar a una comunidad privada';

-- BITÁCORA: lo que hacen quienes administran, a la vista de los integrantes. Solo inserción.
CREATE TABLE social.bitacora_comunidad (
    id            bigint      GENERATED ALWAYS AS IDENTITY,
    comunidad_id  uuid        NOT NULL,
    actor_id      uuid        NOT NULL,
    accion        text        NOT NULL,
    afectado_id   uuid,
    publicacion_id uuid,
    motivo        text,
    datos         jsonb       NOT NULL DEFAULT '{}',
    creada_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bitacora_comunidad_pkey PRIMARY KEY (id),
    CONSTRAINT bitacora_comunidad_comunidad_id_fkey FOREIGN KEY (comunidad_id) REFERENCES social.comunidad (id),
    CONSTRAINT bitacora_comunidad_accion_valida CHECK (accion IN (
        'creada', 'configurada', 'ingreso', 'salida', 'solicitud_aceptada', 'solicitud_rechazada',
        'papel_asignado', 'expulsion', 'publicacion_fijada', 'publicacion_desfijada', 'publicacion_retirada'))
);
CREATE INDEX bitacora_comunidad_idx ON social.bitacora_comunidad (comunidad_id, id DESC);
CREATE TRIGGER bitacora_comunidad_solo_insercion BEFORE UPDATE OR DELETE ON social.bitacora_comunidad
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
COMMENT ON TABLE social.bitacora_comunidad IS 'Registro de las acciones de administración y moderación. Solo inserción';

-- PUBLICACIONES EN UNA COMUNIDAD -------------------------------------------------------------
ALTER TABLE social.publicacion
    ADD COLUMN comunidad_id uuid,
    ADD COLUMN fijada_en timestamptz,
    ADD CONSTRAINT publicacion_comunidad_id_fkey FOREIGN KEY (comunidad_id) REFERENCES social.comunidad (id),
    ADD CONSTRAINT publicacion_fijada_en_comunidad CHECK (fijada_en IS NULL OR comunidad_id IS NOT NULL);
CREATE INDEX publicacion_comunidad_idx ON social.publicacion (comunidad_id, creado_en DESC) WHERE comunidad_id IS NOT NULL;

-- =============================================================================================
-- Funciones
-- =============================================================================================

-- ¿Puede esta persona hacer esto en esta comunidad? Una sola definición de los permisos.
CREATE FUNCTION social.puede(p_comunidad_id uuid, p_usuario_id uuid, p_accion text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT CASE p_accion
        WHEN 'ver' THEN c.privacidad = 'publica' OR i.papel IS NOT NULL
        WHEN 'publicar' THEN i.papel IS NOT NULL
        WHEN 'moderar' THEN i.papel IN ('moderador', 'administrador')
        WHEN 'gestionar_integrantes' THEN i.papel IN ('gestor', 'administrador')
        WHEN 'configurar' THEN i.papel = 'administrador'
        WHEN 'asignar_papeles' THEN i.papel = 'administrador'
        ELSE false END
    FROM social.comunidad c
    LEFT JOIN social.integrante i ON i.comunidad_id = c.id AND i.usuario_id = p_usuario_id
         AND social.rol_usuario(p_usuario_id) IS NOT NULL            -- solo cuentas activas
    WHERE c.id = p_comunidad_id;
$$;
COMMENT ON FUNCTION social.puede(uuid, uuid, text) IS 'Permisos dentro de una comunidad según el papel';

-- ¿Puede esta persona (o alguien sin sesión, NULL) ver esta publicación? La usan todas las lecturas.
CREATE FUNCTION social.puede_ver_publicacion(p_publicacion_id uuid, p_usuario_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT p.comunidad_id IS NULL OR coalesce(social.puede(p.comunidad_id, p_usuario_id, 'ver'), false)
    FROM social.publicacion p WHERE p.id = p_publicacion_id;
$$;
COMMENT ON FUNCTION social.puede_ver_publicacion(uuid, uuid) IS 'Visibilidad de una publicación (las de comunidades privadas, solo para integrantes)';

CREATE FUNCTION social.mi_papel(p_comunidad_id uuid, p_usuario_id uuid) RETURNS text
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT papel FROM social.integrante WHERE comunidad_id = p_comunidad_id AND usuario_id = p_usuario_id;
$$;

-- =============================================================================================
-- Triggers
-- =============================================================================================

-- Contador de integrantes.
CREATE FUNCTION social.contar_integrantes() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    UPDATE social.comunidad SET total_integrantes = total_integrantes + CASE TG_OP WHEN 'INSERT' THEN 1 ELSE -1 END
    WHERE id = coalesce(NEW.comunidad_id, OLD.comunidad_id);
    RETURN NULL;
END;
$$;
CREATE TRIGGER integrante_contar AFTER INSERT OR DELETE ON social.integrante
    FOR EACH ROW EXECUTE FUNCTION social.contar_integrantes();

-- Nunca sin administrador. Se bloquea la fila de la comunidad para que dos cambios simultáneos
-- (por ejemplo, dos administradores quitándose el papel a la vez) no la dejen vacía.
CREATE FUNCTION social.conservar_administrador() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF OLD.papel = 'administrador' AND (TG_OP = 'DELETE' OR NEW.papel <> 'administrador') THEN
        PERFORM 1 FROM social.comunidad WHERE id = OLD.comunidad_id FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM social.integrante
                       WHERE comunidad_id = OLD.comunidad_id AND papel = 'administrador' AND usuario_id <> OLD.usuario_id) THEN
            RAISE EXCEPTION 'ultimo_administrador: la comunidad debe conservar al menos un administrador';
        END IF;
    END IF;
    RETURN coalesce(NEW, OLD);
END;
$$;
CREATE TRIGGER integrante_conservar_administrador BEFORE UPDATE OF papel OR DELETE ON social.integrante
    FOR EACH ROW EXECUTE FUNCTION social.conservar_administrador();

-- Una publicación nueva entra a la comunidad indicada por el procedimiento (variable de la transacción)
-- o, si responde, hereda la de la publicación original. Solo publican sus integrantes, y lo de una
-- comunidad privada no se comparte fuera de ella.
CREATE FUNCTION social.publicacion_en_comunidad() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_original uuid;
BEGIN
    IF NEW.responde_a_id IS NOT NULL THEN
        SELECT comunidad_id INTO NEW.comunidad_id FROM social.publicacion WHERE id = NEW.responde_a_id;
    ELSE
        NEW.comunidad_id := nullif(current_setting('parrhesia.comunidad', true), '')::uuid;
    END IF;
    IF NEW.comunidad_id IS NOT NULL AND NOT coalesce(social.puede(NEW.comunidad_id, NEW.autor_id, 'publicar'), false) THEN
        RAISE EXCEPTION 'no_integrante: solo los integrantes publican en una comunidad';
    END IF;
    IF NEW.comparte_id IS NOT NULL THEN
        SELECT comunidad_id INTO v_original FROM social.publicacion WHERE id = NEW.comparte_id;
        IF v_original IS NOT NULL AND (SELECT privacidad FROM social.comunidad WHERE id = v_original) = 'privada' THEN
            RAISE EXCEPTION 'publicacion_privada: lo publicado en una comunidad privada no se comparte fuera de ella';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER publicacion_en_comunidad BEFORE INSERT ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION social.publicacion_en_comunidad();

-- La comunidad de una publicación no cambia.
CREATE FUNCTION social.comunidad_de_publicacion_fija() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NEW.comunidad_id IS DISTINCT FROM OLD.comunidad_id THEN
        RAISE EXCEPTION 'social.publicacion: la comunidad de una publicación no cambia';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER publicacion_comunidad_fija BEFORE UPDATE OF comunidad_id ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION social.comunidad_de_publicacion_fija();

-- Outbox (para el grafo, T11): en qué comunidad quedó una publicación, y altas y bajas de integrantes.
CREATE FUNCTION social.emitir_evento_comunidad() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF TG_TABLE_NAME = 'publicacion' THEN
        INSERT INTO social.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
        VALUES ('publicacion', NEW.id::text, 'publicacion_en_comunidad',
                jsonb_build_object('publicacion', NEW.id, 'comunidad', NEW.comunidad_id));
    ELSIF TG_TABLE_NAME = 'comunidad' THEN
        INSERT INTO social.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
        VALUES ('comunidad', NEW.id::text, CASE TG_OP WHEN 'INSERT' THEN 'comunidad_creada' ELSE 'comunidad_actualizada' END,
                jsonb_build_object('id', NEW.id, 'nombre', NEW.nombre, 'privacidad', NEW.privacidad, 'creada_en', NEW.creada_en));
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO social.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
        VALUES ('integrante', NEW.comunidad_id || ':' || NEW.usuario_id, 'integrante_agregado',
                jsonb_build_object('comunidad', NEW.comunidad_id, 'usuario', NEW.usuario_id, 'desde', NEW.desde));
    ELSE
        INSERT INTO social.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
        VALUES ('integrante', OLD.comunidad_id || ':' || OLD.usuario_id, 'integrante_quitado',
                jsonb_build_object('comunidad', OLD.comunidad_id, 'usuario', OLD.usuario_id));
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER publicacion_comunidad_salida AFTER INSERT ON social.publicacion
    FOR EACH ROW WHEN (NEW.comunidad_id IS NOT NULL) EXECUTE FUNCTION social.emitir_evento_comunidad();
CREATE TRIGGER comunidad_salida AFTER INSERT OR UPDATE OF nombre, privacidad ON social.comunidad
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento_comunidad();
CREATE TRIGGER integrante_salida AFTER INSERT OR DELETE ON social.integrante
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento_comunidad();

-- =============================================================================================
-- Procedimientos (toda escritura pasa por aquí; cada uno es una transacción)
-- =============================================================================================

CREATE PROCEDURE social.crear_comunidad(p_creador uuid, p_nombre text, p_descripcion text, p_reglas text,
                                        p_privacidad text, INOUT p_comunidad_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF social.rol_usuario(p_creador) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    INSERT INTO social.comunidad (nombre, descripcion, reglas, privacidad, creada_por)
    VALUES (trim(p_nombre), trim(p_descripcion), nullif(trim(p_reglas), ''), p_privacidad, p_creador)
    RETURNING id INTO p_comunidad_id;
    INSERT INTO social.integrante (comunidad_id, usuario_id, papel) VALUES (p_comunidad_id, p_creador, 'administrador');
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion) VALUES (p_comunidad_id, p_creador, 'creada');
END;
$$;

CREATE PROCEDURE social.configurar_comunidad(p_actor uuid, p_comunidad_id uuid, p_nombre text, p_descripcion text,
                                             p_reglas text, p_privacidad text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NOT coalesce(social.puede(p_comunidad_id, p_actor, 'configurar'), false) THEN
        RAISE EXCEPTION 'sin_permiso: solo un administrador configura la comunidad';
    END IF;
    UPDATE social.comunidad SET
        nombre = coalesce(trim(p_nombre), nombre),
        descripcion = coalesce(trim(p_descripcion), descripcion),
        reglas = CASE WHEN p_reglas IS NULL THEN reglas ELSE nullif(trim(p_reglas), '') END,
        privacidad = coalesce(p_privacidad, privacidad),
        actualizada_en = now()
    WHERE id = p_comunidad_id;
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, datos)
    VALUES (p_comunidad_id, p_actor, 'configurada',
            jsonb_strip_nulls(jsonb_build_object('nombre', p_nombre, 'privacidad', p_privacidad,
                                                 'descripcion', p_descripcion IS NOT NULL, 'reglas', p_reglas IS NOT NULL)));
END;
$$;

CREATE PROCEDURE social.fijar_imagen_comunidad(p_actor uuid, p_comunidad_id uuid, p_imagen text, INOUT p_anterior text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NOT coalesce(social.puede(p_comunidad_id, p_actor, 'configurar'), false) THEN
        RAISE EXCEPTION 'sin_permiso: solo un administrador cambia la imagen';
    END IF;
    SELECT imagen INTO p_anterior FROM social.comunidad WHERE id = p_comunidad_id FOR UPDATE;
    UPDATE social.comunidad SET imagen = p_imagen, actualizada_en = now() WHERE id = p_comunidad_id;
END;
$$;

-- Entrar: en una pública se entra de una vez; en una privada queda una solicitud pendiente.
-- Devuelve 'integrante', 'solicitud' o 'ya_integrante'.
CREATE PROCEDURE social.entrar_a_comunidad(p_usuario uuid, p_comunidad_id uuid, p_mensaje text, INOUT p_resultado text)
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_privacidad text;
BEGIN
    IF social.rol_usuario(p_usuario) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    SELECT privacidad INTO v_privacidad FROM social.comunidad WHERE id = p_comunidad_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'comunidad_inexistente: no existe esa comunidad';
    END IF;
    IF social.mi_papel(p_comunidad_id, p_usuario) IS NOT NULL THEN
        p_resultado := 'ya_integrante';
    ELSIF v_privacidad = 'publica' THEN
        INSERT INTO social.integrante (comunidad_id, usuario_id) VALUES (p_comunidad_id, p_usuario);
        INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, afectado_id) VALUES (p_comunidad_id, p_usuario, 'ingreso', p_usuario);
        p_resultado := 'integrante';
    ELSE
        INSERT INTO social.solicitud_ingreso (comunidad_id, usuario_id, mensaje)
        VALUES (p_comunidad_id, p_usuario, nullif(trim(p_mensaje), ''))
        ON CONFLICT (comunidad_id, usuario_id) WHERE estado = 'pendiente' DO NOTHING;
        p_resultado := 'solicitud';
    END IF;
END;
$$;

CREATE PROCEDURE social.resolver_solicitud(p_actor uuid, p_solicitud_id uuid, p_aceptar boolean, p_motivo text)
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    s social.solicitud_ingreso;
BEGIN
    SELECT * INTO s FROM social.solicitud_ingreso WHERE id = p_solicitud_id AND estado = 'pendiente' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'solicitud_no_pendiente: la solicitud no existe o ya fue resuelta';
    END IF;
    IF NOT coalesce(social.puede(s.comunidad_id, p_actor, 'gestionar_integrantes'), false) THEN
        RAISE EXCEPTION 'sin_permiso: solo quien gestiona integrantes resuelve solicitudes';
    END IF;
    UPDATE social.solicitud_ingreso
    SET estado = CASE WHEN p_aceptar THEN 'aceptada' ELSE 'rechazada' END,
        resuelta_por = p_actor, resuelta_en = now(), motivo = nullif(trim(p_motivo), '')
    WHERE id = p_solicitud_id;
    IF p_aceptar AND social.rol_usuario(s.usuario_id) IS NOT NULL THEN
        INSERT INTO social.integrante (comunidad_id, usuario_id) VALUES (s.comunidad_id, s.usuario_id) ON CONFLICT DO NOTHING;
    END IF;
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, afectado_id, motivo)
    VALUES (s.comunidad_id, p_actor, CASE WHEN p_aceptar THEN 'solicitud_aceptada' ELSE 'solicitud_rechazada' END,
            s.usuario_id, nullif(trim(p_motivo), ''));
END;
$$;

CREATE PROCEDURE social.salir_de_comunidad(p_usuario uuid, p_comunidad_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    DELETE FROM social.integrante WHERE comunidad_id = p_comunidad_id AND usuario_id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no_integrante: no perteneces a esta comunidad';
    END IF;
    UPDATE social.solicitud_ingreso SET estado = 'retirada', resuelta_en = now()
    WHERE comunidad_id = p_comunidad_id AND usuario_id = p_usuario AND estado = 'pendiente';
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, afectado_id) VALUES (p_comunidad_id, p_usuario, 'salida', p_usuario);
END;
$$;

-- Expulsar exige un motivo (queda en la bitácora). Un gestor no expulsa a gestores ni administradores.
CREATE PROCEDURE social.expulsar_de_comunidad(p_actor uuid, p_comunidad_id uuid, p_usuario uuid, p_motivo text)
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_papel_actor text := social.mi_papel(p_comunidad_id, p_actor);
    v_papel text := social.mi_papel(p_comunidad_id, p_usuario);
BEGIN
    IF NOT coalesce(social.puede(p_comunidad_id, p_actor, 'gestionar_integrantes'), false) THEN
        RAISE EXCEPTION 'sin_permiso: solo quien gestiona integrantes puede expulsar';
    END IF;
    IF v_papel IS NULL THEN
        RAISE EXCEPTION 'no_integrante: esa persona no pertenece a la comunidad';
    END IF;
    IF p_actor = p_usuario THEN
        RAISE EXCEPTION 'sin_permiso: para irte, usa salir de la comunidad';
    END IF;
    IF v_papel IN ('gestor', 'administrador') AND v_papel_actor <> 'administrador' THEN
        RAISE EXCEPTION 'sin_permiso: solo un administrador expulsa a gestores o administradores';
    END IF;
    IF length(trim(coalesce(p_motivo, ''))) < 10 THEN
        RAISE EXCEPTION 'motivo_requerido: expulsar exige un motivo de al menos 10 caracteres';
    END IF;
    DELETE FROM social.integrante WHERE comunidad_id = p_comunidad_id AND usuario_id = p_usuario;
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, afectado_id, motivo)
    VALUES (p_comunidad_id, p_actor, 'expulsion', p_usuario, trim(p_motivo));
END;
$$;

CREATE PROCEDURE social.asignar_papel(p_actor uuid, p_comunidad_id uuid, p_usuario uuid, p_papel text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NOT coalesce(social.puede(p_comunidad_id, p_actor, 'asignar_papeles'), false) THEN
        RAISE EXCEPTION 'sin_permiso: solo un administrador asigna papeles';
    END IF;
    UPDATE social.integrante SET papel = p_papel WHERE comunidad_id = p_comunidad_id AND usuario_id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no_integrante: esa persona no pertenece a la comunidad';
    END IF;
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, afectado_id, datos)
    VALUES (p_comunidad_id, p_actor, 'papel_asignado', p_usuario, jsonb_build_object('papel', p_papel));
END;
$$;

-- Publicar en una comunidad: el mismo social.publicar de siempre (etiquetas, menciones, outbox,
-- verificación), con la comunidad indicada solo para esta transacción.
CREATE PROCEDURE social.publicar_en_comunidad(p_autor uuid, p_comunidad_id uuid, p_texto text,
                                              p_figuras_ids uuid[], INOUT p_publicacion_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    PERFORM set_config('parrhesia.comunidad', p_comunidad_id::text, true);
    CALL social.publicar(p_autor, p_texto, NULL, NULL, p_figuras_ids, p_publicacion_id);
    PERFORM set_config('parrhesia.comunidad', '', true);
END;
$$;

-- Fijar (máximo 3 por comunidad) o desfijar.
CREATE PROCEDURE social.fijar_publicacion(p_actor uuid, p_publicacion_id uuid, p_fijar boolean)
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_comunidad uuid;
BEGIN
    SELECT comunidad_id INTO v_comunidad FROM social.publicacion WHERE id = p_publicacion_id AND estado = 'visible' FOR UPDATE;
    IF v_comunidad IS NULL THEN
        RAISE EXCEPTION 'publicacion_no_visible: solo se fijan publicaciones visibles de una comunidad';
    END IF;
    IF NOT coalesce(social.puede(v_comunidad, p_actor, 'moderar'), false) THEN
        RAISE EXCEPTION 'sin_permiso: solo quien modera puede fijar publicaciones';
    END IF;
    PERFORM 1 FROM social.comunidad WHERE id = v_comunidad FOR UPDATE;   -- el límite de 3 se revisa sin carreras
    IF p_fijar AND (SELECT count(*) FROM social.publicacion WHERE comunidad_id = v_comunidad AND fijada_en IS NOT NULL
                    AND id <> p_publicacion_id) >= 3 THEN
        RAISE EXCEPTION 'limite_fijadas: una comunidad puede fijar hasta 3 publicaciones';
    END IF;
    UPDATE social.publicacion SET fijada_en = CASE WHEN p_fijar THEN now() END WHERE id = p_publicacion_id;
    INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, publicacion_id)
    VALUES (v_comunidad, p_actor, CASE WHEN p_fijar THEN 'publicacion_fijada' ELSE 'publicacion_desfijada' END, p_publicacion_id);
END;
$$;

-- Retirar: el autor, un administrador de la plataforma o quien modera la comunidad de la publicación.
CREATE OR REPLACE PROCEDURE social.retirar_publicacion(p_publicacion_id uuid, p_actor_id uuid)
LANGUAGE plpgsql AS $$
DECLARE
    v_autor     uuid;
    v_comunidad uuid;
BEGIN
    SELECT autor_id, comunidad_id INTO v_autor, v_comunidad FROM social.publicacion
    WHERE id = p_publicacion_id AND estado = 'visible' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'publicacion_no_visible: la publicación no existe o ya fue retirada';
    END IF;
    IF p_actor_id = v_autor THEN
        UPDATE social.publicacion SET estado = 'retirada_por_autor', fijada_en = NULL WHERE id = p_publicacion_id;
    ELSIF social.rol_usuario(p_actor_id) = 'admin'
          OR (v_comunidad IS NOT NULL AND coalesce(social.puede(v_comunidad, p_actor_id, 'moderar'), false)) THEN
        UPDATE social.publicacion SET estado = 'retirada_por_moderacion', fijada_en = NULL WHERE id = p_publicacion_id;
        IF v_comunidad IS NOT NULL THEN
            INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, publicacion_id, afectado_id)
            VALUES (v_comunidad, p_actor_id, 'publicacion_retirada', p_publicacion_id, v_autor);
        END IF;
    ELSE
        RAISE EXCEPTION 'sin_permiso: solo el autor, un administrador o quien modera la comunidad pueden retirarla';
    END IF;
END;
$$;

-- La verificación no expone el texto de una publicación de una comunidad privada: su API pregunta antes.
GRANT EXECUTE ON FUNCTION social.puede_ver_publicacion(uuid, uuid) TO svc_verificacion;

GRANT SELECT, INSERT, UPDATE, DELETE ON social.comunidad, social.integrante, social.solicitud_ingreso TO svc_social;
GRANT SELECT, INSERT ON social.bitacora_comunidad TO svc_social;
GRANT USAGE ON SEQUENCE social.bitacora_comunidad_id_seq TO svc_social;
GRANT EXECUTE ON FUNCTION social.puede(uuid, uuid, text), social.puede_ver_publicacion(uuid, uuid), social.mi_papel(uuid, uuid)
    TO svc_social;
GRANT EXECUTE ON PROCEDURE social.crear_comunidad(uuid, text, text, text, text, uuid),
    social.configurar_comunidad(uuid, uuid, text, text, text, text), social.fijar_imagen_comunidad(uuid, uuid, text, text),
    social.entrar_a_comunidad(uuid, uuid, text, text), social.resolver_solicitud(uuid, uuid, boolean, text),
    social.salir_de_comunidad(uuid, uuid), social.expulsar_de_comunidad(uuid, uuid, uuid, text),
    social.asignar_papel(uuid, uuid, uuid, text), social.publicar_en_comunidad(uuid, uuid, text, uuid[], uuid),
    social.fijar_publicacion(uuid, uuid, boolean)
    TO svc_social;
