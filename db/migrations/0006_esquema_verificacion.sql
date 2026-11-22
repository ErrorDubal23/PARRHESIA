-- 0006: esquema verificacion. Afirmaciones, verificaciones versionadas y su evidencia oficial.
--
-- Diseño: docs/diseno/02_MR.md, 05_logica_bd.md y 06_temas_del_dia.md
-- (decisiones 5, 12, 18 y 20). Aquí están las garantías centrales del proyecto:
--   · una conclusión (distinta de "sin dato comparable") siempre tiene evidencia oficial;
--   · la evidencia solo puede ser una observación vigente y aceptada;
--   · una explicación validada no puede contener una cifra que no esté en la evidencia.
-- Las referencias a otros esquemas (oficial, social, temas, ia) no son llaves
-- foráneas: las revisan triggers con funciones (decisión 1).

CREATE SCHEMA verificacion;
COMMENT ON SCHEMA verificacion IS 'Afirmaciones con cifras, verificaciones contra el dato oficial, evidencia y revisiones';

-- =============================================================================
-- PARTE 1 · Catálogos
-- =============================================================================

-- Filtro previo sin IA (decisión 20): un texto pasa a la IA solo si tiene una cifra
-- y alguna de estas palabras. Los códigos de indicador son los del catálogo.
CREATE TABLE verificacion.palabra_clave (
    codigo_indicador  text NOT NULL,
    palabra           text NOT NULL,
    CONSTRAINT palabra_clave_pkey PRIMARY KEY (codigo_indicador, palabra),
    CONSTRAINT palabra_clave_indicador_valido CHECK (codigo_indicador IN (
        'inflation', 'unemployment', 'minimum_wage', 'public_debt', 'homicides', 'theft', 'extortion', 'kidnapping')),
    CONSTRAINT palabra_clave_minusculas CHECK (palabra = lower(palabra) AND length(palabra) >= 3)
);
COMMENT ON TABLE verificacion.palabra_clave IS 'Palabras de los 8 indicadores para el filtro previo sin IA';

INSERT INTO verificacion.palabra_clave (codigo_indicador, palabra) VALUES
    ('inflation', 'inflación'), ('inflation', 'inflacion'), ('inflation', 'ipc'), ('inflation', 'precios'),
    ('inflation', 'costo de vida'),
    ('unemployment', 'desempleo'), ('unemployment', 'desocupación'), ('unemployment', 'desocupacion'),
    ('unemployment', 'desempleados'), ('unemployment', 'empleo'),
    ('minimum_wage', 'salario mínimo'), ('minimum_wage', 'salario minimo'), ('minimum_wage', 'smmlv'),
    ('minimum_wage', 'mínimo'),
    ('public_debt', 'deuda pública'), ('public_debt', 'deuda publica'), ('public_debt', 'deuda'),
    ('homicides', 'homicidio'), ('homicides', 'homicidios'), ('homicides', 'asesinatos'), ('homicides', 'muertes violentas'),
    ('theft', 'hurto'), ('theft', 'hurtos'), ('theft', 'robos'), ('theft', 'robo'),
    ('extortion', 'extorsión'), ('extortion', 'extorsion'), ('extortion', 'extorsiones'),
    ('kidnapping', 'secuestro'), ('kidnapping', 'secuestros');

-- Catálogo de pruebas de robustez (brechas de contexto que se buscan).
CREATE TABLE verificacion.prueba_robustez (
    codigo       text NOT NULL,
    nombre       text NOT NULL,
    descripcion  text NOT NULL,
    CONSTRAINT prueba_robustez_pkey PRIMARY KEY (codigo),
    CONSTRAINT prueba_robustez_codigo_valido CHECK (codigo ~ '^[a-z_]{3,40}$')
);
COMMENT ON TABLE verificacion.prueba_robustez IS 'Pruebas que se aplican a cada afirmación para encontrar brechas de contexto';

