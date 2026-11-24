"""Vistas de lectura (migración 0039): existen, cada servicio lee solo las suyas y cuentan bien.

Reutiliza las ayudas de las pruebas de cada esquema para armar los datos.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.test_comunidades import comunidad, cuenta, publicar
from tests.test_temas import articulos, medio, registrar_temas
from tests.test_verificacion import afirmar, oficial, publicacion, verificar  # noqa: F401 (oficial y publicacion son fixtures)

VISTAS = {
    "oficial.ultimo_dato_serie": ("v", "svc_oficial"),
    "social.perfil_publico": ("v", "svc_social"),
    "social.actividad_comunidad": ("v", "svc_social"),
    "verificacion.conclusiones_por_indicador": ("m", "svc_verificacion"),
    "temas.cobertura_por_medio": ("v", "svc_temas"),
}
SERVICIOS = ["svc_oficial", "svc_social", "svc_verificacion", "svc_temas", "svc_ia", "svc_grafo"]


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c
        c.execute(
            "TRUNCATE social.cambio_rol, verificacion.entrega_evento, verificacion.evento_salida, verificacion.revision_humana,"
            " verificacion.resultado_prueba, verificacion.evidencia, verificacion.verificacion,"
            " verificacion.afirmacion, verificacion.procesamiento,"
            " oficial.observacion, oficial.descarga, oficial.serie, oficial.indicador, oficial.fuente,"
            " temas.entrega_evento, temas.evento_salida, temas.declaracion_reportada, temas.tema_articulo,"
            " temas.tema, temas.articulo, temas.medio, social.figura_publica,"
            " social.usuario, social.publicacion, social.etiqueta, social.evento_salida, social.comunidad CASCADE")
        # TRUNCATE no dispara el trigger de inserción: la vista materializada se deja al día para la prueba siguiente.
        c.execute("REFRESH MATERIALIZED VIEW verificacion.conclusiones_por_indicador")


def test_the_five_views_exist_with_comment_and_only_their_service_reads_them(db):
    for vista, (tipo, servicio) in VISTAS.items():
        fila = db.execute("SELECT c.relkind::text, obj_description(c.oid, 'pg_class') FROM pg_class c"
                          " WHERE c.oid = to_regclass(%s)", (vista,)).fetchone()
        assert fila is not None, vista
        assert fila[0] == tipo and fila[1], vista
        for rol in SERVICIOS:
            puede = db.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", (rol, vista)).fetchone()[0]
            assert puede == (rol == servicio), (vista, rol)
            assert not db.execute("SELECT has_table_privilege(%s, %s, 'INSERT')", (rol, vista)).fetchone()[0]


def test_the_refresh_routine_is_not_callable_by_anyone_else(db):
    for rol in SERVICIOS + ["public"]:
        assert not db.execute("SELECT has_function_privilege(%s, 'verificacion.refrescar_conclusiones()', 'EXECUTE')",
                              (rol,)).fetchone()[0], rol


def test_last_official_data_point_ignores_quarantined_observations(db, oficial):
    # El fixture deja 2026-08 aceptada y 2026-09 en cuarentena: el último dato publicable es agosto.
    assert db.execute("SELECT ultimo_periodo, total_periodos FROM oficial.ultimo_dato_serie"
                      " WHERE codigo_serie = 'unemployment_rate_national'").fetchone() == ("2026-08", 1)


def test_public_profile_has_no_private_data_and_counts_visible_posts(db):
    columnas = {r[0] for r in db.execute("SELECT column_name FROM information_schema.columns"
                                         " WHERE table_schema = 'social' AND table_name = 'perfil_publico'")}
    assert not columnas & {"correo", "clave_hash"}
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    db.execute("CALL social.seguir(%s, %s)", (beto, ana))
    db.execute("CALL social.publicar(%s, 'Una opinión', NULL, NULL, NULL, NULL)", (ana,))
    assert db.execute("SELECT seguidores, seguidos, publicaciones FROM social.perfil_publico WHERE id = %s",
                      (ana,)).fetchone() == (1, 0, 1)
    # Lo mismo que la función que reemplaza en el perfil.
    assert db.execute("SELECT * FROM social.estadisticas_usuario(%s)", (ana,)).fetchone() == (1, 0, 1)


def test_community_activity_counts_visible_posts_and_last_one(db):
    ana = cuenta(db, "ana")
    vacia, activa = comunidad(db, ana, "Sin publicaciones"), comunidad(db, ana, "Con publicaciones")
    publicar(db, ana, activa)
    ultima = publicar(db, ana, activa, "Otra opinión")
    filas = {f[0]: f[1:] for f in db.execute("SELECT comunidad_id, total_integrantes, total_publicaciones,"
                                             " ultima_publicacion IS NOT NULL FROM social.actividad_comunidad")}
    assert filas[vacia] == (1, 0, False)
    assert filas[activa] == (1, 2, True)
    assert db.execute("SELECT ultima_publicacion = (SELECT creado_en FROM social.publicacion WHERE id = %s)"
                      " FROM social.actividad_comunidad WHERE comunidad_id = %s", (ultima, activa)).fetchone()[0]


def test_materialized_conclusions_refresh_after_each_verification_and_count_the_current_version(db, oficial, publicacion):
    contar = "SELECT conclusion, total FROM verificacion.conclusiones_por_indicador WHERE codigo_indicador = 'unemployment'"
    assert db.execute(contar).fetchall() == []
    a = afirmar(db, publicacion)
    verificar(db, a, [oficial["2026-08"]], conclusion="se_debilita")
    assert db.execute(contar).fetchall() == [("se_debilita", 1)]          # se refrescó sola
    verificar(db, a, [oficial["2026-08"]], conclusion="se_invierte")
    assert db.execute(contar).fetchall() == [("se_invierte", 1)]          # solo cuenta la versión vigente


def test_a_failed_verification_does_not_change_the_materialized_view(db, oficial, publicacion):
    a = afirmar(db, publicacion)
    verificar(db, a, [oficial["2026-08"]], conclusion="se_debilita")
    with pytest.raises(psycopg.errors.RaiseException):                   # cifra que no está en la evidencia
        verificar(db, a, [oficial["2026-08"]], conclusion="se_invierte", explicacion="El dato oficial es 12,7 %.")
    assert db.execute("SELECT conclusion, total FROM verificacion.conclusiones_por_indicador"
                      " WHERE codigo_indicador = 'unemployment'").fetchall() == [("se_debilita", 1)]


def test_outlet_coverage_counts_articles_and_topics_of_the_current_window(db):
    ids = {n: medio(db, n) for n in ("medio_a", "medio_b", "medio_c", "medio_d")}
    reforma = [articulos(db, ids[n], ("La reforma avanza", "Debate en el Congreso"))[0] for n in ("medio_a", "medio_b", "medio_c")]
    registrar_temas(db, [{"titulo": "Reforma tributaria", "etiqueta": "reforma", "articulos": [str(x) for x in reforma]}])
    filas = {f[0]: f[1:] for f in db.execute("SELECT nombre, articulos_totales, articulos_ventana, temas_ventana"
                                             " FROM temas.cobertura_por_medio")}
    assert filas["medio_a"] == (1, 1, 1)
    assert filas["medio_d"] == (0, 0, 0)                                  # medio sin artículos: aparece en cero
