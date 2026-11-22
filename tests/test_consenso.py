"""Extracción por consenso (migración 0008, decisión 26)."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.types.json import Jsonb

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."
LECTURA = [{"texto_citado": "el desempleo bajó al 8,2 %", "codigo_indicador": "unemployment", "variante": "tasa",
            "periodo_desde": "2026-09", "periodo_hasta": "2026-09", "territorio": "national", "valor_dicho": "8.2",
            "unidad_dicha": "%", "comparacion": "nivel", "confianza": 0.9}]


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, verificacion.afirmacion, verificacion.procesamiento, ia.trabajo, social.usuario,"
                  " social.publicacion CASCADE")
        yield c


@pytest.fixture
def publicacion(db):
    autor = db.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', %s, NULL)", (HASH,)).fetchone()[0]
    return db.execute("CALL social.publicar(%s, 'El desempleo bajó al 8,2 %%', NULL, NULL, NULL, NULL)",
                      (autor,)).fetchone()[0]


def coinciden(db, a, b):
    return db.execute("SELECT verificacion.lecturas_coinciden(%s, %s)", (Jsonb(a), Jsonb(b))).fetchone()[0]


def test_readings_are_compared_on_what_the_rules_use(db):
    otra_forma = [{**LECTURA[0], "valor_dicho": "8.20", "texto_citado": "bajó al 8,2 %", "confianza": 0.5}]
    assert coinciden(db, LECTURA, otra_forma) is True  # mismo dato aunque la cita y la confianza cambien
    assert coinciden(db, LECTURA, [{**LECTURA[0], "periodo_desde": "2026-08", "periodo_hasta": "2026-08"}]) is False
    assert coinciden(db, LECTURA, [{**LECTURA[0], "variante": "anual"}]) is False
    dos = LECTURA + [{**LECTURA[0], "codigo_indicador": "inflation", "valor_dicho": "5.1"}]
    assert coinciden(db, dos, list(reversed(dos))) is True  # el orden no importa
    assert coinciden(db, [], []) is True and coinciden(db, LECTURA, []) is False


def registrar(db, publicacion, a, b):
    return db.execute("CALL verificacion.registrar_afirmaciones_consenso('publicacion', %s, NULL, NULL, %s, %s, NULL, NULL)",
                      (publicacion, Jsonb(a), Jsonb(b))).fetchone()


def test_agreeing_readings_go_on_to_the_rules(db, publicacion):
    assert registrar(db, publicacion, LECTURA, LECTURA) == (1, "coinciden")
    assert db.execute("SELECT estado, consenso FROM verificacion.afirmacion").fetchone() == ("extraida", "coinciden")
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (publicacion,)).fetchone()[0] == "pendiente"


def test_disagreeing_readings_wait_for_a_person(db, publicacion):
    otra = [{**LECTURA[0], "valor_dicho": "8.9"}]
    assert registrar(db, publicacion, LECTURA, otra) == (1, "difieren")
    assert db.execute("SELECT estado FROM verificacion.afirmacion").fetchone()[0] == "requiere_revision"
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (publicacion,)).fetchone()[0] == "requiere_revision"
    with pytest.raises(psycopg.errors.CheckViolation, match="afirmacion_difieren_en_revision"):
        db.execute("INSERT INTO verificacion.afirmacion (publicacion_id, posicion, texto_citado, confianza_extraccion,"
                   " consenso) VALUES (%s, 9, 'x', 1, 'difieren')", (publicacion,))


def test_one_reading_without_claims_is_a_disagreement(db, publicacion):
    assert registrar(db, publicacion, [], LECTURA) == (1, "difieren")


def test_two_empty_readings_mean_an_opinion(db, publicacion):
    assert registrar(db, publicacion, [], []) == (0, "coinciden")
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (publicacion,)).fetchone()[0] == "sin_cifras"


def test_each_provider_gets_its_own_job_and_only_available_providers_are_taken(db):
    def encolar(proveedor):
        return db.execute("CALL ia.encolar_trabajo('extraer_afirmaciones', 'v1', %s, %s, NULL, NULL)",
                          (Jsonb({"texto": "hola"}), proveedor)).fetchone()[0]
    groq, openrouter = encolar("groq"), encolar("openrouter")
    assert groq != openrouter and encolar("groq") == groq  # misma entrada, mismo proveedor: un solo trabajo
    tomado = db.execute("SELECT id FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones'], ARRAY['groq'])").fetchone()[0]
    assert tomado == groq
    # Sin cuentas de OpenRouter disponibles, su trabajo espera en la cola.
    assert db.execute("SELECT count(*) FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones'], ARRAY['groq'])").fetchone()[0] == 0


# --- Decisión 33: consenso por afirmación (migraciones 0021 y 0022) -----------------------------

INFL = {"texto_citado": "La inflación anual de septiembre de 2026 fue 6,29 %", "codigo_indicador": "inflation", "variante": "anual",
        "periodo_desde": "2026-09", "periodo_hasta": "2026-09", "territorio": "national", "valor_dicho": "6.29",
        "unidad_dicha": "%", "comparacion": "nivel", "confianza": 0.9}
CAMBIO = {**INFL, "texto_citado": "1,11 puntos más que un año antes", "valor_dicho": "1.11", "comparacion": "variacion_puntos"}


def test_a_claim_both_read_the_same_goes_on_even_if_the_other_reading_has_more(db, publicacion):
    """Caso real de la evaluación v1: un proveedor leyó una afirmación, el otro dos; coinciden en 6,29 %."""
    assert registrar(db, publicacion, [INFL], [INFL, CAMBIO]) == (2, "parcial")
    filas = db.execute("SELECT valor_dicho::text, estado, consenso FROM verificacion.afirmacion ORDER BY posicion").fetchall()
    assert filas == [("6.29", "extraida", "coinciden"), ("1.11", "requiere_revision", "difieren")]


def test_a_reading_that_finds_nothing_sends_the_other_to_review(db, publicacion):
    dos = [{**INFL, "codigo_indicador": "homicides", "variante": "conteo", "valor_dicho": v, "comparacion": "nivel"} for v in ("499", "717")]
    assert registrar(db, publicacion, [], dos) == (2, "difieren")
    assert {e for (e,) in db.execute("SELECT estado FROM verificacion.afirmacion")} == {"requiere_revision"}


def test_same_figure_read_differently_is_reviewed_once(db, publicacion):
    otra_lectura = {**INFL, "comparacion": "variacion_puntos"}
    assert registrar(db, publicacion, [otra_lectura], [INFL]) == (1, "difieren")