INSERT INTO verificacion.prueba_robustez (codigo, nombre, descripcion) VALUES
    ('variante_equivocada', 'Variante equivocada', 'La cifra corresponde a otra variante del indicador (por ejemplo, mensual en vez de anual)'),
    ('periodo_limitado', 'Periodo de comparación limitado', 'La comparación usa un periodo que no representa la serie completa'),
    ('nominal_vs_real', 'Nominal frente a real', 'Se compara un valor nominal cuando la comparación necesita el valor real'),
    ('fuente_distinta', 'Fuente distinta', 'La cifra viene de una fuente distinta a la oficial registrada'),
    ('dato_provisional', 'Dato provisional', 'El valor oficial del periodo todavía es provisional y puede cambiar'),
    ('nota_serie', 'Nota de la serie', 'La serie tiene una nota (cambio de metodología, conflicto entre fuentes) que afecta la comparación');

-- =============================================================================
-- PARTE 2 · Tablas
-- =============================================================================

-- PROCESAMIENTO: qué textos ya pasaron por el filtro o por la IA y con qué resultado.
-- Permite distinguir "todavía no se revisó" de "se revisó y no tenía cifras".
CREATE TABLE verificacion.procesamiento (
    origen_tipo     text        NOT NULL,
    origen_id       uuid        NOT NULL,
    resultado       text        NOT NULL,
    procesado_en    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT procesamiento_pkey PRIMARY KEY (origen_tipo, origen_id),
    CONSTRAINT procesamiento_origen_valido CHECK (origen_tipo IN ('publicacion', 'declaracion', 'declaracion_reportada')),
    CONSTRAINT procesamiento_resultado_valido CHECK (resultado IN ('sin_cifras', 'sin_afirmaciones', 'con_afirmaciones', 'fallido'))
);
COMMENT ON TABLE verificacion.procesamiento IS 'Resultado de pasar un texto por el filtro previo y la extracción';

-- AFIRMACION: una cifra concreta que dice un texto, extraída por la IA.
CREATE TABLE verificacion.afirmacion (
    id                        uuid        NOT NULL DEFAULT gen_random_uuid(),
    publicacion_id            uuid,       -- lógica -> social.publicacion
    declaracion_id            uuid,       -- lógica -> social.declaracion
    declaracion_reportada_id  uuid,       -- lógica -> temas.declaracion_reportada
    posicion                  smallint    NOT NULL,
    texto_citado              text        NOT NULL,
    codigo_indicador          text,
    variante                  text,
    periodo_desde             text,
    periodo_hasta             text,
    territorio                text,
    valor_dicho               numeric,
    unidad_dicha              text,
    comparacion               text,
    confianza_extraccion      numeric     NOT NULL,
    trabajo_ia_id             uuid,       -- lógica -> ia.trabajo
    estado                    text        NOT NULL DEFAULT 'extraida',
    creado_en                 timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT afirmacion_pkey PRIMARY KEY (id),
    -- Arco exclusivo: sale de un solo texto.
    CONSTRAINT afirmacion_un_solo_origen CHECK (num_nonnulls(publicacion_id, declaracion_id, declaracion_reportada_id) = 1),
    CONSTRAINT afirmacion_publicacion_posicion_key UNIQUE (publicacion_id, posicion),
    CONSTRAINT afirmacion_declaracion_posicion_key UNIQUE (declaracion_id, posicion),
    CONSTRAINT afirmacion_reportada_posicion_key UNIQUE (declaracion_reportada_id, posicion),
    CONSTRAINT afirmacion_posicion_valida CHECK (posicion >= 1),
    CONSTRAINT afirmacion_indicador_valido CHECK (codigo_indicador IN (
        'inflation', 'unemployment', 'minimum_wage', 'public_debt', 'homicides', 'theft', 'extortion', 'kidnapping')),
    CONSTRAINT afirmacion_variante_valida CHECK (variante IN
        ('anual', 'mensual', 'anio_corrido', 'tasa', 'conteo', 'nominal', 'real')),
    CONSTRAINT afirmacion_periodos_validos CHECK (
        periodo_desde ~ '^\d{4}(-\d{2}(-\d{2})?)?$' AND periodo_hasta ~ '^\d{4}(-\d{2}(-\d{2})?)?$'
        AND periodo_desde <= periodo_hasta),
    CONSTRAINT afirmacion_comparacion_valida CHECK (comparacion IN ('nivel', 'variacion_porcentual', 'variacion_puntos')),
    CONSTRAINT afirmacion_confianza_valida CHECK (confianza_extraccion BETWEEN 0 AND 1),
    CONSTRAINT afirmacion_estado_valido CHECK (estado IN ('extraida', 'no_verificable', 'verificada', 'requiere_revision'))
);
CREATE INDEX afirmacion_publicacion_idx ON verificacion.afirmacion (publicacion_id) WHERE publicacion_id IS NOT NULL;
CREATE INDEX afirmacion_declaracion_idx ON verificacion.afirmacion (declaracion_id) WHERE declaracion_id IS NOT NULL;
CREATE INDEX afirmacion_reportada_idx ON verificacion.afirmacion (declaracion_reportada_id) WHERE declaracion_reportada_id IS NOT NULL;
COMMENT ON TABLE verificacion.afirmacion IS 'Cifra de una publicación o declaración sobre los 8 indicadores. Solo cambia su estado';

