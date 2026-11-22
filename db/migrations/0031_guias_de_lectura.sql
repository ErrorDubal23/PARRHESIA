-- 0031 · Guías de lectura (decisión 34): cada análisis responde qué pasa con el dato, por qué y cómo
-- comprobarlo uno mismo, también cuando no hay dato comparable.
--
-- Capa 1 (reglas, sin IA): motivos registrados de "sin dato comparable", un catálogo curado de consejos
-- (por motivo, por trampa encontrada, por conclusión y por estado) y los enlaces oficiales de consulta.
-- Capa 2 (IA con doble control): una redacción natural de la guía. La base exige que no tenga cifras ni
-- palabras de juicio, y solo se publica si un segundo modelo, de otro proveedor, la juzga neutral.
-- Capa 3: verificaciones relacionadas de otros medios (Google Fact Check Tools). Se guardan el medio, el
-- título y el enlace, NUNCA su calificación: Parrhesia no dice verdadero o falso.
-- La guía nunca lleva cifras: las cifras están en la conclusión, que sale de la base y de reglas fijas.

-- =============================================================================
-- Capa 1 · Motivos, consejos y fuentes de consulta
-- =============================================================================

CREATE TABLE verificacion.motivo_sin_dato (
    codigo       text NOT NULL,
    descripcion  text NOT NULL,
    CONSTRAINT motivo_sin_dato_pkey PRIMARY KEY (codigo),
    CONSTRAINT motivo_sin_dato_codigo_valido CHECK (codigo ~ '^[a-z_]{3,40}$')
);
COMMENT ON TABLE verificacion.motivo_sin_dato IS 'Por qué el motor no encontró un dato comparable (lo decide el motor de reglas)';

INSERT INTO verificacion.motivo_sin_dato (codigo, descripcion) VALUES
    ('sin_cifra_indicador',   'La afirmación no tiene una cifra sobre uno de los indicadores registrados.'),
    ('variante_no_dicha',     'El texto no dice qué variación del indicador cita.'),
    ('variante_sin_serie',    'No hay una serie oficial registrada para esa variante del indicador.'),
    ('territorio_no_nacional','Solo hay series oficiales registradas para el total nacional.'),
    ('cambio_no_publicado',   'La fuente oficial no publica ese cambio; calcularlo no está permitido en esta versión.'),
    ('periodo_no_dicho',      'El texto no dice a qué periodo corresponde la cifra.'),
    ('indicador_sin_serie',   'No hay una serie oficial aprobada para ese indicador.'),
    ('total_anual_calculado', 'La serie oficial es mensual y el texto habla del año completo; sumarla o promediarla sería un cálculo propio.'),
    ('periodo_sin_dato',      'No hay un dato oficial aceptado para ese periodo en las series registradas.');

-- El motivo queda en la verificación (solo inserción, como el resto de la verificación).
ALTER TABLE verificacion.verificacion
    ADD COLUMN motivo_sin_dato text,
    ADD CONSTRAINT verificacion_motivo_sin_dato_fkey FOREIGN KEY (motivo_sin_dato) REFERENCES verificacion.motivo_sin_dato (codigo),
    ADD CONSTRAINT verificacion_motivo_solo_sin_dato CHECK (motivo_sin_dato IS NULL OR conclusion = 'sin_dato_comparable');

-- Consejos curados por el equipo: "Para entenderlo" (sin cifras) y "Compruébalo tú" (pasos concretos).
CREATE TABLE verificacion.consejo (
    origen           text   NOT NULL,     -- motivo | prueba | conclusion | estado | general
    referencia       text   NOT NULL,     -- el código del motivo, la prueba, la conclusión o el estado
    para_entenderlo  text   NOT NULL,
    pasos            text[] NOT NULL,
    CONSTRAINT consejo_pkey PRIMARY KEY (origen, referencia),
    CONSTRAINT consejo_origen_valido CHECK (origen IN ('motivo', 'prueba', 'conclusion', 'estado', 'general')),
    CONSTRAINT consejo_sin_cifras CHECK (para_entenderlo !~ '[0-9]'),
    CONSTRAINT consejo_pasos_validos CHECK (cardinality(pasos) BETWEEN 1 AND 4 AND array_position(pasos, NULL) IS NULL),
    CONSTRAINT consejo_breve CHECK (length(para_entenderlo) BETWEEN 20 AND 400)
);
COMMENT ON TABLE verificacion.consejo IS 'Consejos de lectura por motivo, trampa, conclusión o estado; neutrales y sin cifras';

