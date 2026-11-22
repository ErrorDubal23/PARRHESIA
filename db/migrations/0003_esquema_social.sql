-- 0003: esquema social. La red social: usuarios, publicaciones, seguimientos,
-- reacciones, etiquetas, figuras públicas, declaraciones, tendencias y outbox.
--
-- Diseño: docs/diseno/02_MR.md y 05_logica_bd.md (decisiones 3, 4, 6, 7, 8, 10, 11, 16 y 18).
-- Las escrituras de la app pasan por procedimientos; los contadores y los eventos
-- del outbox los ponen triggers, así que se cumplen aunque alguien inserte a mano.

CREATE SCHEMA social;
COMMENT ON SCHEMA social IS 'Red social: usuarios, publicaciones, seguimientos, reacciones, etiquetas, figuras públicas y tendencias';

-- =============================================================================
-- PARTE 1 · Tablas
-- =============================================================================

-- USUARIO
CREATE TABLE social.usuario (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    nombre_usuario  text        NOT NULL,
    nombre_visible  text        NOT NULL,
    correo          text        NOT NULL,
    clave_hash      text        NOT NULL,
    rol             text        NOT NULL DEFAULT 'usuario',
    estado          text        NOT NULL DEFAULT 'activo',
    biografia       text,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT usuario_pkey PRIMARY KEY (id),
    CONSTRAINT usuario_nombre_usuario_key UNIQUE (nombre_usuario),
    CONSTRAINT usuario_correo_key UNIQUE (correo),                    -- guardado en minúsculas
    CONSTRAINT usuario_nombre_usuario_valido CHECK (nombre_usuario ~ '^[a-z0-9_]{3,30}$'),
    CONSTRAINT usuario_nombre_visible_valido CHECK (length(trim(nombre_visible)) BETWEEN 1 AND 60),
    CONSTRAINT usuario_correo_valido CHECK (correo ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    -- Solo se acepta una huella bcrypt o argon2id: nunca una contraseña en texto plano.
    CONSTRAINT usuario_clave_es_hash CHECK (clave_hash ~ '^\$(2[aby]\$|argon2id\$)'),
    CONSTRAINT usuario_rol_valido CHECK (rol IN ('usuario', 'verificador', 'admin')),
    CONSTRAINT usuario_estado_valido CHECK (estado IN ('activo', 'en_revision', 'suspendido')),
    CONSTRAINT usuario_biografia_valida CHECK (length(biografia) <= 280)
);
COMMENT ON TABLE social.usuario IS 'Cuenta de la red. Nunca guarda la contraseña ni un lado político';

-- SEGUIMIENTO: quién sigue a quién
CREATE TABLE social.seguimiento (
    seguidor_id  uuid        NOT NULL,
    seguido_id   uuid        NOT NULL,
    creado_en    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT seguimiento_pkey PRIMARY KEY (seguidor_id, seguido_id),
    CONSTRAINT seguimiento_no_a_si_mismo CHECK (seguidor_id <> seguido_id),
    CONSTRAINT seguimiento_seguidor_id_fkey FOREIGN KEY (seguidor_id) REFERENCES social.usuario (id),
    CONSTRAINT seguimiento_seguido_id_fkey FOREIGN KEY (seguido_id) REFERENCES social.usuario (id)
);
CREATE INDEX seguimiento_seguido_idx ON social.seguimiento (seguido_id);
COMMENT ON TABLE social.seguimiento IS 'Relación N:M de usuario consigo mismo';

-- PUBLICACION: original, respuesta o compartida
CREATE TABLE social.publicacion (
    id                 uuid        NOT NULL DEFAULT gen_random_uuid(),
    autor_id           uuid        NOT NULL,
    texto              text,
    responde_a_id      uuid,
    comparte_id        uuid,
    estado             text        NOT NULL DEFAULT 'visible',
    total_respuestas   integer     NOT NULL DEFAULT 0,
    total_compartidas  integer     NOT NULL DEFAULT 0,
    total_reacciones   integer     NOT NULL DEFAULT 0,
    creado_en          timestamptz NOT NULL DEFAULT now(),
    actualizado_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT publicacion_pkey PRIMARY KEY (id),
    CONSTRAINT publicacion_autor_id_fkey FOREIGN KEY (autor_id) REFERENCES social.usuario (id),
    CONSTRAINT publicacion_responde_a_id_fkey FOREIGN KEY (responde_a_id) REFERENCES social.publicacion (id),
    CONSTRAINT publicacion_comparte_id_fkey FOREIGN KEY (comparte_id) REFERENCES social.publicacion (id),
    CONSTRAINT publicacion_texto_valido CHECK (length(trim(texto)) BETWEEN 1 AND 500),
    -- Es respuesta, o compartida, o ninguna de las dos.
    CONSTRAINT publicacion_un_solo_origen CHECK (num_nonnulls(responde_a_id, comparte_id) <= 1),
    -- Solo una compartida puede no tener texto.
    CONSTRAINT publicacion_texto_o_compartida CHECK (texto IS NOT NULL OR comparte_id IS NOT NULL),
    CONSTRAINT publicacion_no_a_si_misma CHECK (responde_a_id <> id AND comparte_id <> id),
    CONSTRAINT publicacion_estado_valido CHECK (estado IN ('visible', 'retirada_por_autor', 'retirada_por_moderacion')),
    CONSTRAINT publicacion_totales_positivos CHECK (total_respuestas >= 0 AND total_compartidas >= 0 AND total_reacciones >= 0)
);
CREATE INDEX publicacion_autor_idx ON social.publicacion (autor_id, creado_en DESC);
CREATE INDEX publicacion_responde_a_idx ON social.publicacion (responde_a_id, creado_en);
CREATE INDEX publicacion_comparte_idx ON social.publicacion (comparte_id);
CREATE INDEX publicacion_reciente_idx ON social.publicacion (creado_en DESC);
COMMENT ON TABLE social.publicacion IS 'Opinión de un usuario. No se edita ni se borra: solo se retira (decisiones 6 y 11)';
COMMENT ON COLUMN social.publicacion.total_respuestas IS 'Desnormalizado a propósito (decisión 7); lo mantiene un trigger';

-- ETIQUETA (#hashtag) y su relación con las publicaciones
CREATE TABLE social.etiqueta (
    id         uuid        NOT NULL DEFAULT gen_random_uuid(),
    nombre     text        NOT NULL,
    creado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT etiqueta_pkey PRIMARY KEY (id),
    CONSTRAINT etiqueta_nombre_key UNIQUE (nombre),
    CONSTRAINT etiqueta_nombre_valido CHECK (nombre ~ '^[a-z0-9_áéíóúñü]{1,50}$')
);
COMMENT ON TABLE social.etiqueta IS 'Hashtag, en minúsculas y sin el #';

CREATE TABLE social.publicacion_etiqueta (
    publicacion_id  uuid NOT NULL,
    etiqueta_id     uuid NOT NULL,
    CONSTRAINT publicacion_etiqueta_pkey PRIMARY KEY (publicacion_id, etiqueta_id),
    CONSTRAINT publicacion_etiqueta_publicacion_id_fkey FOREIGN KEY (publicacion_id) REFERENCES social.publicacion (id),
    CONSTRAINT publicacion_etiqueta_etiqueta_id_fkey FOREIGN KEY (etiqueta_id) REFERENCES social.etiqueta (id)
);
CREATE INDEX publicacion_etiqueta_etiqueta_idx ON social.publicacion_etiqueta (etiqueta_id);

-- REACCION: una por usuario y publicación; se puede cambiar el tipo
CREATE TABLE social.reaccion (
    publicacion_id  uuid        NOT NULL,
    usuario_id      uuid        NOT NULL,
    tipo            text        NOT NULL,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reaccion_pkey PRIMARY KEY (publicacion_id, usuario_id),
    CONSTRAINT reaccion_publicacion_id_fkey FOREIGN KEY (publicacion_id) REFERENCES social.publicacion (id),
    CONSTRAINT reaccion_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id),
    -- Sin "no me gusta" (decisión 3).
    CONSTRAINT reaccion_tipo_valido CHECK (tipo IN ('me_gusta', 'util'))
);
CREATE INDEX reaccion_usuario_idx ON social.reaccion (usuario_id);

-- FIGURA_PUBLICA y sus DECLARACIONes
CREATE TABLE social.figura_publica (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    nombre_completo  text        NOT NULL,
    cargo            text,
    partido          text,                                       -- dato público (decisión 4)
    creado_en        timestamptz NOT NULL DEFAULT now(),
    actualizado_en   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT figura_publica_pkey PRIMARY KEY (id),
    CONSTRAINT figura_publica_nombre_completo_key UNIQUE (nombre_completo)
);
COMMENT ON TABLE social.figura_publica IS 'Figuras públicas de la v1 (10 a 15). Solo a ellas se les guarda partido, porque es público';

CREATE TABLE social.declaracion (
    id              uuid        NOT NULL DEFAULT gen_random_uuid(),
    figura_id       uuid        NOT NULL,
    texto           text        NOT NULL,
    dicha_el        date        NOT NULL,
    tipo            text        NOT NULL,
    url_fuente      text        NOT NULL,
    estado_promesa  text,
    registrada_por  uuid        NOT NULL,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT declaracion_pkey PRIMARY KEY (id),
    CONSTRAINT declaracion_figura_id_fkey FOREIGN KEY (figura_id) REFERENCES social.figura_publica (id),
    CONSTRAINT declaracion_registrada_por_fkey FOREIGN KEY (registrada_por) REFERENCES social.usuario (id),
    CONSTRAINT declaracion_texto_valido CHECK (length(trim(texto)) >= 1),
    CONSTRAINT declaracion_tipo_valido CHECK (tipo IN ('declaracion', 'promesa')),
    CONSTRAINT declaracion_url_valida CHECK (url_fuente ~ '^https?://'),
    CONSTRAINT declaracion_estado_promesa_valido
        CHECK (estado_promesa IN ('pendiente', 'en_curso', 'cumplida', 'no_cumplida')),
    -- Solo una promesa tiene estado de promesa.
    CONSTRAINT declaracion_estado_solo_en_promesa CHECK ((tipo = 'promesa') = (estado_promesa IS NOT NULL))
);
CREATE INDEX declaracion_figura_idx ON social.declaracion (figura_id, dicha_el DESC);
COMMENT ON TABLE social.declaracion IS 'Lo que dijo una figura pública, con su fuente. La registra un verificador o administrador';

CREATE TABLE social.declaracion_etiqueta (
    declaracion_id  uuid NOT NULL,
    etiqueta_id     uuid NOT NULL,
    CONSTRAINT declaracion_etiqueta_pkey PRIMARY KEY (declaracion_id, etiqueta_id),
    CONSTRAINT declaracion_etiqueta_declaracion_id_fkey FOREIGN KEY (declaracion_id) REFERENCES social.declaracion (id),
    CONSTRAINT declaracion_etiqueta_etiqueta_id_fkey FOREIGN KEY (etiqueta_id) REFERENCES social.etiqueta (id)
);
CREATE INDEX declaracion_etiqueta_etiqueta_idx ON social.declaracion_etiqueta (etiqueta_id);
COMMENT ON TABLE social.declaracion_etiqueta IS 'Temas de una declaración, para mostrarla en la página de la tendencia (decisión 16)';

-- Menciones en una publicación
CREATE TABLE social.mencion_figura (
    publicacion_id  uuid NOT NULL,
    figura_id       uuid NOT NULL,
    CONSTRAINT mencion_figura_pkey PRIMARY KEY (publicacion_id, figura_id),
    CONSTRAINT mencion_figura_publicacion_id_fkey FOREIGN KEY (publicacion_id) REFERENCES social.publicacion (id),
    CONSTRAINT mencion_figura_figura_id_fkey FOREIGN KEY (figura_id) REFERENCES social.figura_publica (id)
);

CREATE TABLE social.mencion_usuario (
    publicacion_id  uuid NOT NULL,
    usuario_id      uuid NOT NULL,
    CONSTRAINT mencion_usuario_pkey PRIMARY KEY (publicacion_id, usuario_id),
    CONSTRAINT mencion_usuario_publicacion_id_fkey FOREIGN KEY (publicacion_id) REFERENCES social.publicacion (id),
    CONSTRAINT mencion_usuario_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES social.usuario (id)
);

-- TENDENCIA: foto de cada ventana, calculada por el servicio de grafo
CREATE TABLE social.tendencia (
    id                   uuid        NOT NULL DEFAULT gen_random_uuid(),
    ventana_inicio       timestamptz NOT NULL,
    ventana_fin          timestamptz NOT NULL,
    etiqueta_id          uuid        NOT NULL,
    total_publicaciones  integer     NOT NULL,
    total_autores        integer     NOT NULL,
    diversidad           numeric     NOT NULL,
    puntaje              numeric     NOT NULL,
    posicion             smallint    NOT NULL,
    calculada_en         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tendencia_pkey PRIMARY KEY (id),
    CONSTRAINT tendencia_etiqueta_id_fkey FOREIGN KEY (etiqueta_id) REFERENCES social.etiqueta (id),
    CONSTRAINT tendencia_ventana_etiqueta_key UNIQUE (ventana_inicio, ventana_fin, etiqueta_id),
    CONSTRAINT tendencia_ventana_posicion_key UNIQUE (ventana_inicio, ventana_fin, posicion),
    CONSTRAINT tendencia_ventana_valida CHECK (ventana_fin > ventana_inicio),
    CONSTRAINT tendencia_diversidad_valida CHECK (diversidad BETWEEN 0 AND 1),
    CONSTRAINT tendencia_minimo_tres_autores CHECK (total_autores >= 3),        -- decisión 8
    CONSTRAINT tendencia_posicion_valida CHECK (posicion >= 1)
);
COMMENT ON TABLE social.tendencia IS 'Tendencias de cada ventana de tiempo; la historia queda guardada. Solo inserción';

-- EVENTO_SALIDA (transactional outbox) y ENTREGA_EVENTO (quién ya lo leyó)
CREATE TABLE social.evento_salida (
    id            bigint      GENERATED ALWAYS AS IDENTITY,
    tipo_entidad  text        NOT NULL,
    entidad_id    text        NOT NULL,
    tipo_evento   text        NOT NULL,
    datos         jsonb       NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT evento_salida_pkey PRIMARY KEY (id)
);
CREATE INDEX evento_salida_tipo_idx ON social.evento_salida (tipo_evento, id);
COMMENT ON TABLE social.evento_salida IS 'Outbox: cada cambio de la red queda como evento en la misma transacción. Solo inserción';

CREATE TABLE social.entrega_evento (
    evento_id     bigint      NOT NULL,
    consumidor    text        NOT NULL,
    entregado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT entrega_evento_pkey PRIMARY KEY (evento_id, consumidor),
    CONSTRAINT entrega_evento_evento_id_fkey FOREIGN KEY (evento_id) REFERENCES social.evento_salida (id),
    CONSTRAINT entrega_evento_consumidor_valido CHECK (consumidor IN ('grafo', 'verificacion'))
);
COMMENT ON TABLE social.entrega_evento IS 'Qué consumidor ya procesó cada evento (decisión 18). Solo inserción';

-- =============================================================================
-- PARTE 2 · Funciones
-- =============================================================================

-- #etiquetas de un texto: en minúsculas, sin repetir, en orden de aparición, máximo 10.
CREATE FUNCTION social.extraer_etiquetas(p_texto text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(array_agg(etiqueta ORDER BY posicion), '{}')
    FROM (
        SELECT etiqueta, min(posicion) AS posicion
        FROM (
            SELECT lower(m[1]) AS etiqueta, n AS posicion
            FROM regexp_matches(coalesce(p_texto, ''), '#([[:alnum:]_]+)', 'g') WITH ORDINALITY AS r(m, n)
        ) AS todas
        WHERE etiqueta ~ '^[a-z0-9_áéíóúñü]{1,50}$'
        GROUP BY etiqueta
        ORDER BY min(posicion)
        LIMIT 10
    ) AS primeras;
$$;
COMMENT ON FUNCTION social.extraer_etiquetas(text) IS 'Las #etiquetas de un texto, en minúsculas y sin repetir (máximo 10)';

-- @menciones de un texto, con las mismas reglas.
CREATE FUNCTION social.extraer_menciones(p_texto text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(array_agg(nombre ORDER BY posicion), '{}')
    FROM (
        SELECT nombre, min(posicion) AS posicion
        FROM (
            SELECT lower(m[1]) AS nombre, n AS posicion
            FROM regexp_matches(coalesce(p_texto, ''), '(?:^|[^[:alnum:]_])@([A-Za-z0-9_]{3,30})', 'g')
                 WITH ORDINALITY AS r(m, n)
        ) AS todas
        GROUP BY nombre
        ORDER BY min(posicion)
        LIMIT 10
    ) AS primeras;
$$;
COMMENT ON FUNCTION social.extraer_menciones(text) IS 'Los @usuarios mencionados en un texto, en minúsculas y sin repetir (máximo 10)';

-- Hilo de respuestas, recursivo. Las retiradas conservan su lugar en el árbol.
CREATE FUNCTION social.hilo(p_publicacion_id uuid)
RETURNS TABLE (id uuid, responde_a_id uuid, autor_id uuid, profundidad int, ruta uuid[], estado text, creado_en timestamptz)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE arbol AS (
        SELECT p.id, p.responde_a_id, p.autor_id, 0 AS profundidad, ARRAY[p.id] AS ruta, p.estado, p.creado_en
        FROM social.publicacion p
        WHERE p.id = p_publicacion_id
        UNION ALL
        SELECT r.id, r.responde_a_id, r.autor_id, a.profundidad + 1, a.ruta || r.id, r.estado, r.creado_en
        FROM social.publicacion r
        JOIN arbol a ON r.responde_a_id = a.id
        WHERE a.profundidad < 50
    )
    SELECT * FROM arbol ORDER BY ruta;
$$;
COMMENT ON FUNCTION social.hilo(uuid) IS 'Árbol completo de respuestas de una publicación (WITH RECURSIVE), en orden de lectura';

CREATE FUNCTION social.estadisticas_usuario(p_usuario_id uuid)
RETURNS TABLE (seguidores bigint, seguidos bigint, publicaciones bigint)
LANGUAGE sql STABLE AS $$
    SELECT (SELECT count(*) FROM social.seguimiento WHERE seguido_id = p_usuario_id),
           (SELECT count(*) FROM social.seguimiento WHERE seguidor_id = p_usuario_id),
           (SELECT count(*) FROM social.publicacion WHERE autor_id = p_usuario_id AND estado = 'visible');
$$;
COMMENT ON FUNCTION social.estadisticas_usuario(uuid) IS 'Seguidores, seguidos y publicaciones visibles de un usuario';

-- Respaldo cuando Neo4j no está: etiquetas por autores distintos, sin diversidad.
-- Mismas reglas que las tendencias del grafo (decisión 8).
CREATE FUNCTION social.tendencias_basicas(p_desde timestamptz, p_hasta timestamptz)
RETURNS TABLE (etiqueta text, total_publicaciones bigint, total_autores bigint)
LANGUAGE sql STABLE AS $$
    SELECT e.nombre, count(DISTINCT p.id), count(DISTINCT p.autor_id)
    FROM social.etiqueta e
    JOIN social.publicacion_etiqueta pe ON pe.etiqueta_id = e.id
    JOIN social.publicacion p ON p.id = pe.publicacion_id
    JOIN social.usuario u ON u.id = p.autor_id
    WHERE p.creado_en >= p_desde AND p.creado_en < p_hasta
      AND p.estado = 'visible'
      AND u.estado = 'activo'
      AND u.creado_en < p_desde - interval '7 days'          -- las cuentas nuevas no cuentan
    GROUP BY e.nombre
    HAVING count(DISTINCT p.autor_id) >= 3
    ORDER BY count(DISTINCT p.autor_id) DESC, count(DISTINCT p.id) DESC, e.nombre
    LIMIT 10;
$$;
COMMENT ON FUNCTION social.tendencias_basicas(timestamptz, timestamptz)
    IS 'Tendencias sin diversidad, para cuando el grafo no está disponible';

-- Lo que alimenta la página de una tendencia (decisión 16): declaraciones ligadas
-- a la etiqueta y publicaciones visibles de la ventana. Las conclusiones las agrega
-- el servicio de verificación.
CREATE FUNCTION social.contenido_tendencia(p_etiqueta text, p_desde timestamptz, p_hasta timestamptz)
RETURNS TABLE (tipo text, id uuid, fecha timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT 'declaracion', d.id, d.dicha_el::timestamptz
    FROM social.declaracion d
    JOIN social.declaracion_etiqueta de ON de.declaracion_id = d.id
    JOIN social.etiqueta e ON e.id = de.etiqueta_id
    WHERE e.nombre = lower(p_etiqueta)
    UNION ALL
    SELECT 'publicacion', p.id, p.creado_en
    FROM social.publicacion p
    JOIN social.publicacion_etiqueta pe ON pe.publicacion_id = p.id
    JOIN social.etiqueta e ON e.id = pe.etiqueta_id
    WHERE e.nombre = lower(p_etiqueta) AND p.estado = 'visible'
      AND p.creado_en >= p_desde AND p.creado_en < p_hasta
    ORDER BY 1, 3 DESC;
$$;
COMMENT ON FUNCTION social.contenido_tendencia(text, timestamptz, timestamptz)
    IS 'Declaraciones y publicaciones de una etiqueta, para la página de la tendencia';

-- Eventos que un consumidor todavía no ha procesado, en orden (decisión 18).
CREATE FUNCTION social.eventos_pendientes(p_consumidor text, p_tipos text[], p_limite int DEFAULT 100)
RETURNS SETOF social.evento_salida
LANGUAGE sql STABLE AS $$
    SELECT e.* FROM social.evento_salida e
    WHERE e.tipo_evento = ANY (p_tipos)
      AND NOT EXISTS (SELECT 1 FROM social.entrega_evento d
                      WHERE d.evento_id = e.id AND d.consumidor = p_consumidor)
    ORDER BY e.id
    LIMIT p_limite;
$$;
COMMENT ON FUNCTION social.eventos_pendientes(text, text[], int) IS 'Eventos del outbox que un consumidor aún no ha procesado';

-- Para los triggers de otros esquemas (verificacion, temas). SECURITY DEFINER:
-- responden sin dar permiso de leer las tablas de social.
CREATE FUNCTION social.publicacion_existe(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM social.publicacion WHERE id = p_id);
$$;
CREATE FUNCTION social.declaracion_existe(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM social.declaracion WHERE id = p_id);
$$;
CREATE FUNCTION social.figura_existe(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM social.figura_publica WHERE id = p_id);
$$;
CREATE FUNCTION social.rol_usuario(p_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT rol FROM social.usuario WHERE id = p_id AND estado = 'activo';
$$;
-- El servicio de verificación lee el texto que va a revisar (el outbox no lo lleva).
CREATE FUNCTION social.texto_para_verificar(p_tipo text, p_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT CASE p_tipo
        WHEN 'publicacion' THEN (SELECT texto FROM social.publicacion WHERE id = p_id AND estado = 'visible')
        WHEN 'declaracion' THEN (SELECT texto FROM social.declaracion WHERE id = p_id)
    END;
$$;
COMMENT ON FUNCTION social.texto_para_verificar(text, uuid) IS 'Texto de una publicación visible o de una declaración, para el servicio de verificación';

-- =============================================================================
-- PARTE 3 · Procedimientos
-- =============================================================================

CREATE PROCEDURE social.registrar_usuario(
    p_nombre_usuario text, p_nombre_visible text, p_correo text, p_clave_hash text, INOUT p_usuario_id uuid)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO social.usuario (nombre_usuario, nombre_visible, correo, clave_hash)
    VALUES (p_nombre_usuario, p_nombre_visible, p_correo, p_clave_hash)
    RETURNING id INTO p_usuario_id;
END;
$$;
COMMENT ON PROCEDURE social.registrar_usuario(text, text, text, text, uuid)
    IS 'Crea una cuenta; los duplicados los rechazan las restricciones únicas';

-- Publicar: la publicación, sus etiquetas y sus menciones, todo o nada.
-- Los contadores y los eventos del outbox los ponen los triggers.
CREATE PROCEDURE social.publicar(
    p_autor_id uuid, p_texto text, p_responde_a_id uuid, p_comparte_id uuid,
    p_figuras_ids uuid[], INOUT p_publicacion_id uuid)
LANGUAGE plpgsql AS $$
DECLARE
    v_etiqueta text;
BEGIN
    PERFORM 1 FROM social.usuario WHERE id = p_autor_id AND estado = 'activo';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'autor_inactivo: la cuenta no existe o no está activa';
    END IF;

    -- No se responde ni se comparte una publicación retirada. FOR SHARE impide que
    -- la retiren mientras esta transacción la está usando.
    IF p_responde_a_id IS NOT NULL OR p_comparte_id IS NOT NULL THEN
        PERFORM 1 FROM social.publicacion
        WHERE id = coalesce(p_responde_a_id, p_comparte_id) AND estado = 'visible'
        FOR SHARE;
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
$$;
COMMENT ON PROCEDURE social.publicar(uuid, text, uuid, uuid, uuid[], uuid)
    IS 'Publica, responde o comparte, con etiquetas y menciones, en una sola transacción';

CREATE PROCEDURE social.retirar_publicacion(p_publicacion_id uuid, p_actor_id uuid)
LANGUAGE plpgsql AS $$
DECLARE
    v_autor uuid;
    v_rol   text;
BEGIN
    SELECT autor_id INTO v_autor FROM social.publicacion
    WHERE id = p_publicacion_id AND estado = 'visible' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'publicacion_no_visible: la publicación no existe o ya fue retirada';
    END IF;
    v_rol := social.rol_usuario(p_actor_id);
    IF p_actor_id = v_autor THEN
        UPDATE social.publicacion SET estado = 'retirada_por_autor' WHERE id = p_publicacion_id;
    ELSIF v_rol = 'admin' THEN
        UPDATE social.publicacion SET estado = 'retirada_por_moderacion' WHERE id = p_publicacion_id;
    ELSE
        RAISE EXCEPTION 'sin_permiso: solo el autor o un administrador pueden retirar la publicación';
    END IF;
END;
$$;
COMMENT ON PROCEDURE social.retirar_publicacion(uuid, uuid) IS 'Retira una publicación (no se borra: decisión 6)';

CREATE PROCEDURE social.seguir(p_seguidor_id uuid, p_seguido_id uuid)
LANGUAGE plpgsql AS $$
BEGIN
    IF social.rol_usuario(p_seguidor_id) IS NULL OR social.rol_usuario(p_seguido_id) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: las dos cuentas deben existir y estar activas';
    END IF;
    -- Seguir dos veces no es un error ni crea un segundo evento.
    INSERT INTO social.seguimiento (seguidor_id, seguido_id) VALUES (p_seguidor_id, p_seguido_id)
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE PROCEDURE social.dejar_de_seguir(p_seguidor_id uuid, p_seguido_id uuid)
LANGUAGE sql AS $$
    DELETE FROM social.seguimiento WHERE seguidor_id = p_seguidor_id AND seguido_id = p_seguido_id;
$$;

CREATE PROCEDURE social.reaccionar(p_publicacion_id uuid, p_usuario_id uuid, p_tipo text)
LANGUAGE plpgsql AS $$
BEGIN
    IF social.rol_usuario(p_usuario_id) IS NULL THEN
        RAISE EXCEPTION 'usuario_inactivo: la cuenta no existe o no está activa';
    END IF;
    PERFORM 1 FROM social.publicacion WHERE id = p_publicacion_id AND estado = 'visible' FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'publicacion_no_visible: la publicación no existe o fue retirada';
    END IF;
    -- Cambiar de "me gusta" a "útil" actualiza la misma fila: no suma dos reacciones.
    INSERT INTO social.reaccion (publicacion_id, usuario_id, tipo) VALUES (p_publicacion_id, p_usuario_id, p_tipo)
    ON CONFLICT (publicacion_id, usuario_id) DO UPDATE SET tipo = EXCLUDED.tipo
        WHERE social.reaccion.tipo IS DISTINCT FROM EXCLUDED.tipo;
END;
$$;

CREATE PROCEDURE social.quitar_reaccion(p_publicacion_id uuid, p_usuario_id uuid)
LANGUAGE sql AS $$
    DELETE FROM social.reaccion WHERE publicacion_id = p_publicacion_id AND usuario_id = p_usuario_id;
$$;

-- Declaración de una figura pública con sus temas. Solo verificadores y administradores.
CREATE PROCEDURE social.registrar_declaracion(
    p_registrada_por uuid, p_figura_id uuid, p_texto text, p_dicha_el date, p_tipo text,
    p_url_fuente text, p_etiquetas text[], INOUT p_declaracion_id uuid)
LANGUAGE plpgsql AS $$
DECLARE
    v_etiqueta text;
BEGIN
    IF coalesce(social.rol_usuario(p_registrada_por), '') NOT IN ('verificador', 'admin') THEN
        RAISE EXCEPTION 'sin_permiso: solo un verificador o un administrador registra declaraciones';
    END IF;
    INSERT INTO social.declaracion (figura_id, texto, dicha_el, tipo, url_fuente, estado_promesa, registrada_por)
    VALUES (p_figura_id, p_texto, p_dicha_el, p_tipo, p_url_fuente,
            CASE WHEN p_tipo = 'promesa' THEN 'pendiente' END, p_registrada_por)
    RETURNING id INTO p_declaracion_id;

    FOREACH v_etiqueta IN ARRAY coalesce(p_etiquetas, '{}') LOOP
        v_etiqueta := lower(ltrim(trim(v_etiqueta), '#'));
        INSERT INTO social.etiqueta (nombre) VALUES (v_etiqueta) ON CONFLICT (nombre) DO NOTHING;
        INSERT INTO social.declaracion_etiqueta (declaracion_id, etiqueta_id)
        SELECT p_declaracion_id, e.id FROM social.etiqueta e WHERE e.nombre = v_etiqueta
        ON CONFLICT DO NOTHING;
    END LOOP;
END;
$$;
COMMENT ON PROCEDURE social.registrar_declaracion(uuid, uuid, text, date, text, text, text[], uuid)
    IS 'Registra lo que dijo una figura pública, con su fuente y sus temas';

-- La llama el servicio de grafo: todas las filas de una ventana, o ninguna.
-- filas: [{"etiqueta": "...", "total_publicaciones": n, "total_autores": n,
--          "diversidad": 0.8, "puntaje": 4.0, "posicion": 1}, ...]
CREATE PROCEDURE social.registrar_tendencias(p_ventana_inicio timestamptz, p_ventana_fin timestamptz, p_filas jsonb)
LANGUAGE plpgsql AS $$
DECLARE
    v_insertadas int;
BEGIN
    INSERT INTO social.tendencia (ventana_inicio, ventana_fin, etiqueta_id, total_publicaciones, total_autores,
                                  diversidad, puntaje, posicion)
    SELECT p_ventana_inicio, p_ventana_fin, e.id, (f->>'total_publicaciones')::int, (f->>'total_autores')::int,
           (f->>'diversidad')::numeric, (f->>'puntaje')::numeric, (f->>'posicion')::smallint
    FROM jsonb_array_elements(p_filas) AS f
    JOIN social.etiqueta e ON e.nombre = f->>'etiqueta';
    GET DIAGNOSTICS v_insertadas = ROW_COUNT;
    IF v_insertadas <> jsonb_array_length(p_filas) THEN
        RAISE EXCEPTION 'etiqueta_desconocida: alguna fila de la ventana no corresponde a una etiqueta existente';
    END IF;
END;
$$;

-- Un consumidor marca como procesados los eventos que ya aplicó.
CREATE PROCEDURE social.marcar_entregados(p_consumidor text, p_eventos bigint[])
LANGUAGE sql AS $$
    INSERT INTO social.entrega_evento (evento_id, consumidor)
    SELECT unnest(p_eventos), p_consumidor
    ON CONFLICT DO NOTHING;
$$;

-- =============================================================================
-- PARTE 4 · Triggers
-- =============================================================================

-- Correo y nombre de usuario siempre en minúsculas; id, nombre de usuario y fecha de
-- creación no cambian.
CREATE FUNCTION social.usuario_normalizar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.correo := lower(trim(NEW.correo));
    NEW.nombre_usuario := lower(trim(NEW.nombre_usuario));
    IF TG_OP = 'UPDATE' AND (NEW.id, NEW.nombre_usuario, NEW.creado_en) IS DISTINCT FROM (OLD.id, OLD.nombre_usuario, OLD.creado_en) THEN
        RAISE EXCEPTION 'social.usuario: el id, el nombre de usuario y la fecha de creación no cambian';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER usuario_normalizar BEFORE INSERT OR UPDATE ON social.usuario
    FOR EACH ROW EXECUTE FUNCTION social.usuario_normalizar();

-- Una publicación no se edita (decisión 11): solo cambia su estado y sus contadores.
CREATE FUNCTION social.publicacion_cambios_permitidos() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id, NEW.autor_id, NEW.texto, NEW.responde_a_id, NEW.comparte_id, NEW.creado_en)
       IS DISTINCT FROM (OLD.id, OLD.autor_id, OLD.texto, OLD.responde_a_id, OLD.comparte_id, OLD.creado_en) THEN
        RAISE EXCEPTION 'social.publicacion: una publicación no se edita; solo se puede retirar';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER publicacion_cambios_permitidos BEFORE UPDATE ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION social.publicacion_cambios_permitidos();
CREATE TRIGGER publicacion_transicion BEFORE UPDATE OF estado ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION util.validar_transicion(
        '{"visible": ["retirada_por_autor", "retirada_por_moderacion"]}');
CREATE TRIGGER publicacion_sin_borrado BEFORE DELETE ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- Una declaración solo puede cambiar el estado de su promesa.
CREATE FUNCTION social.declaracion_cambios_permitidos() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id, NEW.figura_id, NEW.texto, NEW.dicha_el, NEW.tipo, NEW.url_fuente, NEW.registrada_por, NEW.creado_en)
       IS DISTINCT FROM (OLD.id, OLD.figura_id, OLD.texto, OLD.dicha_el, OLD.tipo, OLD.url_fuente, OLD.registrada_por, OLD.creado_en) THEN
        RAISE EXCEPTION 'social.declaracion: solo puede cambiar el estado de la promesa';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER declaracion_cambios_permitidos BEFORE UPDATE ON social.declaracion
    FOR EACH ROW EXECUTE FUNCTION social.declaracion_cambios_permitidos();
CREATE TRIGGER declaracion_sin_borrado BEFORE DELETE ON social.declaracion
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- Contadores (decisión 7). Cuentan solo publicaciones visibles: suman al crear y
-- restan al retirar. Van en la misma transacción que el cambio que los causa.
CREATE FUNCTION social.publicacion_contadores() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    delta int := CASE WHEN TG_OP = 'INSERT' THEN 1 ELSE -1 END;
BEGIN
    IF TG_OP = 'UPDATE' AND NOT (OLD.estado = 'visible' AND NEW.estado <> 'visible') THEN
        RETURN NULL;
    END IF;
    IF NEW.responde_a_id IS NOT NULL THEN
        UPDATE social.publicacion SET total_respuestas = total_respuestas + delta WHERE id = NEW.responde_a_id;
    ELSIF NEW.comparte_id IS NOT NULL THEN
        UPDATE social.publicacion SET total_compartidas = total_compartidas + delta WHERE id = NEW.comparte_id;
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER publicacion_contadores AFTER INSERT OR UPDATE OF estado ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION social.publicacion_contadores();

CREATE FUNCTION social.reaccion_contadores() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE social.publicacion SET total_reacciones = total_reacciones + 1 WHERE id = NEW.publicacion_id;
    ELSE
        UPDATE social.publicacion SET total_reacciones = total_reacciones - 1 WHERE id = OLD.publicacion_id;
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER reaccion_contadores AFTER INSERT OR DELETE ON social.reaccion
    FOR EACH ROW EXECUTE FUNCTION social.reaccion_contadores();

-- actualizado_en
CREATE TRIGGER usuario_actualizado BEFORE UPDATE ON social.usuario
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER publicacion_actualizado BEFORE UPDATE ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER reaccion_actualizado BEFORE UPDATE ON social.reaccion
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();
CREATE TRIGGER figura_publica_actualizado BEFORE UPDATE ON social.figura_publica
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();

-- Solo inserción
CREATE TRIGGER tendencia_solo_insercion BEFORE UPDATE OR DELETE ON social.tendencia
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER evento_salida_solo_insercion BEFORE UPDATE OR DELETE ON social.evento_salida
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER entrega_evento_solo_insercion BEFORE UPDATE OR DELETE ON social.entrega_evento
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- Outbox: un trigger por tabla escribe el evento en la misma transacción. Nunca
-- lleva el correo, la contraseña ni el texto: el grafo no los necesita.
CREATE FUNCTION social.emitir_evento() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_tipo_entidad text;
    v_entidad      text;
    v_evento       text;
    v_datos        jsonb;
BEGIN
    CASE TG_TABLE_NAME
    WHEN 'usuario' THEN
        IF TG_OP = 'UPDATE' AND OLD.estado IS NOT DISTINCT FROM NEW.estado THEN
            RETURN NULL;
        END IF;
        v_tipo_entidad := 'usuario'; v_entidad := NEW.id::text;
        v_evento := CASE TG_OP WHEN 'INSERT' THEN 'usuario_creado' ELSE 'usuario_cambio_estado' END;
        v_datos := jsonb_build_object('id', NEW.id, 'nombre_usuario', NEW.nombre_usuario,
                                      'estado', NEW.estado, 'creado_en', NEW.creado_en);
    WHEN 'seguimiento' THEN
        v_tipo_entidad := 'seguimiento';
        IF TG_OP = 'INSERT' THEN
            v_evento := 'seguimiento_creado';
            v_entidad := NEW.seguidor_id || ':' || NEW.seguido_id;
            v_datos := jsonb_build_object('seguidor', NEW.seguidor_id, 'seguido', NEW.seguido_id, 'en', NEW.creado_en);
        ELSE
            v_evento := 'seguimiento_borrado';
            v_entidad := OLD.seguidor_id || ':' || OLD.seguido_id;
            v_datos := jsonb_build_object('seguidor', OLD.seguidor_id, 'seguido', OLD.seguido_id, 'en', now());
        END IF;
    WHEN 'publicacion' THEN
        IF TG_OP = 'UPDATE' AND OLD.estado IS NOT DISTINCT FROM NEW.estado THEN
            RETURN NULL;
        END IF;
        v_tipo_entidad := 'publicacion'; v_entidad := NEW.id::text;
        IF TG_OP = 'INSERT' THEN
            v_evento := 'publicacion_creada';
            v_datos := jsonb_build_object('id', NEW.id, 'autor', NEW.autor_id, 'responde_a', NEW.responde_a_id,
                                          'comparte', NEW.comparte_id, 'creado_en', NEW.creado_en);
        ELSE
            v_evento := 'publicacion_retirada';
            v_datos := jsonb_build_object('id', NEW.id, 'estado', NEW.estado);
        END IF;
    WHEN 'publicacion_etiqueta' THEN
        v_tipo_entidad := 'publicacion'; v_entidad := NEW.publicacion_id::text; v_evento := 'publicacion_etiquetada';
        v_datos := jsonb_build_object('publicacion', NEW.publicacion_id,
                                      'etiqueta', (SELECT nombre FROM social.etiqueta WHERE id = NEW.etiqueta_id));
    WHEN 'mencion_usuario' THEN
        v_tipo_entidad := 'publicacion'; v_entidad := NEW.publicacion_id::text; v_evento := 'publicacion_menciona';
        v_datos := jsonb_build_object('publicacion', NEW.publicacion_id, 'tipo_destino', 'usuario',
                                      'destino_id', NEW.usuario_id);
    WHEN 'mencion_figura' THEN
        v_tipo_entidad := 'publicacion'; v_entidad := NEW.publicacion_id::text; v_evento := 'publicacion_menciona';
        v_datos := jsonb_build_object('publicacion', NEW.publicacion_id, 'tipo_destino', 'figura',
                                      'destino_id', NEW.figura_id);
    WHEN 'reaccion' THEN
        v_tipo_entidad := 'reaccion';
        IF TG_OP = 'DELETE' THEN
            v_entidad := OLD.publicacion_id || ':' || OLD.usuario_id; v_evento := 'reaccion_quitada';
            v_datos := jsonb_build_object('publicacion', OLD.publicacion_id, 'usuario', OLD.usuario_id, 'en', now());
        ELSE
            v_entidad := NEW.publicacion_id || ':' || NEW.usuario_id; v_evento := 'reaccion_puesta';
            v_datos := jsonb_build_object('publicacion', NEW.publicacion_id, 'usuario', NEW.usuario_id,
                                          'tipo', NEW.tipo, 'en', now());
        END IF;
    WHEN 'figura_publica' THEN
        v_tipo_entidad := 'figura'; v_entidad := NEW.id::text; v_evento := 'figura_creada';
        v_datos := jsonb_build_object('id', NEW.id, 'nombre_completo', NEW.nombre_completo);
    WHEN 'declaracion' THEN
        v_tipo_entidad := 'declaracion'; v_entidad := NEW.id::text; v_evento := 'declaracion_creada';
        v_datos := jsonb_build_object('id', NEW.id, 'figura', NEW.figura_id, 'dicha_el', NEW.dicha_el);
    END CASE;

    INSERT INTO social.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
    VALUES (v_tipo_entidad, v_entidad, v_evento, v_datos);
    RETURN NULL;
END;
$$;
COMMENT ON FUNCTION social.emitir_evento() IS 'Escribe en el outbox el evento de cada cambio de la red, en la misma transacción';

CREATE TRIGGER usuario_salida AFTER INSERT OR UPDATE OF estado ON social.usuario
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER seguimiento_salida AFTER INSERT OR DELETE ON social.seguimiento
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER publicacion_salida AFTER INSERT OR UPDATE OF estado ON social.publicacion
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER publicacion_etiqueta_salida AFTER INSERT ON social.publicacion_etiqueta
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER mencion_usuario_salida AFTER INSERT ON social.mencion_usuario
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER mencion_figura_salida AFTER INSERT ON social.mencion_figura
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER reaccion_salida AFTER INSERT OR UPDATE OF tipo OR DELETE ON social.reaccion
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER figura_publica_salida AFTER INSERT ON social.figura_publica
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();
CREATE TRIGGER declaracion_salida AFTER INSERT ON social.declaracion
    FOR EACH ROW EXECUTE FUNCTION social.emitir_evento();

-- Despierta a los consumidores (grafo y verificación) sin que tengan que preguntar a cada rato.
CREATE FUNCTION social.avisar_evento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('evento_salida', 'social');
    RETURN NULL;
END;
$$;
CREATE TRIGGER evento_salida_aviso AFTER INSERT ON social.evento_salida
    FOR EACH STATEMENT EXECUTE FUNCTION social.avisar_evento();