-- VERIFICACION: la conclusión sobre una afirmación. Versionada: no se edita (decisión 5).
CREATE TABLE verificacion.verificacion (
    id                    uuid        NOT NULL DEFAULT gen_random_uuid(),
    afirmacion_id         uuid        NOT NULL,
    version               smallint    NOT NULL,
    codigo_serie          text,       -- lógica -> oficial.serie.codigo
    conclusion            text        NOT NULL,
    explicacion           text        NOT NULL,
    explicacion_validada  boolean     NOT NULL,
    version_motor         text        NOT NULL,
    creado_en             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT verificacion_pkey PRIMARY KEY (id),
    CONSTRAINT verificacion_afirmacion_id_fkey FOREIGN KEY (afirmacion_id) REFERENCES verificacion.afirmacion (id),
    CONSTRAINT verificacion_afirmacion_version_key UNIQUE (afirmacion_id, version),
    CONSTRAINT verificacion_version_positiva CHECK (version >= 1),
    -- Nunca "verdadero/falso": se sostiene, se debilita, se invierte o no hay dato comparable.
    CONSTRAINT verificacion_conclusion_valida CHECK (conclusion IN ('se_sostiene', 'se_debilita', 'se_invierte', 'sin_dato_comparable')),
    -- Hay serie si y solo si hay dato comparable.
    CONSTRAINT verificacion_serie_si_hay_dato CHECK ((codigo_serie IS NULL) = (conclusion = 'sin_dato_comparable')),
    CONSTRAINT verificacion_explicacion_valida CHECK (length(trim(explicacion)) >= 1)
);
COMMENT ON TABLE verificacion.verificacion IS 'Conclusión versionada; la vigente es la de mayor versión. Solo inserción';

-- EVIDENCIA: qué observaciones oficiales respaldan la conclusión.
CREATE TABLE verificacion.evidencia (
    verificacion_id  uuid NOT NULL,
    observacion_id   uuid NOT NULL,       -- lógica -> oficial.observacion (vigente y aceptada)
    rol              text NOT NULL,
    CONSTRAINT evidencia_pkey PRIMARY KEY (verificacion_id, observacion_id),
    CONSTRAINT evidencia_verificacion_id_fkey FOREIGN KEY (verificacion_id) REFERENCES verificacion.verificacion (id),
    CONSTRAINT evidencia_rol_valido CHECK (rol IN ('citada', 'completa', 'contraste'))
);
COMMENT ON TABLE verificacion.evidencia IS 'Observaciones oficiales que respaldan una verificación. Solo inserción';

CREATE TABLE verificacion.resultado_prueba (
    verificacion_id  uuid NOT NULL,
    codigo_prueba    text NOT NULL,
    resultado        text NOT NULL,
    detalle          text,
    CONSTRAINT resultado_prueba_pkey PRIMARY KEY (verificacion_id, codigo_prueba),
    CONSTRAINT resultado_prueba_verificacion_id_fkey FOREIGN KEY (verificacion_id) REFERENCES verificacion.verificacion (id),
    CONSTRAINT resultado_prueba_codigo_prueba_fkey FOREIGN KEY (codigo_prueba) REFERENCES verificacion.prueba_robustez (codigo),
    CONSTRAINT resultado_prueba_resultado_valido CHECK (resultado IN ('sin_brecha', 'con_brecha', 'no_aplica'))
);
COMMENT ON TABLE verificacion.resultado_prueba IS 'Resultado de cada prueba de robustez en una verificación. Solo inserción';