INSERT INTO verificacion.consejo (origen, referencia, para_entenderlo, pasos) VALUES
    ('motivo', 'sin_cifra_indicador',
     'La frase no trae una cifra de los indicadores que se verifican aquí, así que no hay nada que comparar con un dato oficial.',
     ARRAY['Si el texto menciona un dato, busca de dónde sale antes de compartirlo.']),
    ('motivo', 'variante_no_dicha',
     'La inflación se publica de varias formas: la del mes, la de lo corrido del año y la de doce meses. Cada una da una cifra distinta, y sin saber cuál se cita no se puede comparar.',
     ARRAY['Busca si el texto dice «anual», «mensual» o «en lo corrido del año».',
           'En el boletín del IPC del DANE las tres variaciones aparecen juntas: compara con la que corresponda.']),
    ('motivo', 'variante_sin_serie',
     'Esa forma de medir el indicador todavía no está entre las series oficiales registradas en Parrhesia.',
     ARRAY['Revisa si la fuente oficial publica esa misma medida y con qué nombre.',
           'Si la encuentras, compara con el mismo periodo que dice el texto.']),
    ('motivo', 'territorio_no_nacional',
     'Las cifras de una ciudad o un departamento se miden aparte del total del país y no se comparan con él.',
     ARRAY['Busca en la fuente oficial la tabla por ciudades o departamentos.',
           'Fíjate si el dato de la ciudad es de un mes o de un trimestre móvil: el texto y la tabla deben hablar del mismo periodo.']),
    ('motivo', 'cambio_no_publicado',
     'La cifra es un cambio (cuánto subió o bajó), no el valor del indicador. Calcular un cambio exige elegir contra qué periodo, y esa elección puede cambiar lo que parece decir el dato.',
     ARRAY['Pregunta frente a qué mes o año se mide el cambio.',
           'Busca el valor oficial de los dos periodos y fíjate si el cambio es en puntos o en porcentaje: no es lo mismo.',
           'Mira varios periodos: un cambio puede verse grande o pequeño según con qué se compare.']),
    ('motivo', 'periodo_no_dicho',
     'Una cifra sin fecha no se puede comparar: el mismo indicador cambia de un mes a otro.',
     ARRAY['Busca de qué mes o año habla la cifra; a veces está en la fuente que se cita.',
           'Si no aparece, pregunta a quien la publicó a qué periodo corresponde.']),
    ('motivo', 'indicador_sin_serie',
     'Todavía no hay datos oficiales aceptados de ese indicador en Parrhesia, así que no se hace la comparación.',
     ARRAY['Consulta directamente la fuente oficial del indicador.',
           'Fíjate en la fecha de corte del dato y en si es provisional.']),
    ('motivo', 'total_anual_calculado',
     'La fuente publica el dato mes a mes; el total del año exigiría sumar o promediar, y ese cálculo no lo publica la fuente.',
     ARRAY['Busca si la fuente publica un total anual con ese mismo nombre.',
           'Si alguien sumó los meses, revisa que estén todos y que sean del mismo año.']),
    ('motivo', 'periodo_sin_dato',
     'La fuente todavía no ha publicado un dato aceptado para ese periodo, o el que hay está en revisión.',
     ARRAY['Revisa en la fuente oficial cuándo se publica el siguiente dato.',
           'Si el periodo es muy reciente, la cifra puede venir de una estimación y no del dato oficial.']),
    ('prueba', 'variante_equivocada',
     'Un mismo indicador se publica de varias formas. Una cifra correcta en una forma da otra impresión si se presenta como si fuera otra.',
     ARRAY['Verifica que la cifra sea de la misma variación que dice el texto: mensual, anual o en lo corrido del año.']),
    ('prueba', 'periodo_limitado',
     'Elegir con qué periodo se compara puede hacer que un dato parezca subir o bajar. Mirar varios periodos da el cuadro completo.',
     ARRAY['Compara con el mes anterior y con el mismo mes del año anterior.',
           'Mira la gráfica de la serie: ¿la tendencia es la que sugiere el texto?']),
    ('prueba', 'dato_provisional',
     'Algunos datos oficiales se publican primero como provisionales y se ajustan después.',
     ARRAY['Revisa si la fuente marca el dato como provisional y cuándo queda definitivo.']),
    ('prueba', 'nota_serie',
     'La fuente dejó una nota sobre ese periodo (un ajuste, un cambio de método o un hecho excepcional) que cambia cómo se lee el dato.',
     ARRAY['Lee la nota oficial en la ficha del dato antes de sacar conclusiones.']),
    ('prueba', 'nominal_vs_real',
     'Un valor en pesos de distintos años no se compara directamente: la inflación cambia lo que vale el dinero.',
     ARRAY['Pregunta si la cifra está en pesos de cada año o descontando la inflación.']),
    ('prueba', 'fuente_distinta',
     'La cifra puede venir de otra entidad, con otro método o con otra definición.',
     ARRAY['Busca qué entidad publicó la cifra y si mide lo mismo que la fuente oficial.']),
    ('conclusion', 'se_invierte',
     'La cifra puede ser correcta y aun así la dirección (subió o bajó) no coincide con lo que muestran los datos oficiales.',
     ARRAY['Busca el dato del periodo anterior y compáralo tú mismo: ¿subió o bajó?']),
    ('conclusion', 'se_sostiene',
     'La cifra coincide con el dato oficial. Aun así, una cifra exacta puede contar solo una parte de la historia.',
     ARRAY['Mira la serie completa para ver si ese dato es habitual o excepcional.']),
    ('estado', 'en_revision',
     'Las dos lecturas automáticas no coincidieron o la cifra es ambigua, así que una persona del equipo la revisa. Mientras tanto no hay conclusión.',
     ARRAY['Busca la fuente que cita el texto y el periodo exacto de la cifra.',
           'Compara con la fuente oficial del indicador.']),
    ('general', 'antes_de_compartir',
     'Antes de compartir un dato vale la pena detenerse un momento: ¿quién lo dice, de dónde sale y qué dicen otras fuentes?',
     ARRAY['Detente: no compartas solo por el titular.',
           'Busca la fuente original de la cifra, no una captura o un resumen.',
           'Mira qué dicen otros medios y la fuente oficial sobre el mismo dato.']),
    ('general', 'leer_tema',
     'Un tema del día reúne lo que publicaron varios medios. Que muchos medios hablen de algo no dice si es cierto ni si es importante: dice que se está cubriendo.',
     ARRAY['Lee el mismo hecho en al menos dos medios distintos y compara qué cuenta cada uno.',
           'Distingue lo que se sabe, con su fuente, de lo que se opina o se supone.',
           'Si aparece una cifra, busca de qué entidad oficial sale y de qué periodo es.',
           'Fíjate en la fecha: una noticia vieja puede circular como si fuera nueva.']);

