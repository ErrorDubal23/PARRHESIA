"""Esquema ia (migración 0004): la cola de trabajos, las cuentas y los intentos."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest
from psycopg.types.json import Jsonb


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c
        c.execute("TRUNCATE ia.intento, ia.trabajo, ia.credencial")


def encolar(db, entrada, tipo="extraer_afirmaciones", version="v1"):
    return db.execute("CALL ia.encolar_trabajo(%s, %s, %s, NULL, NULL, NULL)", (tipo, version, Jsonb(entrada))).fetchone()


def tomar(db, tipos=("extraer_afirmaciones",)):
    return db.execute("SELECT id FROM ia.tomar_trabajo(%s, ARRAY['groq'])", (list(tipos),)).fetchone()


def intento(db, trabajo, alias, resultado, salida=None, esperar=None):
    db.execute(
        "CALL ia.registrar_intento(%s, %s, 'openai/gpt-oss-120b', %s, 100, 20, %s, %s, %s, now())",
        (trabajo, alias, resultado, None if resultado == "ok" else "detalle del error",
         Jsonb(salida) if salida is not None else None, esperar),
    )


def estado(db, trabajo):
    return db.execute("SELECT estado FROM ia.trabajo WHERE id = %s", (trabajo,)).fetchone()[0]


@pytest.fixture
def cuentas(db):
    db.execute("CALL ia.configurar_credencial('groq_cuenta_1', 'groq', true)")
    db.execute("CALL ia.configurar_credencial('groq_cuenta_2', 'groq', true)")


def test_there_is_no_column_for_secrets(db):
    columnas = {r[0] for r in db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ia'")}
    assert not {c for c in columnas if any(p in c for p in ("llave", "clave", "secret", "key", "token_api"))}


def test_same_input_is_enqueued_once_and_cached_when_done(db, cuentas):
    primero, cache = encolar(db, {"texto": "La inflación es 5,2 %", "idioma": "es"})
    assert cache is False
    # Mismo contenido con las llaves en otro orden: misma huella, mismo trabajo.
    assert encolar(db, {"idioma": "es", "texto": "La inflación es 5,2 %"}) == (primero, False)
    tomar(db)
    intento(db, primero, "groq_cuenta_1", "ok", salida={"afirmaciones": []})
    assert encolar(db, {"texto": "La inflación es 5,2 %", "idioma": "es"}) == (primero, True)
    otro, cache = encolar(db, {"texto": "La inflación es 5,2 %", "idioma": "es"}, version="v2")
    assert otro != primero and cache is False  # otra versión del prompt: trabajo nuevo


def test_two_workers_never_take_the_same_job(test_db_url, db):
    a, _ = encolar(db, {"n": 1})
    b, _ = encolar(db, {"n": 2})
    with psycopg.connect(test_db_url) as w1, psycopg.connect(test_db_url) as w2:
        primero = w1.execute("SELECT id FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones'], ARRAY['groq'])").fetchone()[0]
        # w1 no ha confirmado y tiene la fila bloqueada: w2 no espera, toma la otra.
        w2.execute("SET lock_timeout = '1s'")
        segundo = w2.execute("SELECT id FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones'], ARRAY['groq'])").fetchone()[0]
        assert {primero, segundo} == {a, b}
        assert w2.execute("SELECT count(*) FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones'], ARRAY['groq'])").fetchone()[0] == 0
        w1.commit()
        w2.commit()


def test_a_crashed_worker_job_is_taken_again_after_its_deadline(db):
    t, _ = encolar(db, {"n": 1})
    assert tomar(db)[0] == t
    assert tomar(db) is None  # tiene plazo de 5 minutos
    db.execute("UPDATE ia.trabajo SET proximo_intento_en = now() - interval '1 second' WHERE id = %s", (t,))
    assert tomar(db)[0] == t


def test_rate_limit_pauses_the_account_and_moves_to_the_next(db, cuentas):
    t, _ = encolar(db, {"n": 1})
    assert db.execute("SELECT ia.elegir_credencial('groq')").fetchone()[0] == "groq_cuenta_1"
    tomar(db)
    intento(db, t, "groq_cuenta_1", "limite_alcanzado", esperar=timedelta(minutes=10))
    assert estado(db, t) == "en_cola"
    assert db.execute("SELECT ia.elegir_credencial('groq')").fetchone()[0] == "groq_cuenta_2"
    assert tomar(db)[0] == t  # listo de inmediato: queda otra cuenta
    intento(db, t, "groq_cuenta_2", "limite_alcanzado", esperar=timedelta(minutes=3))
    # Todas en pausa: el trabajo espera hasta que se libere la primera cuenta.
    assert db.execute("SELECT ia.elegir_credencial('groq')").fetchone()[0] is None
    espera = db.execute("SELECT proximo_intento_en - now() FROM ia.trabajo WHERE id = %s", (t,)).fetchone()[0]
    assert timedelta(minutes=2) < espera <= timedelta(minutes=3)
    assert tomar(db) is None


def test_errors_back_off_and_fail_on_the_fifth(db, cuentas):
    t, _ = encolar(db, {"n": 1})
    esperas = []
    for _ in range(5):
        db.execute("UPDATE ia.trabajo SET proximo_intento_en = now() WHERE id = %s", (t,))
        tomar(db)
        intento(db, t, "groq_cuenta_1", "salida_invalida")
        esperas.append(db.execute(
            "SELECT extract(epoch FROM proximo_intento_en - now())::int FROM ia.trabajo WHERE id = %s", (t,)).fetchone()[0])
    assert esperas[:4] == [2, 4, 8, 16]
    assert estado(db, t) == "fallido"
    assert db.execute("SELECT count(*) FROM ia.intento WHERE trabajo_id = %s", (t,)).fetchone()[0] == 5


def test_rate_limits_do_not_count_as_failures(db, cuentas):
    t, _ = encolar(db, {"n": 1})
    for _ in range(6):
        db.execute("UPDATE ia.credencial SET pausada_hasta = NULL")
        db.execute("UPDATE ia.trabajo SET proximo_intento_en = now() WHERE id = %s", (t,))
        tomar(db)
        intento(db, t, "groq_cuenta_1", "limite_alcanzado")
    assert estado(db, t) == "en_cola"


def test_state_machine_and_output_rules(db, cuentas):
    t, _ = encolar(db, {"n": 1})
    with pytest.raises(psycopg.errors.RaiseException, match="trabajo_no_en_curso"):
        intento(db, t, "groq_cuenta_1", "ok", salida={"x": 1})
    tomar(db)
    with pytest.raises(psycopg.errors.RaiseException, match="salida_faltante"):
        intento(db, t, "groq_cuenta_1", "ok")
    intento(db, t, "groq_cuenta_1", "ok", salida={"x": 1})
    with pytest.raises(psycopg.errors.RaiseException, match="no se permite pasar de terminado a en_cola"):
        db.execute("UPDATE ia.trabajo SET estado = 'en_cola', salida = NULL, terminado_en = NULL WHERE id = %s", (t,))
    with pytest.raises(psycopg.errors.RaiseException, match="la entrada y el proveedor no cambian"):
        db.execute("UPDATE ia.trabajo SET entrada = '{}' WHERE id = %s", (t,))
    with pytest.raises(psycopg.errors.CheckViolation, match="trabajo_salida_solo_si_terminado"):
        db.execute("INSERT INTO ia.trabajo (tipo, version_prompt, entrada, salida) VALUES"
                   " ('agrupar_temas', 'v1', '{}', '{\"x\": 1}')")
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("UPDATE ia.intento SET resultado = 'ok'")


def test_unknown_account_is_refused(db):
    t, _ = encolar(db, {"n": 1})
    tomar(db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation, match="intento_credencial_alias_fkey"):
        intento(db, t, "cuenta_inexistente", "ok", salida={"x": 1})
    assert estado(db, t) == "en_curso"  # el procedimiento se deshizo completo


def test_a_failed_job_is_final_for_that_input_and_prompt_version(db, cuentas):
    t, _ = encolar(db, {"n": 1})
    for _ in range(5):
        db.execute("UPDATE ia.trabajo SET proximo_intento_en = now() WHERE id = %s", (t,))
        tomar(db)
        intento(db, t, "groq_cuenta_1", "salida_invalida")
    assert estado(db, t) == "fallido"
    assert encolar(db, {"n": 1}) == (t, False)          # devuelve el fallido: quien lo pidió usa su respaldo
    nuevo, _ = encolar(db, {"n": 1}, version="v2")      # una versión nueva del prompt sí vuelve a intentar
    assert nuevo != t
