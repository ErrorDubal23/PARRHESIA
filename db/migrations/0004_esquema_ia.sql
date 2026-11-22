-- 0004: esquema ia. Cola de trabajos de IA independiente de la cuenta.
--
-- Diseño: docs/diseno/03_servicio_ia.md y 05_logica_bd.md.
-- La app nunca llama a la IA: el servicio de verificación (o el de temas) encola un
-- trabajo; el servicio de IA lo toma con FOR UPDATE SKIP LOCKED, elige una cuenta
-- disponible y registra cada intento. Si una cuenta llega a su límite, queda en pausa
-- y el trabajo pasa a otra. La base nunca guarda una llave secreta: solo el alias.

CREATE SCHEMA ia;
COMMENT ON SCHEMA ia IS 'Cola de trabajos de IA, intentos y cuentas (sin secretos)';

-- =============================================================================
-- PARTE 1 · Tablas
-- =============================================================================

-- CREDENCIAL: una cuenta del proveedor, identificada solo por su alias.
-- La llave vive en la configuración del contenedor del servicio de IA
-- (variable GROQ_KEY_<alias>), nunca aquí.
CREATE TABLE ia.credencial (
    alias           text        NOT NULL,
    proveedor       text        NOT NULL,
    habilitada      boolean     NOT NULL DEFAULT true,
    pausada_hasta   timestamptz,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT credencial_pkey PRIMARY KEY (alias),
    CONSTRAINT credencial_alias_valido CHECK (alias ~ '^[a-z0-9_]{3,40}$'),
    CONSTRAINT credencial_proveedor_valido CHECK (proveedor ~ '^[a-z0-9_]{2,30}$')
);
COMMENT ON TABLE ia.credencial IS 'Cuentas del proveedor de IA por alias. No hay columna para la llave secreta';

-- TRABAJO: una tarea para la IA, con su entrada y, al terminar, su salida validada.
CREATE TABLE ia.trabajo (
    id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
    tipo                text        NOT NULL,
    version_prompt      text        NOT NULL,
    entrada             jsonb       NOT NULL,
    huella_entrada      text        NOT NULL,     -- sha256 de la entrada; la calcula un trigger
    estado              text        NOT NULL DEFAULT 'en_cola',
    salida              jsonb,
    proximo_intento_en  timestamptz NOT NULL DEFAULT now(),
    creado_en           timestamptz NOT NULL DEFAULT now(),
    terminado_en        timestamptz,
    CONSTRAINT trabajo_pkey PRIMARY KEY (id),
    CONSTRAINT trabajo_tipo_valido CHECK (tipo IN
        ('extraer_afirmaciones', 'redactar_explicacion', 'agrupar_temas', 'extraer_declaraciones')),
    CONSTRAINT trabajo_estado_valido CHECK (estado IN ('en_cola', 'en_curso', 'terminado', 'fallido')),
    -- Hay salida si y solo si el trabajo terminó bien.
    CONSTRAINT trabajo_salida_solo_si_terminado CHECK ((estado = 'terminado') = (salida IS NOT NULL)),
    -- Un trabajo terminado o fallido tiene su fecha de fin, y solo ellos.
    CONSTRAINT trabajo_fin_solo_si_cerrado CHECK ((estado IN ('terminado', 'fallido')) = (terminado_en IS NOT NULL))
);
-- Caché: la misma entrada, con el mismo tipo y la misma versión del prompt, se resuelve una sola vez.
CREATE UNIQUE INDEX trabajo_resultado_unico_idx ON ia.trabajo (tipo, version_prompt, huella_entrada)
    WHERE estado = 'terminado';
-- Tampoco se encola dos veces lo mismo mientras está pendiente.
CREATE UNIQUE INDEX trabajo_pendiente_unico_idx ON ia.trabajo (tipo, version_prompt, huella_entrada)
    WHERE estado IN ('en_cola', 'en_curso');
CREATE INDEX trabajo_cola_idx ON ia.trabajo (proximo_intento_en) WHERE estado IN ('en_cola', 'en_curso');
COMMENT ON TABLE ia.trabajo IS 'Cola de trabajos de IA. La salida solo se guarda después de validar su formato';