-- Dónde consultar cada indicador. La curan personas; la IA nunca escribe un enlace.
CREATE TABLE oficial.consulta_fuente (
    id                uuid    NOT NULL DEFAULT gen_random_uuid(),
    codigo_indicador  text    NOT NULL,
    orden             smallint NOT NULL DEFAULT 1,
    nombre            text    NOT NULL,
    url               text    NOT NULL,
    como_leer         text    NOT NULL,
    CONSTRAINT consulta_fuente_pkey PRIMARY KEY (id),
    CONSTRAINT consulta_fuente_indicador_orden_key UNIQUE (codigo_indicador, orden),
    CONSTRAINT consulta_fuente_indicador_valido CHECK (codigo_indicador IN (
        'inflation', 'unemployment', 'minimum_wage', 'public_debt', 'homicides', 'theft', 'extortion', 'kidnapping')),
    -- Solo sitios oficiales colombianos, por https.
    CONSTRAINT consulta_fuente_url_oficial CHECK (url ~ '^https://([a-z0-9-]+\.)*gov\.co(/|$)'),
    CONSTRAINT consulta_fuente_como_leer CHECK (length(como_leer) BETWEEN 20 AND 400)
);
COMMENT ON TABLE oficial.consulta_fuente IS 'Páginas oficiales donde una persona puede comprobar cada indicador por su cuenta';

