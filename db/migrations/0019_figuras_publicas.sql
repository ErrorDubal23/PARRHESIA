-- 0019 · Gestión de figuras públicas (segunda etapa, T10a).
--
-- Solo verificadores y administradores crean y editan figuras (evita fichas inventadas contra personas
-- privadas o cargos falsos). Cualquier persona puede proponer una, con fuente; un verificador la revisa.
-- Cada dato de la ficha lleva su fuente oficial: el cargo siempre; el partido solo si hay fuente, y nunca
-- se usa para agrupar, colorear ni contar lados. Cada cambio queda en una bitácora de solo inserción.

-- Nombre comparable: sin tildes, sin mayúsculas y sin espacios de sobra (igual que temas.buscar_figura).
CREATE FUNCTION util.nombre_comparable(p_nombre text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = '' AS $$
    SELECT regexp_replace(translate(lower(trim(p_nombre)), 'áéíóúüñ', 'aeiouun'), '\s+', ' ', 'g');
$$;

ALTER TABLE social.figura_publica
    ADD COLUMN url_fuente_cargo text,
    ADD COLUMN cargo_desde date,
    ADD COLUMN cargo_hasta date,
    ADD COLUMN url_fuente_partido text,
    ADD COLUMN foto text,
    ADD COLUMN estado text NOT NULL DEFAULT 'activa',
    ADD COLUMN creada_por uuid,
    ADD CONSTRAINT figura_publica_creada_por_fkey FOREIGN KEY (creada_por) REFERENCES social.usuario (id),
    ADD CONSTRAINT figura_publica_nombre_valido CHECK (length(trim(nombre_completo)) BETWEEN 3 AND 120),
    ADD CONSTRAINT figura_publica_url_cargo_valida CHECK (url_fuente_cargo ~ '^https://'),
    ADD CONSTRAINT figura_publica_url_partido_valida CHECK (url_fuente_partido ~ '^https://'),
    -- El partido es un dato público solo si se puede mostrar de dónde sale.
    ADD CONSTRAINT figura_publica_partido_con_fuente CHECK (partido IS NULL OR url_fuente_partido IS NOT NULL),
    ADD CONSTRAINT figura_publica_periodo_valido CHECK (cargo_hasta IS NULL OR cargo_desde IS NULL OR cargo_hasta >= cargo_desde),
    ADD CONSTRAINT figura_publica_foto_valida CHECK (foto ~ '^[0-9a-f]{32}\.webp$'),
    ADD CONSTRAINT figura_publica_estado_valido CHECK (estado IN ('activa', 'archivada'));
-- Dos fichas no pueden ser la misma persona escrita distinto ("Gustavo Petro" y "gustavo  petro").
CREATE UNIQUE INDEX figura_publica_nombre_comparable_key ON social.figura_publica (util.nombre_comparable(nombre_completo));
CREATE INDEX figura_publica_nombre_trgm ON social.figura_publica USING gin (util.nombre_comparable(nombre_completo) util.gin_trgm_ops);

-- BITÁCORA de la ficha: qué cambió, de qué valor a cuál, quién y cuándo. Solo inserción.
CREATE TABLE social.bitacora_figura (
    id          bigint      GENERATED ALWAYS AS IDENTITY,
    figura_id   uuid        NOT NULL,
    actor_id    uuid        NOT NULL,
    accion      text        NOT NULL,
    cambios     jsonb       NOT NULL DEFAULT '{}',
    motivo      text,
    creada_en   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bitacora_figura_pkey PRIMARY KEY (id),
    CONSTRAINT bitacora_figura_figura_id_fkey FOREIGN KEY (figura_id) REFERENCES social.figura_publica (id),
    CONSTRAINT bitacora_figura_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES social.usuario (id),
    CONSTRAINT bitacora_figura_accion_valida CHECK (accion IN ('creada', 'editada', 'archivada', 'reactivada', 'foto'))
);
CREATE INDEX bitacora_figura_idx ON social.bitacora_figura (figura_id, id DESC);
CREATE TRIGGER bitacora_figura_solo_insercion BEFORE UPDATE OR DELETE ON social.bitacora_figura
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
COMMENT ON TABLE social.bitacora_figura IS 'Cambios de cada ficha de figura pública (antes y después). Solo inserción';

-- PROPUESTA: cualquier persona sugiere una figura; un verificador la acepta (crea la ficha) o la rechaza.
CREATE TABLE social.propuesta_figura (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    propuesta_por    uuid        NOT NULL,
    nombre_completo  text        NOT NULL,
    cargo            text        NOT NULL,
    url_fuente       text        NOT NULL,
    nota             text,
    estado           text        NOT NULL DEFAULT 'pendiente',
    creada_en        timestamptz NOT NULL DEFAULT now(),
    resuelta_por     uuid,
    resuelta_en      timestamptz,
    motivo           text,
    figura_id        uuid,
    CONSTRAINT propuesta_figura_pkey PRIMARY KEY (id),
    CONSTRAINT propuesta_figura_propuesta_por_fkey FOREIGN KEY (propuesta_por) REFERENCES social.usuario (id),
    CONSTRAINT propuesta_figura_resuelta_por_fkey FOREIGN KEY (resuelta_por) REFERENCES social.usuario (id),
    CONSTRAINT propuesta_figura_figura_id_fkey FOREIGN KEY (figura_id) REFERENCES social.figura_publica (id),
    CONSTRAINT propuesta_figura_nombre_valido CHECK (length(trim(nombre_completo)) BETWEEN 3 AND 120),
    CONSTRAINT propuesta_figura_cargo_valido CHECK (length(trim(cargo)) BETWEEN 2 AND 160),
    CONSTRAINT propuesta_figura_url_valida CHECK (url_fuente ~ '^https://'),
    CONSTRAINT propuesta_figura_nota_valida CHECK (length(nota) <= 500),
    CONSTRAINT propuesta_figura_estado_valido CHECK (estado IN ('pendiente', 'aceptada', 'rechazada')),
    CONSTRAINT propuesta_figura_resolucion_coherente CHECK ((estado = 'pendiente') = (resuelta_en IS NULL)),
    CONSTRAINT propuesta_figura_aceptada_con_figura CHECK ((estado = 'aceptada') = (figura_id IS NOT NULL))
);
CREATE INDEX propuesta_figura_pendiente_idx ON social.propuesta_figura (creada_en) WHERE estado = 'pendiente';
CREATE TRIGGER propuesta_figura_transicion BEFORE UPDATE OF estado ON social.propuesta_figura
    FOR EACH ROW EXECUTE FUNCTION util.validar_transicion('{"pendiente": ["aceptada", "rechazada"]}');
COMMENT ON TABLE social.propuesta_figura IS 'Figura sugerida por una persona, pendiente de revisión';

-- =============================================================================================

CREATE FUNCTION social.puede_gestionar_figuras(p_usuario uuid) RETURNS boolean
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT coalesce(social.rol_usuario(p_usuario) IN ('verificador', 'admin'), false);
$$;

-- Fichas con nombre parecido, para avisar antes de crear un duplicado.
CREATE FUNCTION social.figuras_parecidas(p_nombre text)
RETURNS TABLE (id uuid, nombre_completo text, cargo text, parecido real)
LANGUAGE sql STABLE SET search_path = '' AS $$
    SELECT f.id, f.nombre_completo, f.cargo, util.similarity(util.nombre_comparable(f.nombre_completo), util.nombre_comparable(p_nombre))
    FROM social.figura_publica f
    WHERE length(trim(p_nombre)) >= 3
      AND util.similarity(util.nombre_comparable(f.nombre_completo), util.nombre_comparable(p_nombre)) > 0.35
    ORDER BY 4 DESC LIMIT 5;
$$;

CREATE PROCEDURE social.crear_figura(p_actor uuid, p_nombre text, p_cargo text, p_url_fuente_cargo text,
                                     p_cargo_desde date, p_cargo_hasta date, p_partido text, p_url_fuente_partido text,
                                     INOUT p_figura_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NOT social.puede_gestionar_figuras(p_actor) THEN
        RAISE EXCEPTION 'sin_permiso: solo verificadores y administradores registran figuras públicas';
    END IF;
    IF nullif(trim(p_cargo), '') IS NULL OR p_url_fuente_cargo IS NULL THEN
        RAISE EXCEPTION 'cargo_sin_fuente: el cargo y su fuente oficial son obligatorios';
    END IF;
    INSERT INTO social.figura_publica (nombre_completo, cargo, url_fuente_cargo, cargo_desde, cargo_hasta,
                                       partido, url_fuente_partido, creada_por)
    VALUES (regexp_replace(trim(p_nombre), '\s+', ' ', 'g'), trim(p_cargo), trim(p_url_fuente_cargo), p_cargo_desde, p_cargo_hasta,
            nullif(trim(p_partido), ''), CASE WHEN nullif(trim(p_partido), '') IS NULL THEN NULL ELSE trim(p_url_fuente_partido) END,
            p_actor)
    RETURNING id INTO p_figura_id;
    INSERT INTO social.bitacora_figura (figura_id, actor_id, accion, cambios)
    VALUES (p_figura_id, p_actor, 'creada', jsonb_build_object('nombre_completo', p_nombre, 'cargo', p_cargo));
END;
$$;

-- Editar: solo cambia lo que llega (NULL = no tocar; '' en partido lo quita). La bitácora guarda antes y después.
CREATE PROCEDURE social.editar_figura(p_actor uuid, p_figura_id uuid, p_nombre text, p_cargo text, p_url_fuente_cargo text,
                                      p_cargo_desde date, p_cargo_hasta date, p_partido text, p_url_fuente_partido text,
                                      p_estado text, p_motivo text)
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    antes social.figura_publica;
    despues social.figura_publica;
    v_cambios jsonb := '{}';
    v_campo text;
BEGIN
    IF NOT social.puede_gestionar_figuras(p_actor) THEN
        RAISE EXCEPTION 'sin_permiso: solo verificadores y administradores editan figuras públicas';
    END IF;
    SELECT * INTO antes FROM social.figura_publica WHERE id = p_figura_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'figura_inexistente: no existe esa figura pública';
    END IF;
    UPDATE social.figura_publica SET
        nombre_completo = coalesce(regexp_replace(trim(p_nombre), '\s+', ' ', 'g'), nombre_completo),
        cargo = coalesce(trim(p_cargo), cargo),
        url_fuente_cargo = coalesce(trim(p_url_fuente_cargo), url_fuente_cargo),
        cargo_desde = coalesce(p_cargo_desde, cargo_desde),
        cargo_hasta = coalesce(p_cargo_hasta, cargo_hasta),
        partido = CASE WHEN p_partido IS NULL THEN partido ELSE nullif(trim(p_partido), '') END,
        url_fuente_partido = CASE WHEN p_partido IS NULL THEN coalesce(trim(p_url_fuente_partido), url_fuente_partido)
                                  WHEN nullif(trim(p_partido), '') IS NULL THEN NULL
                                  ELSE coalesce(trim(p_url_fuente_partido), url_fuente_partido) END,
        estado = coalesce(p_estado, estado),
        actualizado_en = now()
    WHERE id = p_figura_id
    RETURNING * INTO despues;
    FOREACH v_campo IN ARRAY ARRAY['nombre_completo', 'cargo', 'url_fuente_cargo', 'cargo_desde', 'cargo_hasta',
                                   'partido', 'url_fuente_partido', 'estado'] LOOP
        IF to_jsonb(antes) -> v_campo IS DISTINCT FROM to_jsonb(despues) -> v_campo THEN
            v_cambios := v_cambios || jsonb_build_object(v_campo, jsonb_build_object('antes', to_jsonb(antes) -> v_campo,
                                                                                      'despues', to_jsonb(despues) -> v_campo));
        END IF;
    END LOOP;
    IF v_cambios <> '{}' THEN
        INSERT INTO social.bitacora_figura (figura_id, actor_id, accion, cambios, motivo)
        VALUES (p_figura_id, p_actor,
                CASE WHEN antes.estado <> despues.estado THEN (CASE despues.estado WHEN 'archivada' THEN 'archivada' ELSE 'reactivada' END)
                     ELSE 'editada' END,
                v_cambios, nullif(trim(p_motivo), ''));
    END IF;
END;
$$;

CREATE PROCEDURE social.fijar_foto_figura(p_actor uuid, p_figura_id uuid, p_foto text, INOUT p_anterior text)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF NOT social.puede_gestionar_figuras(p_actor) THEN
        RAISE EXCEPTION 'sin_permiso: solo verificadores y administradores cambian la foto';
    END IF;
    SELECT foto INTO p_anterior FROM social.figura_publica WHERE id = p_figura_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'figura_inexistente: no existe esa figura pública';
    END IF;
    UPDATE social.figura_publica SET foto = p_foto, actualizado_en = now() WHERE id = p_figura_id;
    INSERT INTO social.bitacora_figura (figura_id, actor_id, accion) VALUES (p_figura_id, p_actor, 'foto');
END;
$$;

CREATE PROCEDURE social.proponer_figura(p_usuario uuid, p_nombre text, p_cargo text, p_url_fuente text, p_nota text,
                                        INOUT p_propuesta_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF social.rol_usuario(p_usuario) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    IF EXISTS (SELECT 1 FROM social.figura_publica WHERE util.nombre_comparable(nombre_completo) = util.nombre_comparable(p_nombre)) THEN
        RAISE EXCEPTION 'figura_ya_registrada: esa figura pública ya tiene ficha';
    END IF;
    INSERT INTO social.propuesta_figura (propuesta_por, nombre_completo, cargo, url_fuente, nota)
    VALUES (p_usuario, trim(p_nombre), trim(p_cargo), trim(p_url_fuente), nullif(trim(p_nota), ''))
    RETURNING id INTO p_propuesta_id;
END;
$$;

-- Aceptar crea la ficha con el cargo y la fuente propuestos (el verificador puede completarla luego).
CREATE PROCEDURE social.resolver_propuesta_figura(p_actor uuid, p_propuesta_id uuid, p_aceptar boolean, p_motivo text,
                                                  INOUT p_figura_id uuid)
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    p social.propuesta_figura;
BEGIN
    IF NOT social.puede_gestionar_figuras(p_actor) THEN
        RAISE EXCEPTION 'sin_permiso: solo verificadores y administradores revisan propuestas';
    END IF;
    SELECT * INTO p FROM social.propuesta_figura WHERE id = p_propuesta_id AND estado = 'pendiente' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'propuesta_no_pendiente: la propuesta no existe o ya fue resuelta';
    END IF;
    IF p_aceptar THEN
        CALL social.crear_figura(p_actor, p.nombre_completo, p.cargo, p.url_fuente, NULL, NULL, NULL, NULL, p_figura_id);
    ELSIF length(trim(coalesce(p_motivo, ''))) < 5 THEN
        RAISE EXCEPTION 'motivo_requerido: rechazar una propuesta exige un motivo';
    END IF;
    UPDATE social.propuesta_figura
    SET estado = CASE WHEN p_aceptar THEN 'aceptada' ELSE 'rechazada' END,
        resuelta_por = p_actor, resuelta_en = now(), motivo = nullif(trim(p_motivo), ''), figura_id = p_figura_id
    WHERE id = p_propuesta_id;
END;
$$;

GRANT SELECT, INSERT, UPDATE ON social.propuesta_figura TO svc_social;
GRANT SELECT, INSERT ON social.bitacora_figura TO svc_social;
GRANT USAGE ON SEQUENCE social.bitacora_figura_id_seq TO svc_social;
GRANT EXECUTE ON FUNCTION util.nombre_comparable(text) TO svc_social, svc_temas;
GRANT EXECUTE ON FUNCTION social.puede_gestionar_figuras(uuid), social.figuras_parecidas(text) TO svc_social;
GRANT EXECUTE ON PROCEDURE social.crear_figura(uuid, text, text, text, date, date, text, text, uuid),
    social.editar_figura(uuid, uuid, text, text, text, date, date, text, text, text, text),
    social.fijar_foto_figura(uuid, uuid, text, text), social.proponer_figura(uuid, text, text, text, text, uuid),
    social.resolver_propuesta_figura(uuid, uuid, boolean, text, uuid)
    TO svc_social;