-- INTENTO: cada llamada al proveedor, con la cuenta usada y su resultado.
CREATE TABLE ia.intento (
    trabajo_id        uuid        NOT NULL,
    numero            smallint    NOT NULL,
    credencial_alias  text        NOT NULL,
    modelo            text        NOT NULL,
    resultado         text        NOT NULL,
    tokens_entrada    integer,
    tokens_salida     integer,
    error             text,
    iniciado_en       timestamptz NOT NULL,
    terminado_en      timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT intento_pkey PRIMARY KEY (trabajo_id, numero),
    CONSTRAINT intento_trabajo_id_fkey FOREIGN KEY (trabajo_id) REFERENCES ia.trabajo (id),
    CONSTRAINT intento_credencial_alias_fkey FOREIGN KEY (credencial_alias) REFERENCES ia.credencial (alias),
    CONSTRAINT intento_resultado_valido CHECK (resultado IN ('ok', 'limite_alcanzado', 'error_proveedor', 'salida_invalida')),
    CONSTRAINT intento_numero_positivo CHECK (numero >= 1),
    CONSTRAINT intento_tokens_positivos CHECK (coalesce(tokens_entrada, 0) >= 0 AND coalesce(tokens_salida, 0) >= 0),
    CONSTRAINT intento_fechas_validas CHECK (terminado_en >= iniciado_en),
    CONSTRAINT intento_error_si_falla CHECK ((resultado = 'ok') = (error IS NULL))
);
CREATE INDEX intento_credencial_idx ON ia.intento (credencial_alias, iniciado_en DESC);
COMMENT ON TABLE ia.intento IS 'Historial de llamadas al proveedor: cuenta, modelo, tokens y resultado. Solo inserción';

-- =============================================================================
-- PARTE 2 · Triggers
-- =============================================================================

-- La huella se calcula siempre en la base: el texto de un jsonb sale con las llaves
-- ordenadas, así que la misma entrada da la misma huella aunque llegue en otro orden.
CREATE FUNCTION ia.calcular_huella() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.huella_entrada := encode(sha256(convert_to(NEW.entrada::text, 'UTF8')), 'hex');
    RETURN NEW;
END;
$$;
CREATE TRIGGER trabajo_huella BEFORE INSERT ON ia.trabajo
    FOR EACH ROW EXECUTE FUNCTION ia.calcular_huella();

-- Lo que define un trabajo no cambia después de encolarlo.
CREATE FUNCTION ia.trabajo_cambios_permitidos() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id, NEW.tipo, NEW.version_prompt, NEW.entrada, NEW.huella_entrada, NEW.creado_en)
       IS DISTINCT FROM (OLD.id, OLD.tipo, OLD.version_prompt, OLD.entrada, OLD.huella_entrada, OLD.creado_en) THEN
        RAISE EXCEPTION 'ia.trabajo: el tipo, la versión del prompt y la entrada no cambian';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trabajo_cambios_permitidos BEFORE UPDATE ON ia.trabajo
    FOR EACH ROW EXECUTE FUNCTION ia.trabajo_cambios_permitidos();

-- Máquina de estados: terminado y fallido son finales.
CREATE TRIGGER trabajo_transicion BEFORE UPDATE OF estado ON ia.trabajo
    FOR EACH ROW EXECUTE FUNCTION util.validar_transicion(
        '{"en_cola": ["en_curso"], "en_curso": ["en_cola", "terminado", "fallido"]}');
CREATE TRIGGER trabajo_sin_borrado BEFORE DELETE ON ia.trabajo
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

CREATE TRIGGER intento_solo_insercion BEFORE UPDATE OR DELETE ON ia.intento
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER credencial_actualizado BEFORE UPDATE ON ia.credencial
    FOR EACH ROW EXECUTE FUNCTION util.marcar_actualizado();

-- Despierta al servicio de IA cuando llega trabajo nuevo.
CREATE FUNCTION ia.avisar_trabajo() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('trabajo_ia', 'nuevo');
    RETURN NULL;
END;
$$;
CREATE TRIGGER trabajo_aviso AFTER INSERT ON ia.trabajo
    FOR EACH STATEMENT EXECUTE FUNCTION ia.avisar_trabajo();

-- =============================================================================
-- PARTE 3 · Funciones
-- =============================================================================