INSERT INTO oficial.consulta_fuente (codigo_indicador, orden, nombre, url, como_leer) VALUES
    ('inflation', 1, 'DANE · Índice de Precios al Consumidor (IPC)',
     'https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc',
     'El boletín de cada mes trae la variación del mes, la de lo corrido del año y la de doce meses; el anexo trae la serie histórica.'),
    ('unemployment', 1, 'DANE · Gran Encuesta Integrada de Hogares (empleo y desempleo)',
     'https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo',
     'El boletín trae la tasa nacional del mes; los anexos traen ciudades y áreas metropolitanas, a veces en trimestre móvil.'),
    ('minimum_wage', 1, 'Banco de la República · Estadísticas (SUAMECA)',
     'https://suameca.banrep.gov.co',
     'Busca «salario mínimo»: el valor de cada año lo fija un decreto del Gobierno y la serie muestra todos los años.'),
    ('public_debt', 1, 'Ministerio de Hacienda · Deuda pública',
     'https://www.irc.gov.co/deuda-publica',
     'Fíjate si la cifra es deuda bruta o neta, del Gobierno Nacional Central o de todo el sector público, y si está en pesos o como parte del PIB.'),
    ('homicides', 1, 'Policía Nacional · Estadística delictiva',
     'https://www.policia.gov.co/estadistica-delictiva',
     'Los cuadros traen los casos por mes y por departamento; los meses más recientes pueden cambiar mientras se consolidan.'),
    ('theft', 1, 'Policía Nacional · Estadística delictiva',
     'https://www.policia.gov.co/estadistica-delictiva',
     'Hay varios tipos de hurto (a personas, a comercio, a residencias, de vehículos): revisa que la cifra sea del mismo tipo.'),
    ('extortion', 1, 'Policía Nacional · Estadística delictiva',
     'https://www.policia.gov.co/estadistica-delictiva',
     'Las cifras son casos denunciados: un cambio puede reflejar más o menos denuncias, no solo más o menos casos.'),
    ('kidnapping', 1, 'Policía Nacional · Estadística delictiva',
     'https://www.policia.gov.co/estadistica-delictiva',
     'Revisa si la cifra es de secuestro simple o extorsivo, y de qué periodo.');

-- =============================================================================
-- Capa 2 · Redacción con IA, juzgada por otro modelo
-- =============================================================================

ALTER TABLE ia.trabajo DROP CONSTRAINT trabajo_tipo_valido;
ALTER TABLE ia.trabajo ADD CONSTRAINT trabajo_tipo_valido CHECK (tipo IN
    ('extraer_afirmaciones', 'redactar_explicacion', 'agrupar_temas', 'extraer_declaraciones',
     'redactar_guia', 'juzgar_neutralidad'));

CREATE TABLE verificacion.guia_redactada (
    afirmacion_id    uuid        NOT NULL,
    version_prompt   text        NOT NULL,
    texto            text        NOT NULL,
    trabajo_ia_id    uuid        NOT NULL,          -- lógica -> ia.trabajo (redacción)
    trabajo_juez_id  uuid,                          -- lógica -> ia.trabajo (juez de neutralidad)
    neutral          boolean,                       -- veredicto del juez; NULL = el juez no respondió
    motivo_juez      text,
    creada_en        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT guia_redactada_pkey PRIMARY KEY (afirmacion_id, version_prompt),
    CONSTRAINT guia_redactada_afirmacion_id_fkey FOREIGN KEY (afirmacion_id) REFERENCES verificacion.afirmacion (id),
    -- La guía nunca lleva cifras ni palabras de juicio: se revisa aquí, además de en el servicio.
    CONSTRAINT guia_redactada_sin_cifras CHECK (texto !~ '[0-9]'),
    CONSTRAINT guia_redactada_sin_juicios CHECK (texto !~* '(mentir|mentira|falso|falsa|enga[ñn]|manipul|propaganda|desinform|miente)'),
    CONSTRAINT guia_redactada_breve CHECK (length(texto) BETWEEN 40 AND 700),
    CONSTRAINT guia_redactada_juez_completo CHECK (neutral IS NULL OR trabajo_juez_id IS NOT NULL)
);
COMMENT ON TABLE verificacion.guia_redactada IS 'Guía redactada por IA a partir de las reglas; solo se publica si el juez la consideró neutral. Solo inserción';
CREATE TRIGGER guia_redactada_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.guia_redactada
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

-- =============================================================================
-- Capa 3 · Verificaciones relacionadas de otros medios (sin su calificación)
-- =============================================================================

