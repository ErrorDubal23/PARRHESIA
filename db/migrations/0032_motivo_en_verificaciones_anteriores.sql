-- 0032 · Las verificaciones "sin dato comparable" anteriores a 0031 reciben su motivo.
--
-- La verificación es de solo inserción: no se edita. Se registra una versión nueva con la misma conclusión,
-- la misma explicación y las mismas pruebas, más el código del motivo, que se reconoce en la explicación que
-- el motor ya había guardado ("No hay dato comparable. <motivo>"). El historial muestra cómo se completó.
DO $$
DECLARE
    r record;
    v_id uuid;
    v_pruebas jsonb;
BEGIN
    FOR r IN
        SELECT v.*, m.codigo AS motivo
        FROM verificacion.afirmacion a
        CROSS JOIN LATERAL verificacion.verificacion_vigente(a.id) v
        JOIN verificacion.motivo_sin_dato m
          ON position(m.descripcion IN v.explicacion) > 0
          OR (m.codigo = 'periodo_sin_dato' AND v.explicacion LIKE '%No hay un dato oficial aceptado para el periodo%')
        WHERE v.conclusion = 'sin_dato_comparable' AND v.motivo_sin_dato IS NULL
    LOOP
        SELECT coalesce(jsonb_agg(jsonb_build_object('codigo', p.codigo_prueba, 'resultado', p.resultado,
                                                     'detalle', p.detalle)), '[]')
        INTO v_pruebas FROM verificacion.resultado_prueba p WHERE p.verificacion_id = r.id;
        CALL verificacion.registrar_verificacion(
            r.afirmacion_id, NULL, r.conclusion, r.explicacion, r.explicacion_validada, r.version_motor, '[]',
            v_pruebas, r.motivo, v_id);
    END LOOP;
END;
$$;
