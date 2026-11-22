"""Roles de las cuentas con bitácora (migración 0035): quién administra y quién verifica es trazable."""

from __future__ import annotations

import psycopg
import pytest

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."
MOTIVO = "Se suma al equipo de verificación."


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.sesion, social.usuario RESTART IDENTITY CASCADE")     # limpia al empezar: otras pruebas pueden dejar cuentas
        yield c
        c.execute("RESET ROLE")
        c.execute("TRUNCATE social.cambio_rol, social.sesion, social.usuario RESTART IDENTITY CASCADE")


def cuenta(db, nombre):
    return db.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
                      (nombre, nombre.title(), f"{nombre}@correo.co", HASH)).fetchone()[0]


def rol(db, uid):
    return db.execute("SELECT rol FROM social.usuario WHERE id = %s", (uid,)).fetchone()[0]


def test_role_cannot_change_with_a_direct_update(db):
    ana = cuenta(db, "ana")
    with pytest.raises(psycopg.errors.RaiseException, match="rol_por_procedimiento"):
        db.execute("UPDATE social.usuario SET rol = 'admin' WHERE id = %s", (ana,))


def test_first_admin_from_console_then_admin_assigns_and_everything_is_logged(db):
    jefa, vero = cuenta(db, "jefa"), cuenta(db, "vero")
    db.execute("CALL social.asignar_rol_consola(%s, 'admin', 'Primera administradora del proyecto.')", (jefa,))
    db.execute("CALL social.asignar_rol(%s, %s, 'verificador', %s)", (jefa, vero, MOTIVO))
    assert rol(db, vero) == "verificador"
    bitacora = db.execute("SELECT usuario_id, rol_anterior, rol_nuevo, actor_id FROM social.cambio_rol ORDER BY id").fetchall()
    assert bitacora == [(jefa, "usuario", "admin", None), (vero, "usuario", "verificador", jefa)]
    assert {n for (n,) in db.execute("SELECT nombre_usuario FROM social.equipo")} == {"jefa", "vero"}


def test_only_an_admin_assigns_roles_and_a_reason_is_required(db):
    jefa, vero, ana = cuenta(db, "jefa"), cuenta(db, "vero"), cuenta(db, "ana")
    db.execute("CALL social.asignar_rol_consola(%s, 'admin', 'Primera administradora del proyecto.')", (jefa,))
    db.execute("CALL social.asignar_rol(%s, %s, 'verificador', %s)", (jefa, vero, MOTIVO))
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):        # un verificador no asigna
        db.execute("CALL social.asignar_rol(%s, %s, 'verificador', %s)", (vero, ana, MOTIVO))
    with pytest.raises(psycopg.errors.CheckViolation, match="cambio_rol_motivo_valido"):
        db.execute("CALL social.asignar_rol(%s, %s, 'verificador', 'porque sí')", (jefa, ana))
    assert rol(db, ana) == "usuario"                                                   # nada quedó a medias
    with pytest.raises(psycopg.errors.RaiseException, match="rol_sin_cambio"):
        db.execute("CALL social.asignar_rol(%s, %s, 'verificador', %s)", (jefa, vero, MOTIVO))


def test_the_last_admin_cannot_be_removed(db):
    jefa, otra = cuenta(db, "jefa"), cuenta(db, "otra")
    db.execute("CALL social.asignar_rol_consola(%s, 'admin', 'Primera administradora del proyecto.')", (jefa,))
    with pytest.raises(psycopg.errors.RaiseException, match="ultimo_admin"):
        db.execute("CALL social.asignar_rol(%s, %s, 'usuario', 'Deja la administración del proyecto.')", (jefa, jefa))
    with pytest.raises(psycopg.errors.RaiseException, match="ultimo_admin"):        # tampoco desactivándola
        db.execute("UPDATE social.usuario SET estado = 'suspendido' WHERE id = %s", (jefa,))
    db.execute("CALL social.asignar_rol(%s, %s, 'admin', 'Segunda administradora para no depender de una.')", (jefa, otra))
    db.execute("CALL social.asignar_rol(%s, %s, 'usuario', 'Deja la administración del proyecto.')", (otra, jefa))
    assert (rol(db, jefa), rol(db, otra)) == ("usuario", "admin")


def test_the_log_is_insert_only(db):
    jefa = cuenta(db, "jefa")
    db.execute("CALL social.asignar_rol_consola(%s, 'admin', 'Primera administradora del proyecto.')", (jefa,))
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("UPDATE social.cambio_rol SET motivo = 'Otro motivo cualquiera.'")
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("DELETE FROM social.cambio_rol")


def test_the_social_service_cannot_bypass_the_admin_check(db):
    ana = cuenta(db, "ana")
    db.execute("SET ROLE svc_social")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):                          # la consola no es para la web
        db.execute("CALL social.asignar_rol_consola(%s, 'admin', 'Intento desde el servicio web.')", (ana,))
    db.execute("SELECT set_config('parrhesia.cambio_rol', 'procedimiento', false)")
    with pytest.raises(psycopg.errors.Error):                                          # ni marcando la sesión a mano
        db.execute("UPDATE social.usuario SET rol = 'admin' WHERE id = %s", (ana,))
    db.execute("RESET ROLE")
    assert rol(db, ana) == "usuario"