CREATE TABLE verificacion.consulta_externa (
    afirmacion_id  uuid        NOT NULL,
    consultada_en  timestamptz NOT NULL DEFAULT now(),
    total          smallint    NOT NULL,
    CONSTRAINT consulta_externa_pkey PRIMARY KEY (afirmacion_id),
    CONSTRAINT consulta_externa_afirmacion_id_fkey FOREIGN KEY (afirmacion_id) REFERENCES verificacion.afirmacion (id),
    CONSTRAINT consulta_externa_total_valido CHECK (total BETWEEN 0 AND 3)
);
CREATE TABLE verificacion.verificacion_externa (
    afirmacion_id  uuid     NOT NULL,
    posicion       smallint NOT NULL,
    medio          text     NOT NULL,
    titulo         text     NOT NULL,
    url            text     NOT NULL,
    publicada_en   date,
    CONSTRAINT verificacion_externa_pkey PRIMARY KEY (afirmacion_id, posicion),
    CONSTRAINT verificacion_externa_consulta_fkey FOREIGN KEY (afirmacion_id) REFERENCES verificacion.consulta_externa (afirmacion_id),
    CONSTRAINT verificacion_externa_posicion_valida CHECK (posicion BETWEEN 1 AND 3),
    CONSTRAINT verificacion_externa_url_valida CHECK (url ~ '^https://'),
    CONSTRAINT verificacion_externa_textos CHECK (length(medio) BETWEEN 2 AND 120 AND length(titulo) BETWEEN 3 AND 300)
);
COMMENT ON TABLE verificacion.verificacion_externa IS 'Verificación relacionada publicada por otro medio: medio, título y enlace; nunca su calificación';
CREATE TRIGGER consulta_externa_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.consulta_externa
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();
CREATE TRIGGER verificacion_externa_solo_insercion BEFORE UPDATE OR DELETE ON verificacion.verificacion_externa
    FOR EACH ROW EXECUTE FUNCTION util.prohibir_cambios();

CREATE PROCEDURE verificacion.registrar_consulta_externa(p_afirmacion_id uuid, p_resultados jsonb)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO verificacion.consulta_externa (afirmacion_id, total)
    VALUES (p_afirmacion_id, least(jsonb_array_length(coalesce(p_resultados, '[]')), 3))
    ON CONFLICT (afirmacion_id) DO NOTHING;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    INSERT INTO verificacion.verificacion_externa (afirmacion_id, posicion, medio, titulo, url, publicada_en)
    SELECT p_afirmacion_id, n, r->>'medio', r->>'titulo', r->>'url', (r->>'publicada_en')::date
    FROM jsonb_array_elements(coalesce(p_resultados, '[]')) WITH ORDINALITY AS x(r, n)
    WHERE n <= 3;
END;
$$;

-- =============================================================================
-- La verificación guarda ahora su motivo
-- =============================================================================

CREATE PROCEDURE verificacion.registrar_verificacion(
    p_afirmacion_id uuid, p_codigo_serie text, p_conclusion text, p_explicacion text,
    p_explicacion_validada boolean, p_version_motor text,
    p_evidencias jsonb, p_pruebas jsonb, p_motivo_sin_dato text, INOUT p_verificacion_id uuid)
LANGUAGE plpgsql AS $$
DECLARE
    v_version smallint;
BEGIN
    PERFORM 1 FROM verificacion.afirmacion WHERE id = p_afirmacion_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'afirmacion_inexistente: la afirmación % no existe', p_afirmacion_id;
    END IF;

    SELECT coalesce(max(version), 0) + 1 INTO v_version
    FROM verificacion.verificacion WHERE afirmacion_id = p_afirmacion_id;

    INSERT INTO verificacion.verificacion (afirmacion_id, version, codigo_serie, conclusion, explicacion,
                                           explicacion_validada, version_motor, motivo_sin_dato)
    VALUES (p_afirmacion_id, v_version, p_codigo_serie, p_conclusion, p_explicacion,
            p_explicacion_validada, p_version_motor, p_motivo_sin_dato)
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
COMMENT ON PROCEDURE verificacion.registrar_verificacion(uuid, text, text, text, boolean, text, jsonb, jsonb, text, uuid)
    IS 'Guarda la versión siguiente de la verificación, con evidencia, pruebas y el motivo si no hay dato comparable (0031)';

-- =============================================================================
-- La guía completa de una afirmación
-- =============================================================================