-- Toma el siguiente trabajo listo. FOR UPDATE SKIP LOCKED: si otro trabajador tiene
-- bloqueada una fila, esta consulta la salta en vez de esperarla, así dos
-- trabajadores nunca reciben el mismo trabajo. Al tomarlo se le da un plazo de 5
-- minutos: si el trabajador se cae, al vencer el plazo otro lo puede retomar.
CREATE FUNCTION ia.tomar_trabajo(p_tipos text[]) RETURNS SETOF ia.trabajo
LANGUAGE sql VOLATILE AS $$
    UPDATE ia.trabajo t
    SET estado = 'en_curso',
        proximo_intento_en = now() + interval '5 minutes'
    WHERE t.id = (
        SELECT c.id FROM ia.trabajo c
        WHERE c.tipo = ANY (p_tipos)
          AND c.estado IN ('en_cola', 'en_curso')      -- 'en_curso' con plazo vencido = trabajador caído
          AND c.proximo_intento_en <= now()
        ORDER BY c.proximo_intento_en
        FOR UPDATE SKIP LOCKED
        LIMIT 1)
    RETURNING t.*;
$$;
COMMENT ON FUNCTION ia.tomar_trabajo(text[]) IS 'Toma un trabajo listo sin chocar con otros trabajadores (FOR UPDATE SKIP LOCKED)';