CREATE TABLE verificacion.revision_humana (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    verificacion_id  uuid        NOT NULL,
    revisor_id       uuid        NOT NULL,      -- lógica -> social.usuario (verificador o admin)
    decision         text        NOT NULL,
    motivo           text        NOT NULL,
    creado_en        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT revision_humana_pkey PRIMARY KEY (id),
    CONSTRAINT revision_humana_verificacion_id_fkey FOREIGN KEY (verificacion_id) REFERENCES verificacion.verificacion (id),
    CONSTRAINT revision_humana_decision_valida CHECK (decision IN ('confirmada', 'corregida')),
    CONSTRAINT revision_humana_motivo_valido CHECK (length(trim(motivo)) >= 3)
);
COMMENT ON TABLE verificacion.revision_humana IS 'Revisión de una verificación por un verificador. Solo inserción';

-- Outbox hacia el grafo (decisiones 10 y 18)
CREATE TABLE verificacion.evento_salida (
    id            bigint      GENERATED ALWAYS AS IDENTITY,
    tipo_entidad  text        NOT NULL,
    entidad_id    text        NOT NULL,
    tipo_evento   text        NOT NULL,
    datos         jsonb       NOT NULL,
    creado_en     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT evento_salida_pkey PRIMARY KEY (id)
);
CREATE INDEX evento_salida_tipo_idx ON verificacion.evento_salida (tipo_evento, id);

CREATE TABLE verificacion.entrega_evento (
    evento_id     bigint      NOT NULL,
    consumidor    text        NOT NULL,
    entregado_en  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT entrega_evento_pkey PRIMARY KEY (evento_id, consumidor),
    CONSTRAINT entrega_evento_evento_id_fkey FOREIGN KEY (evento_id) REFERENCES verificacion.evento_salida (id),
    CONSTRAINT entrega_evento_consumidor_valido CHECK (consumidor IN ('grafo', 'verificacion'))
);

-- =============================================================================
-- PARTE 3 · Funciones
-- =============================================================================

