"""Auditoría, BD-11: acciones simultáneas (doble clic, dos pestañas, dos trabajadores) no duplican ni descuadran."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."
VECES = 12


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida CASCADE")   # limpia al empezar: otras pruebas pueden dejar cuentas
        yield c
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida CASCADE")


def cuenta(db, nombre):
    return db.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
                      (nombre, nombre.title(), f"{nombre}@correo.co", HASH)).fetchone()[0]


def a_la_vez(url, sentencia, parametros, errores=None):
    """La misma sentencia desde VECES conexiones a la vez; devuelve cuántas terminaron sin error. Ninguna puede
    fallar por bloqueo mutuo (deadlock): eso era lo que perdía acciones antes de la migración 0037."""
    def una(_):
        try:
            with psycopg.connect(url, autocommit=True) as c:
                c.execute(sentencia, parametros)
            return None
        except psycopg.Error as e:
            return e
    with ThreadPoolExecutor(VECES) as grupo:
        fallas = [e for e in grupo.map(una, range(VECES)) if e is not None]
    assert not any(isinstance(e, psycopg.errors.DeadlockDetected) for e in fallas), "hubo bloqueos mutuos"
    if errores is not None:
        errores.extend(fallas)
    return VECES - len(fallas)


def test_same_reaction_many_times_at_once_counts_once(db, test_db_url):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    p = db.execute("CALL social.publicar(%s, 'Texto', NULL, NULL, '{}', NULL)", (ana,)).fetchone()[0]
    assert a_la_vez(test_db_url, "CALL social.reaccionar(%s, %s, 'util')", (p, beto)) == VECES
    reales = db.execute("SELECT count(*) FROM social.reaccion WHERE publicacion_id = %s", (p,)).fetchone()[0]
    contador = db.execute("SELECT total_reacciones FROM social.publicacion WHERE id = %s", (p,)).fetchone()[0]
    assert reales == 1 and contador == 1


def test_sharing_many_times_at_once_leaves_one_share(db, test_db_url):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    p = db.execute("CALL social.publicar(%s, 'Texto', NULL, NULL, '{}', NULL)", (ana,)).fetchone()[0]
    errores = []
    a_la_vez(test_db_url, "CALL social.publicar(%s, NULL, NULL, %s, '{}', NULL)", (beto, p), errores)
    assert all(isinstance(e, psycopg.errors.UniqueViolation) for e in errores)      # "ya compartiste", nada más
    reales = db.execute("SELECT count(*) FROM social.publicacion WHERE comparte_id = %s AND estado = 'visible'", (p,)).fetchone()[0]
    contador = db.execute("SELECT total_compartidas FROM social.publicacion WHERE id = %s", (p,)).fetchone()[0]
    assert reales == 1 and contador == 1


def test_following_many_times_at_once_follows_once(db, test_db_url):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    assert a_la_vez(test_db_url, "CALL social.seguir(%s, %s)", (beto, ana)) == VECES
    assert db.execute("SELECT count(*) FROM social.seguimiento WHERE seguidor_id = %s", (beto,)).fetchone()[0] == 1


def test_many_replies_at_once_keep_the_counter_exact(db, test_db_url):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    p = db.execute("CALL social.publicar(%s, 'Texto', NULL, NULL, '{}', NULL)", (ana,)).fetchone()[0]
    hechas = a_la_vez(test_db_url, "CALL social.publicar(%s, 'Respuesta', %s, NULL, '{}', NULL)", (beto, p))
    contador = db.execute("SELECT total_respuestas FROM social.publicacion WHERE id = %s", (p,)).fetchone()[0]
    assert hechas == VECES and contador == VECES


def test_two_workers_never_take_the_same_ai_job(db, test_db_url):
    db.execute("TRUNCATE ia.intento, ia.trabajo")
    for i in range(VECES):
        db.execute("CALL ia.encolar_trabajo('extraer_afirmaciones', 'v1', %s, 'groq', NULL, NULL)", (f'{{"texto": "t{i}"}}',))

    def tomar(_):
        with psycopg.connect(test_db_url, autocommit=True) as c:
            fila = c.execute("SELECT id FROM ia.tomar_trabajo(ARRAY['extraer_afirmaciones'], ARRAY['groq'])").fetchone()
            return fila[0] if fila else None
    with ThreadPoolExecutor(VECES * 2) as grupo:
        tomados = [t for t in grupo.map(tomar, range(VECES * 2)) if t]
    assert len(tomados) == VECES and len(set(tomados)) == VECES
