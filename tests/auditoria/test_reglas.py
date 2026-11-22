"""Auditoría, BD-06, BD-08 y BD-10: transiciones de estado, outbox en la misma transacción y todo o nada."""

from __future__ import annotations

import uuid

import psycopg
import pytest

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida,"
                  " social.figura_publica, social.propuesta_figura, social.comunidad CASCADE")   # limpia al empezar: otras pruebas pueden dejar cuentas
        yield c
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida,"
                  " social.figura_publica, social.propuesta_figura, social.comunidad CASCADE")


def cuenta(db, nombre, rol=None):
    uid = db.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
                     (nombre, nombre.title(), f"{nombre}@correo.co", HASH)).fetchone()[0]
    if rol:
        db.execute("CALL social.asignar_rol_consola(%s, %s, 'Rol asignado para una prueba automática.')", (uid, rol))
    return uid


def eventos(db):
    return db.execute("SELECT count(*) FROM social.evento_salida").fetchone()[0]


# --- BD-06: transiciones de estado ------------------------------------------------------------------------

def test_a_proposal_is_resolved_only_once(db):
    ana, vero = cuenta(db, "ana"), cuenta(db, "vero", "verificador")
    prop = db.execute("CALL social.proponer_figura(%s, 'Persona Propuesta', 'Ministra', 'https://www.gov.co', NULL, NULL)", (ana,)).fetchone()[0]
    db.execute("CALL social.resolver_propuesta_figura(%s, %s, false, 'No tiene cargo público verificable.', NULL)", (vero, prop))
    with pytest.raises(psycopg.errors.RaiseException, match="propuesta_no_pendiente"):
        db.execute("CALL social.resolver_propuesta_figura(%s, %s, true, 'Cambio de opinión.', NULL)", (vero, prop))


def test_a_join_request_is_resolved_only_once(db):
    jefa, ana = cuenta(db, "jefa"), cuenta(db, "ana")
    com = db.execute("CALL social.crear_comunidad(%s, 'Privada de prueba', 'Comunidad privada para la auditoría.', NULL, 'privada', NULL)",
                     (jefa,)).fetchone()[0]
    db.execute("CALL social.entrar_a_comunidad(%s, %s, 'Quiero entrar', NULL)", (ana, com))
    sol = db.execute("SELECT id FROM social.solicitud_ingreso WHERE usuario_id = %s", (ana,)).fetchone()[0]
    db.execute("CALL social.resolver_solicitud(%s, %s, true, NULL)", (jefa, sol))
    with pytest.raises(psycopg.errors.RaiseException, match="solicitud_no_pendiente"):
        db.execute("CALL social.resolver_solicitud(%s, %s, false, 'Ya no')", (jefa, sol))


def test_a_withdrawn_post_cannot_come_back(db):
    ana = cuenta(db, "ana")
    p = db.execute("CALL social.publicar(%s, 'Texto', NULL, NULL, '{}', NULL)", (ana,)).fetchone()[0]
    db.execute("CALL social.retirar_publicacion(%s, %s)", (p, ana))
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("UPDATE social.publicacion SET estado = 'visible' WHERE id = %s", (p,))


# --- BD-08: el outbox va en la misma transacción ---------------------------------------------------------

def test_a_rolled_back_post_leaves_no_event(db):
    ana = cuenta(db, "ana")
    antes = eventos(db)
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.execute("CALL social.publicar(%s, 'Esto se deshace', NULL, NULL, '{}', NULL)", (ana,))
            raise RuntimeError("se deshace a propósito")
    assert eventos(db) == antes
    assert db.execute("SELECT count(*) FROM social.publicacion WHERE texto = 'Esto se deshace'").fetchone()[0] == 0


def test_every_post_emits_its_event(db):
    ana = cuenta(db, "ana")
    p = db.execute("CALL social.publicar(%s, 'Con evento #prueba', NULL, NULL, '{}', NULL)", (ana,)).fetchone()[0]
    tipos = {t for (t,) in db.execute("SELECT tipo_evento FROM social.evento_salida WHERE entidad_id = %s", (str(p),))}
    assert "publicacion_creada" in tipos


# --- BD-10: todo o nada ------------------------------------------------------------------------------------

def test_publishing_with_an_unknown_figure_leaves_nothing(db):
    ana = cuenta(db, "ana")
    antes = eventos(db)
    with pytest.raises(psycopg.Error):
        db.execute("CALL social.publicar(%s, 'Mención rota', NULL, NULL, %s, NULL)", (ana, [uuid.uuid4()]))
    assert db.execute("SELECT count(*) FROM social.publicacion WHERE texto = 'Mención rota'").fetchone()[0] == 0
    assert eventos(db) == antes


def test_a_duplicate_community_leaves_nothing(db):
    jefa = cuenta(db, "jefa")
    db.execute("CALL social.crear_comunidad(%s, 'Única', 'Comunidad para probar duplicados.', NULL, 'publica', NULL)", (jefa,))
    integrantes = db.execute("SELECT count(*) FROM social.integrante").fetchone()[0]
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("CALL social.crear_comunidad(%s, 'Única', 'Otra descripción para el duplicado.', NULL, 'publica', NULL)", (jefa,))
    assert db.execute("SELECT count(*) FROM social.comunidad").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM social.integrante").fetchone()[0] == integrantes