-- Filtro previo sin IA: al menos una cifra y una palabra clave (sin distinguir tildes).
CREATE FUNCTION verificacion.requiere_extraccion(p_texto text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT cardinality(util.cifras_en_texto(p_texto)) > 0
       AND EXISTS (
           SELECT 1 FROM verificacion.palabra_clave k
           WHERE position(translate(k.palabra, 'áéíóúü', 'aeiouu')
                          IN translate(lower(coalesce(p_texto, '')), 'áéíóúü', 'aeiouu')) > 0);
$$;
COMMENT ON FUNCTION verificacion.requiere_extraccion(text) IS 'Filtro previo sin IA: verdadero si el texto tiene una cifra y una palabra de los 8 indicadores';

CREATE FUNCTION verificacion.verificacion_vigente(p_afirmacion_id uuid) RETURNS SETOF verificacion.verificacion
LANGUAGE sql STABLE AS $$
    SELECT * FROM verificacion.verificacion WHERE afirmacion_id = p_afirmacion_id ORDER BY version DESC LIMIT 1;
$$;
COMMENT ON FUNCTION verificacion.verificacion_vigente(uuid) IS 'La versión vigente (la mayor) de la verificación de una afirmación';

-- Las cifras que una explicación puede usar: los valores de la evidencia, el valor
-- que dijo el texto y los números de los periodos citados (años y meses).
-- SECURITY DEFINER: lee las observaciones oficiales sin dar permiso sobre oficial.
CREATE FUNCTION verificacion.cifras_permitidas(p_verificacion_id uuid) RETURNS numeric[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT coalesce(array_agg(DISTINCT n), '{}') FROM (
        SELECT o.valor AS n
        FROM verificacion.evidencia e JOIN oficial.observacion o ON o.id = e.observacion_id
        WHERE e.verificacion_id = p_verificacion_id AND o.valor IS NOT NULL
        UNION ALL
        SELECT parte::numeric
        FROM verificacion.evidencia e JOIN oficial.observacion o ON o.id = e.observacion_id,
             LATERAL unnest(string_to_array(o.periodo, '-')) AS parte
        WHERE e.verificacion_id = p_verificacion_id
        UNION ALL
        SELECT a.valor_dicho
        FROM verificacion.verificacion v JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id
        WHERE v.id = p_verificacion_id AND a.valor_dicho IS NOT NULL
        UNION ALL
        SELECT parte::numeric
        FROM verificacion.verificacion v JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id,
             LATERAL unnest(string_to_array(concat_ws('-', a.periodo_desde, a.periodo_hasta), '-')) AS parte
        WHERE v.id = p_verificacion_id AND parte <> ''
    ) AS permitidas;
$$;
COMMENT ON FUNCTION verificacion.cifras_permitidas(uuid) IS 'Cifras que puede usar la explicación de una verificación';

-- Lo que la app muestra junto a una publicación.
CREATE FUNCTION verificacion.estado_publicacion(p_publicacion_id uuid) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN p.resultado IS NULL THEN 'pendiente'
        WHEN p.resultado IN ('sin_cifras', 'sin_afirmaciones') THEN 'sin_cifras'
        WHEN p.resultado = 'fallido' THEN 'requiere_revision'
        WHEN EXISTS (SELECT 1 FROM verificacion.afirmacion a
                     WHERE a.publicacion_id = p_publicacion_id AND a.estado = 'requiere_revision') THEN 'requiere_revision'
        WHEN EXISTS (SELECT 1 FROM verificacion.afirmacion a
                     WHERE a.publicacion_id = p_publicacion_id AND a.estado = 'extraida') THEN 'pendiente'
        ELSE 'lista'
    END
    FROM (SELECT (SELECT resultado FROM verificacion.procesamiento
                  WHERE origen_tipo = 'publicacion' AND origen_id = p_publicacion_id) AS resultado) AS p;
$$;
COMMENT ON FUNCTION verificacion.estado_publicacion(uuid)
    IS 'sin_cifras (es opinión), pendiente, lista o requiere_revision';

-- Para la página de una tendencia o de un tema: conclusiones vigentes agrupadas.
-- Solo cuenta lo guardado; no produce cifras nuevas.
CREATE FUNCTION verificacion.resumen_conclusiones(p_publicaciones uuid[], p_declaraciones uuid[], p_reportadas uuid[])
RETURNS TABLE (conclusion text, total bigint, series text[])
LANGUAGE sql STABLE AS $$
    WITH vigentes AS (
        SELECT DISTINCT ON (a.id) v.conclusion, v.codigo_serie
        FROM verificacion.afirmacion a
        JOIN verificacion.verificacion v ON v.afirmacion_id = a.id
        WHERE a.publicacion_id = ANY (coalesce(p_publicaciones, '{}'))
           OR a.declaracion_id = ANY (coalesce(p_declaraciones, '{}'))
           OR a.declaracion_reportada_id = ANY (coalesce(p_reportadas, '{}'))
        ORDER BY a.id, v.version DESC
    )
    SELECT conclusion, count(*), array_remove(array_agg(DISTINCT codigo_serie), NULL)
    FROM vigentes GROUP BY conclusion ORDER BY conclusion;
$$;
COMMENT ON FUNCTION verificacion.resumen_conclusiones(uuid[], uuid[], uuid[])
    IS 'Conteo de conclusiones vigentes y series citadas de un conjunto de textos';

CREATE FUNCTION verificacion.eventos_pendientes(p_consumidor text, p_tipos text[], p_limite int DEFAULT 100)
RETURNS SETOF verificacion.evento_salida
LANGUAGE sql STABLE AS $$
    SELECT e.* FROM verificacion.evento_salida e
    WHERE e.tipo_evento = ANY (p_tipos)
      AND NOT EXISTS (SELECT 1 FROM verificacion.entrega_evento d WHERE d.evento_id = e.id AND d.consumidor = p_consumidor)
    ORDER BY e.id
    LIMIT p_limite;
$$;

-- =============================================================================
-- PARTE 4 · Triggers
-- =============================================================================

-- Integridad entre esquemas (decisión 1): el texto de origen existe.
CREATE FUNCTION verificacion.afirmacion_destino_existe() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.publicacion_id IS NOT NULL AND NOT social.publicacion_existe(NEW.publicacion_id))
       OR (NEW.declaracion_id IS NOT NULL AND NOT social.declaracion_existe(NEW.declaracion_id))
       OR (NEW.declaracion_reportada_id IS NOT NULL AND NOT temas.declaracion_existe(NEW.declaracion_reportada_id)) THEN
        RAISE EXCEPTION 'origen_inexistente: el texto de la afirmación no existe';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER afirmacion_destino_existe BEFORE INSERT ON verificacion.afirmacion
    FOR EACH ROW EXECUTE FUNCTION verificacion.afirmacion_destino_existe();

-- Una afirmación solo cambia de estado.
CREATE FUNCTION verificacion.afirmacion_cambios_permitidos() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - 'estado') IS DISTINCT FROM (to_jsonb(OLD) - 'estado') THEN
        RAISE EXCEPTION 'verificacion.afirmacion: solo puede cambiar el estado';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER afirmacion_cambios_permitidos BEFORE UPDATE ON verificacion.afirmacion
    FOR EACH ROW EXECUTE FUNCTION verificacion.afirmacion_cambios_permitidos();
