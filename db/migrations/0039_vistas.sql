-- 0039 · Vistas de lectura (y una vista materializada)
--
-- Cinco consultas que los servicios repetían a mano pasan a ser vistas con nombre, documentadas y con su
-- permiso propio. Ninguna escribe ni cambia datos: solo nombran lecturas que ya existían.
--
--   1. oficial.ultimo_dato_serie              último periodo vigente y aceptado de cada serie aprobada
--   2. social.perfil_publico                  cada cuenta con sus conteos, sin correo ni datos privados
--   3. social.actividad_comunidad             integrantes, publicaciones y última actividad por comunidad
--   4. verificacion.conclusiones_por_indicador  (MATERIALIZADA) conclusiones vigentes por indicador
--   5. temas.cobertura_por_medio              artículos y temas de cada medio en la ventana actual
--
-- Las vistas corren con los permisos de su dueño (no security_invoker): cada servicio recibe SELECT sobre la
-- vista y no necesita permiso sobre las tablas que lee por dentro.

-- 1 · Último dato de cada serie ------------------------------------------------------------------------------
-- Misma regla de vigencia que oficial.observaciones_vigentes: por (periodo, territorio) manda la secuencia
-- mayor, y solo cuenta si esa versión está aceptada. Antes /v1/series tomaba max(periodo) sobre todas las
-- observaciones, incluidas las retiradas o en cuarentena.
CREATE VIEW oficial.ultimo_dato_serie AS
    WITH vigentes AS (
        SELECT DISTINCT ON (o.serie_id, o.periodo, o.territorio) o.serie_id, o.periodo, o.estado
        FROM oficial.observacion o
        ORDER BY o.serie_id, o.periodo, o.territorio, o.secuencia DESC)
    SELECT s.id AS serie_id, s.codigo AS codigo_serie, i.codigo AS codigo_indicador,
           max(v.periodo) AS ultimo_periodo,
           count(DISTINCT v.periodo) AS total_periodos
    FROM oficial.serie s
    JOIN oficial.indicador i ON i.id = s.indicador_id
    LEFT JOIN vigentes v ON v.serie_id = s.id AND v.estado = 'aceptada'
    WHERE s.aprobada
    GROUP BY s.id, s.codigo, i.codigo;
COMMENT ON VIEW oficial.ultimo_dato_serie IS
    'Cada serie aprobada con su último periodo vigente y aceptado, y cuántos periodos tiene';

-- 2 · Perfil público ------------------------------------------------------------------------------------------
-- Lo que cualquiera puede ver de una cuenta. No incluye correo, clave ni nada de la sesión.
CREATE VIEW social.perfil_publico AS
    SELECT u.id, u.nombre_usuario, u.nombre_visible, u.biografia, u.rol, u.estado, u.foto, u.creado_en,
           (SELECT count(*) FROM social.seguimiento s WHERE s.seguido_id = u.id) AS seguidores,
           (SELECT count(*) FROM social.seguimiento s WHERE s.seguidor_id = u.id) AS seguidos,
           (SELECT count(*) FROM social.publicacion p WHERE p.autor_id = u.id AND p.estado = 'visible') AS publicaciones
    FROM social.usuario u;
COMMENT ON VIEW social.perfil_publico IS
    'Datos públicos de cada cuenta con seguidores, seguidos y publicaciones visibles (sin correo ni clave)';

-- 3 · Actividad de cada comunidad -----------------------------------------------------------------------------
CREATE VIEW social.actividad_comunidad AS
    SELECT c.id AS comunidad_id, c.nombre, c.privacidad, c.total_integrantes,
           count(p.id) AS total_publicaciones,
           max(p.creado_en) AS ultima_publicacion
    FROM social.comunidad c
    LEFT JOIN social.publicacion p ON p.comunidad_id = c.id AND p.estado = 'visible'
    GROUP BY c.id, c.nombre, c.privacidad, c.total_integrantes;
COMMENT ON VIEW social.actividad_comunidad IS
    'Integrantes, publicaciones visibles y fecha de la última publicación de cada comunidad';