-- La cuenta habilitada y sin pausa que lleva más tiempo sin usarse: reparte la
-- carga entre cuentas. Nulo si todas están en pausa.
CREATE FUNCTION ia.elegir_credencial(p_proveedor text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT c.alias
    FROM ia.credencial c
    LEFT JOIN LATERAL (SELECT max(i.iniciado_en) AS ultimo_uso FROM ia.intento i
                       WHERE i.credencial_alias = c.alias) u ON true
    WHERE c.proveedor = p_proveedor AND c.habilitada
      AND (c.pausada_hasta IS NULL OR c.pausada_hasta <= now())
    ORDER BY u.ultimo_uso NULLS FIRST, c.alias
    LIMIT 1;
$$;
COMMENT ON FUNCTION ia.elegir_credencial(text) IS 'Cuenta disponible que lleva más tiempo sin usarse; nulo si todas están en pausa';

-- Para un tablero: cuántos trabajos hay en cada estado.
CREATE FUNCTION ia.estado_cola() RETURNS TABLE (tipo text, estado text, total bigint)
LANGUAGE sql STABLE AS $$
    SELECT tipo, estado, count(*) FROM ia.trabajo GROUP BY tipo, estado ORDER BY tipo, estado;
$$;

-- =============================================================================
-- PARTE 4 · Procedimientos
-- =============================================================================

-- Encolar: si la misma entrada ya está resuelta, devuelve ese trabajo (caché) sin
-- llamar a la IA; si ya está en cola, devuelve el que está en cola.
CREATE PROCEDURE ia.encolar_trabajo(
    p_tipo text, p_version_prompt text, p_entrada jsonb,
    INOUT p_trabajo_id uuid, INOUT p_desde_cache boolean)
LANGUAGE plpgsql AS $$
DECLARE
    v_huella text := encode(sha256(convert_to(p_entrada::text, 'UTF8')), 'hex');
BEGIN
    SELECT id INTO p_trabajo_id FROM ia.trabajo
    WHERE tipo = p_tipo AND version_prompt = p_version_prompt AND huella_entrada = v_huella
      AND estado = 'terminado';
    IF FOUND THEN
        p_desde_cache := true;
        RETURN;
    END IF;
    p_desde_cache := false;

    -- Si dos servicios encolan lo mismo a la vez, el índice único parcial deja pasar
    -- a uno solo; el otro recibe el trabajo que ya quedó en cola.
    INSERT INTO ia.trabajo (tipo, version_prompt, entrada)
    VALUES (p_tipo, p_version_prompt, p_entrada)
    ON CONFLICT (tipo, version_prompt, huella_entrada) WHERE estado IN ('en_cola', 'en_curso') DO NOTHING
    RETURNING id INTO p_trabajo_id;
    IF p_trabajo_id IS NULL THEN
        SELECT id INTO p_trabajo_id FROM ia.trabajo
        WHERE tipo = p_tipo AND version_prompt = p_version_prompt AND huella_entrada = v_huella
          AND estado IN ('en_cola', 'en_curso');
    END IF;
END;
$$;
COMMENT ON PROCEDURE ia.encolar_trabajo(text, text, jsonb, uuid, boolean)
    IS 'Encola un trabajo, o devuelve el ya resuelto (caché) o el ya pendiente';

-- Registrar un intento y mover el trabajo, todo en una transacción:
--   ok                -> terminado, con su salida validada
--   limite_alcanzado  -> la cuenta queda en pausa; el trabajo vuelve a la cola sin
--                        contar como fallo (a otra cuenta, o cuando acabe la pausa)
--   error_proveedor,
--   salida_invalida   -> vuelve a la cola con espera creciente (2, 4, 8, 16 s);
--                        al quinto fallo, fallido
CREATE PROCEDURE ia.registrar_intento(
    p_trabajo_id uuid, p_alias text, p_modelo text, p_resultado text,
    p_tokens_entrada integer, p_tokens_salida integer, p_error text,
    p_salida jsonb, p_esperar interval, p_iniciado_en timestamptz)
LANGUAGE plpgsql AS $$
DECLARE
    v_numero     smallint;
    v_proveedor  text;
    v_fallos     int;
    v_libre      text;
BEGIN
    PERFORM 1 FROM ia.trabajo WHERE id = p_trabajo_id AND estado = 'en_curso' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'trabajo_no_en_curso: el trabajo % no está en curso', p_trabajo_id;
    END IF;
    IF p_resultado = 'ok' AND p_salida IS NULL THEN
        RAISE EXCEPTION 'salida_faltante: un intento exitoso necesita su salida validada';
    END IF;

    SELECT coalesce(max(numero), 0) + 1 INTO v_numero FROM ia.intento WHERE trabajo_id = p_trabajo_id;
    INSERT INTO ia.intento (trabajo_id, numero, credencial_alias, modelo, resultado,
                            tokens_entrada, tokens_salida, error, iniciado_en)
    VALUES (p_trabajo_id, v_numero, p_alias, p_modelo, p_resultado,
            p_tokens_entrada, p_tokens_salida, p_error, p_iniciado_en);

    IF p_resultado = 'ok' THEN
        UPDATE ia.trabajo SET estado = 'terminado', salida = p_salida, terminado_en = now()
        WHERE id = p_trabajo_id;

    ELSIF p_resultado = 'limite_alcanzado' THEN
        UPDATE ia.credencial SET pausada_hasta = now() + coalesce(p_esperar, interval '60 seconds')
        WHERE alias = p_alias
        RETURNING proveedor INTO v_proveedor;
        v_libre := ia.elegir_credencial(v_proveedor);
        UPDATE ia.trabajo
        SET estado = 'en_cola',
            proximo_intento_en = CASE
                WHEN v_libre IS NOT NULL THEN now()
                ELSE (SELECT min(pausada_hasta) FROM ia.credencial
                      WHERE proveedor = v_proveedor AND habilitada AND pausada_hasta > now())
            END
        WHERE id = p_trabajo_id;

    ELSE
        SELECT count(*) INTO v_fallos FROM ia.intento
        WHERE trabajo_id = p_trabajo_id AND resultado IN ('error_proveedor', 'salida_invalida');
        IF v_fallos >= 5 THEN
            UPDATE ia.trabajo SET estado = 'fallido', terminado_en = now() WHERE id = p_trabajo_id;
        ELSE
            UPDATE ia.trabajo
            SET estado = 'en_cola', proximo_intento_en = now() + make_interval(secs => 2 ^ v_fallos)
            WHERE id = p_trabajo_id;
        END IF;
    END IF;
END;
$$;
COMMENT ON PROCEDURE ia.registrar_intento(uuid, text, text, text, integer, integer, text, jsonb, interval, timestamptz)
    IS 'Guarda un intento y mueve el trabajo y la cuenta según el resultado';

-- Agregar o habilitar una cuenta. Después basta reiniciar solo el servicio de IA.
CREATE PROCEDURE ia.configurar_credencial(p_alias text, p_proveedor text, p_habilitada boolean)
LANGUAGE sql AS $$
    INSERT INTO ia.credencial (alias, proveedor, habilitada) VALUES (p_alias, p_proveedor, p_habilitada)
    ON CONFLICT (alias) DO UPDATE SET proveedor = EXCLUDED.proveedor, habilitada = EXCLUDED.habilitada;
$$;