CREATE TRIGGER afirmacion_transicion BEFORE UPDATE OF estado ON verificacion.afirmacion
    FOR EACH ROW EXECUTE FUNCTION util.validar_transicion(
        '{"extraida": ["verificada", "no_verificable", "requiere_revision"],
          "verificada": ["requiere_revision", "no_verificable"],
          "no_verificable": ["requiere_revision", "verificada"],
          "requiere_revision": ["verificada", "no_verificable"]}');
CREATE TRIGGER afirmacion_sin_borrado BEFORE DELETE ON verificacion.afirmacion
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- La serie existe y está aprobada.
CREATE FUNCTION verificacion.verificacion_serie_existe() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.codigo_serie IS NOT NULL AND NOT oficial.serie_aprobada(NEW.codigo_serie) THEN
        RAISE EXCEPTION 'serie_no_aprobada: la serie % no existe o no está aprobada', NEW.codigo_serie;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER verificacion_serie_existe BEFORE INSERT ON verificacion.verificacion
    FOR EACH ROW EXECUTE FUNCTION verificacion.verificacion_serie_existe();

-- La evidencia es una observación vigente y aceptada (nunca una en cuarentena).
CREATE FUNCTION verificacion.evidencia_observacion_aceptada() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT oficial.esta_aceptada(NEW.observacion_id) THEN
        RAISE EXCEPTION 'evidencia_no_aceptada: la observación % no es la versión vigente aceptada', NEW.observacion_id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER evidencia_observacion_aceptada BEFORE INSERT ON verificacion.evidencia
    FOR EACH ROW EXECUTE FUNCTION verificacion.evidencia_observacion_aceptada();

-- Diferido: al confirmar, una conclusión con dato comparable tiene su evidencia citada.
CREATE FUNCTION verificacion.verificacion_tiene_evidencia() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.conclusion <> 'sin_dato_comparable' AND NOT EXISTS (
        SELECT 1 FROM verificacion.evidencia WHERE verificacion_id = NEW.id AND rol = 'citada') THEN
        RAISE EXCEPTION 'sin_evidencia: la conclusión % no tiene una observación oficial citada', NEW.conclusion;
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER verificacion_tiene_evidencia AFTER INSERT ON verificacion.verificacion
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION verificacion.verificacion_tiene_evidencia();

-- Diferido: una explicación validada no tiene cifras fuera de la evidencia (decisión 12).
CREATE FUNCTION verificacion.explicacion_cifras_respaldadas() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_sobrantes numeric[];
BEGIN
    IF NEW.explicacion_validada THEN
        SELECT array_agg(c) INTO v_sobrantes
        FROM unnest(util.cifras_en_texto(NEW.explicacion)) AS c
        WHERE c <> ALL (verificacion.cifras_permitidas(NEW.id));
        IF v_sobrantes IS NOT NULL THEN
            RAISE EXCEPTION 'cifra_sin_respaldo: la explicación usa % y no está en la evidencia', v_sobrantes;
        END IF;
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER explicacion_cifras_respaldadas AFTER INSERT ON verificacion.verificacion
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION verificacion.explicacion_cifras_respaldadas();

-- Solo un verificador o un administrador revisa.
CREATE FUNCTION verificacion.revision_por_verificador() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(social.rol_usuario(NEW.revisor_id), '') NOT IN ('verificador', 'admin') THEN
        RAISE EXCEPTION 'sin_permiso: solo un verificador o un administrador revisa verificaciones';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER revision_por_verificador BEFORE INSERT ON verificacion.revision_humana
    FOR EACH ROW EXECUTE FUNCTION verificacion.revision_por_verificador();