-- 4 · Conclusiones por indicador (vista materializada) ---------------------------------------------------------
-- Cuenta, por indicador, cuántas cifras verificadas quedaron en cada conclusión. Solo cuenta la versión
-- vigente (la mayor) de cada verificación. Es materializada porque recorre todas las verificaciones y se lee
-- mucho más de lo que cambia; se refresca sola después de cada verificación nueva (trigger de abajo).
CREATE MATERIALIZED VIEW verificacion.conclusiones_por_indicador AS
    WITH vigentes AS (
        SELECT DISTINCT ON (v.afirmacion_id) v.afirmacion_id, v.conclusion
        FROM verificacion.verificacion v
        ORDER BY v.afirmacion_id, v.version DESC)
    SELECT a.codigo_indicador, v.conclusion, count(*) AS total
    FROM vigentes v
    JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id
    GROUP BY a.codigo_indicador, v.conclusion;
COMMENT ON MATERIALIZED VIEW verificacion.conclusiones_por_indicador IS
    'Cuántas cifras verificadas (versión vigente) quedaron en cada conclusión, por indicador. Se refresca tras cada verificación';
-- Índice único: lo exige REFRESH ... CONCURRENTLY (deja leer la vista mientras se refresca).
CREATE UNIQUE INDEX conclusiones_por_indicador_uq
    ON verificacion.conclusiones_por_indicador (codigo_indicador, conclusion);

-- Refresco. SECURITY DEFINER: solo el dueño de la vista puede refrescarla, y el servicio de verificación
-- no necesita ser dueño. search_path vacío, como el resto de rutinas con SECURITY DEFINER.
CREATE FUNCTION verificacion.refrescar_conclusiones() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY verificacion.conclusiones_por_indicador;
    RETURN NULL;
END;
$$;
COMMENT ON FUNCTION verificacion.refrescar_conclusiones() IS
    'Refresca verificacion.conclusiones_por_indicador (la llama el trigger tras cada verificación nueva)';
REVOKE EXECUTE ON FUNCTION verificacion.refrescar_conclusiones() FROM PUBLIC;

-- Una vez por sentencia (no por fila): una verificación con varias filas refresca una sola vez.
CREATE TRIGGER verificacion_refresca_conclusiones
    AFTER INSERT ON verificacion.verificacion
    FOR EACH STATEMENT EXECUTE FUNCTION verificacion.refrescar_conclusiones();

-- 5 · Cobertura de cada medio ---------------------------------------------------------------------------------
-- La ventana actual es la del cálculo de temas más reciente (la misma que usa temas.temas_actuales).
CREATE VIEW temas.cobertura_por_medio AS
    WITH ventana AS (
        SELECT ventana_inicio, ventana_fin FROM temas.tema
        ORDER BY ventana_fin DESC, ventana_inicio DESC LIMIT 1)
    SELECT m.id AS medio_id, m.nombre, m.habilitado,
           count(DISTINCT a.id) AS articulos_totales,
           count(DISTINCT a.id) FILTER (WHERE a.publicado_en BETWEEN w.ventana_inicio AND w.ventana_fin)
               AS articulos_ventana,
           count(DISTINCT ta.tema_id) AS temas_ventana,
           max(a.publicado_en) AS ultimo_articulo
    FROM temas.medio m
    LEFT JOIN ventana w ON true
    LEFT JOIN temas.articulo a ON a.medio_id = m.id
    LEFT JOIN temas.tema_articulo ta ON ta.articulo_id = a.id
        AND ta.tema_id IN (SELECT t.id FROM temas.tema t
                           WHERE (t.ventana_inicio, t.ventana_fin) = (w.ventana_inicio, w.ventana_fin))
    GROUP BY m.id, m.nombre, m.habilitado;
COMMENT ON VIEW temas.cobertura_por_medio IS
    'Artículos de cada medio (en total y en la ventana actual), en cuántos temas actuales aparece y su último artículo';

-- Permisos: cada servicio lee solo las vistas de su esquema.
GRANT SELECT ON oficial.ultimo_dato_serie TO svc_oficial;
GRANT SELECT ON social.perfil_publico, social.actividad_comunidad TO svc_social;
GRANT SELECT ON verificacion.conclusiones_por_indicador TO svc_verificacion;
GRANT SELECT ON temas.cobertura_por_medio TO svc_temas;