CREATE FUNCTION verificacion.guia_de(p_afirmacion_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    WITH a AS (SELECT * FROM verificacion.afirmacion WHERE id = p_afirmacion_id),
    v AS (SELECT * FROM verificacion.verificacion WHERE afirmacion_id = p_afirmacion_id ORDER BY version DESC LIMIT 1),
    claves AS (
        SELECT 'estado' AS origen, 'en_revision' AS referencia, 0 AS orden FROM a WHERE a.estado = 'requiere_revision'
        UNION ALL SELECT 'motivo', v.motivo_sin_dato, 1 FROM v WHERE v.motivo_sin_dato IS NOT NULL
        UNION ALL SELECT 'conclusion', v.conclusion, 2 FROM v WHERE v.conclusion IN ('se_invierte', 'se_sostiene')
        UNION ALL SELECT 'prueba', r.codigo_prueba, 3 FROM v
                  JOIN verificacion.resultado_prueba r ON r.verificacion_id = v.id WHERE r.resultado = 'con_brecha'
        UNION ALL SELECT 'general', 'antes_de_compartir', 9)
    SELECT jsonb_build_object(
        'motivo', (SELECT m.descripcion FROM v JOIN verificacion.motivo_sin_dato m ON m.codigo = v.motivo_sin_dato),
        'consejos', coalesce((
            SELECT jsonb_agg(jsonb_build_object('origen', c.origen, 'codigo', c.referencia,
                                                'para_entenderlo', c.para_entenderlo, 'pasos', to_jsonb(c.pasos))
                             ORDER BY k.orden, c.referencia)
            FROM claves k JOIN verificacion.consejo c ON c.origen = k.origen AND c.referencia = k.referencia), '[]'),
        'fuentes', coalesce((
            SELECT jsonb_agg(jsonb_build_object('nombre', f.nombre, 'url', f.url, 'como_leer', f.como_leer) ORDER BY f.orden)
            FROM a JOIN oficial.consulta_fuente f ON f.codigo_indicador = a.codigo_indicador), '[]'),
        'redaccion', (SELECT g.texto FROM verificacion.guia_redactada g
                      WHERE g.afirmacion_id = p_afirmacion_id AND g.neutral ORDER BY g.creada_en DESC LIMIT 1),
        'otros_medios', coalesce((
            SELECT jsonb_agg(jsonb_build_object('medio', e.medio, 'titulo', e.titulo, 'url', e.url,
                                                'publicada_en', e.publicada_en) ORDER BY e.posicion)
            FROM verificacion.verificacion_externa e WHERE e.afirmacion_id = p_afirmacion_id), '[]'));
$$;
COMMENT ON FUNCTION verificacion.guia_de(uuid)
    IS 'Decisión 34: por qué (motivo y consejos), cómo comprobarlo (pasos y fuentes oficiales), la redacción neutral y verificaciones de otros medios';

-- Afirmaciones que aún no tienen guía redactada para una versión del prompt (vigentes o en revisión).
CREATE FUNCTION verificacion.afirmaciones_sin_guia(p_version text, p_limite int DEFAULT 20)
RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT a.id FROM verificacion.afirmacion a
    WHERE (a.estado IN ('verificada', 'no_verificable', 'requiere_revision'))
      AND a.creado_en > now() - interval '14 days'
      -- Solo textos que alguien puede leer: no se gasta IA en publicaciones retiradas.
      AND (a.publicacion_id IS NULL OR social.texto_para_verificar('publicacion', a.publicacion_id) IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM verificacion.guia_redactada g WHERE g.afirmacion_id = a.id AND g.version_prompt = p_version)
    ORDER BY a.creado_en DESC LIMIT p_limite;
$$;

GRANT SELECT ON oficial.consulta_fuente TO svc_oficial;
GRANT SELECT ON verificacion.motivo_sin_dato, verificacion.consejo TO svc_verificacion;
GRANT SELECT, INSERT ON verificacion.guia_redactada, verificacion.consulta_externa, verificacion.verificacion_externa TO svc_verificacion;
GRANT EXECUTE ON FUNCTION verificacion.guia_de(uuid), verificacion.afirmaciones_sin_guia(text, int) TO svc_verificacion;
GRANT EXECUTE ON PROCEDURE verificacion.registrar_consulta_externa(uuid, jsonb),
    verificacion.registrar_verificacion(uuid, text, text, text, boolean, text, jsonb, jsonb, text, uuid) TO svc_verificacion;