-- Cada verificación nueva va al grafo (relación VERIFICADA_CON).
CREATE FUNCTION verificacion.emitir_verificacion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    a verificacion.afirmacion;
BEGIN
    SELECT * INTO a FROM verificacion.afirmacion WHERE id = NEW.afirmacion_id;
    INSERT INTO verificacion.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos)
    VALUES ('verificacion', NEW.id::text, 'verificacion_publicada',
            jsonb_build_object('verificacion', NEW.id, 'afirmacion', a.id, 'publicacion', a.publicacion_id,
                               'declaracion', a.declaracion_id, 'declaracion_reportada', a.declaracion_reportada_id,
                               'serie', NEW.codigo_serie, 'indicador', a.codigo_indicador,
                               'conclusion', NEW.conclusion, 'version', NEW.version));
    RETURN NULL;
END;
$$;
CREATE TRIGGER verificacion_salida AFTER INSERT ON verificacion.verificacion
    FOR EACH ROW EXECUTE FUNCTION verificacion.emitir_verificacion();

CREATE FUNCTION verificacion.avisar_evento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('evento_salida', 'verificacion');
    RETURN NULL;
END;
$$;
CREATE TRIGGER evento_salida_aviso AFTER INSERT ON verificacion.evento_salida
    FOR EACH STATEMENT EXECUTE FUNCTION verificacion.avisar_evento();

CREATE TRIGGER verificacion_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.verificacion
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER evidencia_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.evidencia
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER resultado_prueba_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.resultado_prueba
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER revision_humana_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.revision_humana
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER evento_salida_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.evento_salida
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER entrega_evento_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.entrega_evento
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- =============================================================================
-- PARTE 5 · Procedimientos
-- =============================================================================

-- El filtro previo dijo que el texto no tiene cifras de los 8 indicadores, o la
-- extracción falló del todo: se registra para no dejarlo "pendiente" para siempre.
CREATE PROCEDURE verificacion.registrar_procesamiento(p_origen_tipo text, p_origen_id uuid, p_resultado text)
LANGUAGE sql AS $$
    INSERT INTO verificacion.procesamiento (origen_tipo, origen_id, resultado)
    VALUES (p_origen_tipo, p_origen_id, p_resultado)
    ON CONFLICT (origen_tipo, origen_id) DO UPDATE SET resultado = EXCLUDED.resultado, procesado_en = now();
$$;

-- Guarda las afirmaciones que extrajo la IA de un texto, todas o ninguna.
-- afirmaciones: [{"texto_citado": "...", "codigo_indicador": "unemployment", "variante": "tasa",
--                 "periodo_desde": "2026-09", "periodo_hasta": "2026-09", "territorio": "national",
--                 "valor_dicho": 8.2, "unidad_dicha": "%", "comparacion": "nivel", "confianza": 0.9}]
CREATE PROCEDURE verificacion.registrar_afirmaciones(p_origen_tipo text, p_origen_id uuid, p_trabajo_ia_id uuid,
                                                     p_afirmaciones jsonb, INOUT p_guardadas int)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO verificacion.afirmacion (
        publicacion_id, declaracion_id, declaracion_reportada_id, posicion, texto_citado, codigo_indicador,
        variante, periodo_desde, periodo_hasta, territorio, valor_dicho, unidad_dicha, comparacion,
        confianza_extraccion, trabajo_ia_id)
    SELECT CASE WHEN p_origen_tipo = 'publicacion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion' THEN p_origen_id END,
           CASE WHEN p_origen_tipo = 'declaracion_reportada' THEN p_origen_id END,
           n, f->>'texto_citado', f->>'codigo_indicador', f->>'variante', f->>'periodo_desde', f->>'periodo_hasta',
           f->>'territorio', (f->>'valor_dicho')::numeric, f->>'unidad_dicha', f->>'comparacion',
           (f->>'confianza')::numeric, p_trabajo_ia_id
    FROM jsonb_array_elements(p_afirmaciones) WITH ORDINALITY AS x(f, n);
    GET DIAGNOSTICS p_guardadas = ROW_COUNT;
    CALL verificacion.registrar_procesamiento(p_origen_tipo, p_origen_id,
        CASE WHEN p_guardadas > 0 THEN 'con_afirmaciones' ELSE 'sin_afirmaciones' END);
