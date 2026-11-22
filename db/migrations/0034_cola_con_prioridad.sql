-- 0034 · La cola de IA atiende primero lo que una persona está esperando, y la base elige el segundo lector.
--
-- Medido el 22 nov 2026 (ia.intento, últimos dos días): Groq responde en ~1,2 s por llamada y el plan gratuito de
-- OpenRouter en ~19 s, con 160 respuestas de límite alcanzado. La cola atendía por orden de llegada, así que las
-- guías y el juez de neutralidad (que también usan el segundo proveedor) competían con las cifras de una noticia
-- que alguien acababa de pedir analizar.
--
-- 1. ia.prioridad_trabajo: el orden de atención por tipo, en un solo lugar y con prueba.
-- 2. ia.tomar_trabajo: igual que en 0008 (SKIP LOCKED, proveedor exigido), pero primero por prioridad.
-- 3. ia.primer_proveedor_habilitado: el servicio de verificación pide "el primero de esta lista que tenga una
--    cuenta habilitada" (por ejemplo gemini y, si no hay, openrouter). Así un trabajo nunca se encola para un
--    proveedor sin cuenta, donde se quedaría esperando para siempre. Las llaves siguen fuera de la base: solo
--    se mira si hay una cuenta habilitada con ese alias.
-- Solo funciones: no cambia datos existentes.

-- 1 · Prioridad: 0 = alguien espera la conclusión; 1 = temas del día (proceso de fondo con su propio ritmo);
--     2 = lo que acompaña a una conclusión ya publicada (explicación, guía y juez).
CREATE FUNCTION ia.prioridad_trabajo(p_tipo text) RETURNS smallint
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_tipo
        WHEN 'extraer_afirmaciones' THEN 0
        WHEN 'extraer_declaraciones' THEN 1
        WHEN 'agrupar_temas' THEN 1
        ELSE 2
    END::smallint;
$$;
COMMENT ON FUNCTION ia.prioridad_trabajo(text)
    IS 'Orden de atención de la cola: 0 lo que una persona espera, 1 temas del día, 2 lo que acompaña a una conclusión';

-- 2 · Misma firma que en 0008: CREATE OR REPLACE conserva el permiso de svc_ia.
CREATE OR REPLACE FUNCTION ia.tomar_trabajo(p_tipos text[], p_proveedores text[]) RETURNS SETOF ia.trabajo
LANGUAGE sql VOLATILE AS $$
    UPDATE ia.trabajo t
    SET estado = 'en_curso',
        proximo_intento_en = now() + interval '5 minutes'
    WHERE t.id = (
        SELECT c.id FROM ia.trabajo c
        WHERE c.tipo = ANY (p_tipos)
          AND (c.proveedor IS NULL OR c.proveedor = ANY (p_proveedores))
          AND c.estado IN ('en_cola', 'en_curso')
          AND c.proximo_intento_en <= now()
        ORDER BY ia.prioridad_trabajo(c.tipo), c.proximo_intento_en
        FOR UPDATE SKIP LOCKED
        LIMIT 1)
    RETURNING t.*;
$$;
COMMENT ON FUNCTION ia.tomar_trabajo(text[], text[])
    IS 'Toma el trabajo listo de mayor prioridad de un proveedor disponible, sin chocar con otros trabajadores (SKIP LOCKED)';

-- 3 · El primero de la lista con una cuenta habilitada (aunque esté en pausa: la pausa es temporal y el
--     trabajo espera); nulo si ninguno tiene.
CREATE FUNCTION ia.primer_proveedor_habilitado(p_preferidos text[]) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT p.proveedor
    FROM unnest(p_preferidos) WITH ORDINALITY AS p(proveedor, orden)
    WHERE EXISTS (SELECT 1 FROM ia.credencial c WHERE c.proveedor = p.proveedor AND c.habilitada)
    ORDER BY p.orden
    LIMIT 1;
$$;
COMMENT ON FUNCTION ia.primer_proveedor_habilitado(text[])
    IS 'Primer proveedor de la lista con alguna cuenta habilitada; nulo si ninguno';

-- 0007 quitó el permiso por defecto.
GRANT EXECUTE ON FUNCTION ia.prioridad_trabajo(text) TO svc_ia;
GRANT EXECUTE ON FUNCTION ia.primer_proveedor_habilitado(text[]) TO svc_verificacion;
