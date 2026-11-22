-- 0020 · Las tendencias de respaldo no cuentan lo publicado en comunidades privadas (T11).
--
-- Una etiqueta usada dentro de una comunidad privada no debe aparecer en las tendencias públicas:
-- revelaría de qué se habla adentro. Las tendencias del grafo aplican la misma regla (consultas.py).

CREATE OR REPLACE FUNCTION social.tendencias_basicas(p_desde timestamptz, p_hasta timestamptz)
RETURNS TABLE (etiqueta text, total_publicaciones bigint, total_autores bigint)
LANGUAGE sql STABLE AS $$
    SELECT e.nombre, count(DISTINCT p.id), count(DISTINCT p.autor_id)
    FROM social.etiqueta e
    JOIN social.publicacion_etiqueta pe ON pe.etiqueta_id = e.id
    JOIN social.publicacion p ON p.id = pe.publicacion_id
    JOIN social.usuario u ON u.id = p.autor_id
    LEFT JOIN social.comunidad c ON c.id = p.comunidad_id
    WHERE p.creado_en >= p_desde AND p.creado_en < p_hasta
      AND p.estado = 'visible'
      AND u.estado = 'activo'
      AND u.creado_en < p_desde - interval '7 days'          -- las cuentas nuevas no cuentan
      AND coalesce(c.privacidad, 'publica') = 'publica'      -- lo privado no sale de su comunidad
    GROUP BY e.nombre
    HAVING count(DISTINCT p.autor_id) >= 3
    ORDER BY count(DISTINCT p.autor_id) DESC, count(DISTINCT p.id) DESC, e.nombre
    LIMIT 10;
$$;