END;
$$;
COMMENT ON PROCEDURE verificacion.registrar_afirmaciones(text, uuid, uuid, jsonb, int)
    IS 'Guarda las afirmaciones extraídas de un texto y marca el texto como procesado';

-- Guarda una verificación nueva (versión siguiente) con su evidencia y sus pruebas.
-- Los triggers diferidos revisan al confirmar que haya evidencia y que la explicación
-- no tenga cifras sin respaldo; si no, se deshace todo.
CREATE PROCEDURE verificacion.registrar_verificacion(
    p_afirmacion_id uuid, p_codigo_serie text, p_conclusion text, p_explicacion text,
    p_explicacion_validada boolean, p_version_motor text,
    p_evidencias jsonb, p_pruebas jsonb, INOUT p_verificacion_id uuid)
LANGUAGE plpgsql AS $$
DECLARE
    v_version smallint;
BEGIN
    -- Bloquear la afirmación: dos verificaciones simultáneas no toman el mismo número de versión.
    PERFORM 1 FROM verificacion.afirmacion WHERE id = p_afirmacion_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'afirmacion_inexistente: la afirmación % no existe', p_afirmacion_id;
    END IF;

    SELECT coalesce(max(version), 0) + 1 INTO v_version
    FROM verificacion.verificacion WHERE afirmacion_id = p_afirmacion_id;

    INSERT INTO verificacion.verificacion (afirmacion_id, version, codigo_serie, conclusion, explicacion,
                                           explicacion_validada, version_motor)
    VALUES (p_afirmacion_id, v_version, p_codigo_serie, p_conclusion, p_explicacion,
            p_explicacion_validada, p_version_motor)
    RETURNING id INTO p_verificacion_id;

    INSERT INTO verificacion.evidencia (verificacion_id, observacion_id, rol)
    SELECT p_verificacion_id, (e->>'observacion_id')::uuid, e->>'rol'
    FROM jsonb_array_elements(coalesce(p_evidencias, '[]')) AS e;

    INSERT INTO verificacion.resultado_prueba (verificacion_id, codigo_prueba, resultado, detalle)
    SELECT p_verificacion_id, r->>'codigo', r->>'resultado', r->>'detalle'
    FROM jsonb_array_elements(coalesce(p_pruebas, '[]')) AS r;

    UPDATE verificacion.afirmacion
    SET estado = CASE WHEN p_conclusion = 'sin_dato_comparable' THEN 'no_verificable' ELSE 'verificada' END
    WHERE id = p_afirmacion_id;
END;
$$;
COMMENT ON PROCEDURE verificacion.registrar_verificacion(uuid, text, text, text, boolean, text, jsonb, jsonb, uuid)
    IS 'Guarda la versión siguiente de la verificación de una afirmación, con evidencia y pruebas';

-- Revisión humana. "corregida" deja la afirmación en revisión hasta que llegue la
-- versión corregida por registrar_verificacion.
CREATE PROCEDURE verificacion.registrar_revision(p_verificacion_id uuid, p_revisor_id uuid, p_decision text, p_motivo text)
LANGUAGE plpgsql AS $$
DECLARE
    v_afirmacion uuid;
BEGIN
    SELECT afirmacion_id INTO v_afirmacion FROM verificacion.verificacion WHERE id = p_verificacion_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'verificacion_inexistente: la verificación % no existe', p_verificacion_id;
    END IF;
    PERFORM 1 FROM verificacion.afirmacion WHERE id = v_afirmacion FOR UPDATE;
    INSERT INTO verificacion.revision_humana (verificacion_id, revisor_id, decision, motivo)
    VALUES (p_verificacion_id, p_revisor_id, p_decision, p_motivo);
    IF p_decision = 'corregida' THEN
        UPDATE verificacion.afirmacion SET estado = 'requiere_revision' WHERE id = v_afirmacion;
    END IF;
END;
$$;

CREATE PROCEDURE verificacion.marcar_entregados(p_consumidor text, p_eventos bigint[])
LANGUAGE sql AS $$
    INSERT INTO verificacion.entrega_evento (evento_id, consumidor)
    SELECT unnest(p_eventos), p_consumidor
    ON CONFLICT DO NOTHING;
$$;
