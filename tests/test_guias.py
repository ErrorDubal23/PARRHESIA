"""Guías de lectura (decisión 34, migración 0031): reglas en la base, sin cifras ni juicios."""

from __future__ import annotations

import psycopg
import pytest

from servicios.ia.formatos import SalidaInvalida, validar


@pytest.fixture
def pg(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c


def test_every_reason_and_every_robustness_check_has_a_guide(pg):
    sin_consejo = pg.execute(
        "SELECT codigo FROM verificacion.motivo_sin_dato m WHERE NOT EXISTS (SELECT 1 FROM verificacion.consejo c"
        " WHERE c.origen = 'motivo' AND c.referencia = m.codigo)"
        " UNION ALL SELECT codigo FROM verificacion.prueba_robustez p WHERE NOT EXISTS (SELECT 1 FROM verificacion.consejo c"
        " WHERE c.origen = 'prueba' AND c.referencia = p.codigo)").fetchall()
    assert sin_consejo == []
    indicadores = {r[0] for r in pg.execute("SELECT DISTINCT codigo_indicador FROM oficial.consulta_fuente")}
    assert indicadores == {"inflation", "unemployment", "minimum_wage", "public_debt", "homicides", "theft", "extortion",
                           "kidnapping"}


def test_advice_has_no_figures_and_sources_are_official(pg):
    with pytest.raises(psycopg.errors.CheckViolation, match="consejo_sin_cifras"):
        pg.execute("INSERT INTO verificacion.consejo VALUES ('general', 'x', 'La inflación fue de seis por ciento, o 6 %.', ARRAY['a'])")
    with pytest.raises(psycopg.errors.CheckViolation, match="consulta_fuente_url_oficial"):
        pg.execute("INSERT INTO oficial.consulta_fuente (codigo_indicador, orden, nombre, url, como_leer) VALUES"
                   " ('inflation', 9, 'Blog', 'https://un-blog.com/inflacion', 'Una explicación cualquiera de la inflación.')")


def test_a_written_guide_never_carries_figures_or_judgements():
    entrada = {}
    with pytest.raises(SalidaInvalida):
        validar("redactar_guia", '{"guia": "La inflación fue 6,3 % según el DANE, revisa el boletín del mes para comprobarlo."}', entrada)
    with pytest.raises(SalidaInvalida):
        validar("redactar_guia", '{"guia": "Esta cifra es falsa y busca engañar; revisa el boletín del DANE para comprobarlo tú."}', entrada)
    ok = validar("redactar_guia", '{"guia": "La cifra es de otra variación del indicador. Revisa en el boletín del DANE cuál se cita."}', entrada)
    assert ok["guia"].startswith("La cifra")
    assert validar("juzgar_neutralidad", '{"neutral": false, "agrega_hechos": true, "motivo": "toma partido"}', entrada)["neutral"] is False


def test_other_outlets_are_stored_without_their_rating(pg):
    columnas = {r[0] for r in pg.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'verificacion' AND table_name = 'verificacion_externa'")}
    assert columnas == {"afirmacion_id", "posicion", "medio", "titulo", "url", "publicada_en"}   # nunca "verdadero/falso"


def test_a_guide_does_not_rate_the_figure_or_say_where_it_comes_from():
    # Revisión de la v1 con datos reales (migración 0033): "proviene del Ministerio…", "la cifra es confiable".
    for texto in ("El dato proviene del Ministerio de Hacienda; revisa su página para comprobarlo con calma.",
                  "La cifra coincide con el registro oficial, por lo que es confiable. Revisa la serie completa."):
        with pytest.raises(SalidaInvalida):
            validar("redactar_guia", '{"guia": "%s"}' % texto, {})


def test_only_the_current_prompt_version_is_published(pg):
    assert dict(pg.execute("SELECT tipo, version FROM verificacion.prompt_vigente").fetchall()) == {
        "redactar_guia": "redactar_guia.v2", "juzgar_neutralidad": "juzgar_neutralidad.v2"}
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.execute("UPDATE verificacion.prompt_vigente SET version = 'otro_prompt.v9' WHERE tipo = 'redactar_guia'")
