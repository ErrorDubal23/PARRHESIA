"""Comunidades en PostgreSQL (migración 0018, decisión 28): papeles, solicitudes, visibilidad y bitácora."""

from __future__ import annotations

import threading

import psycopg
import pytest

HASH = "$argon2id$v=19$m=1$x$y"


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida, social.comunidad CASCADE")
        yield c


def cuenta(c, nombre):
    return c.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)", (nombre, nombre.title(), f"{nombre}@x.co", HASH)).fetchone()[0]


def comunidad(c, creador, nombre="Economía colombiana", privacidad="publica"):
    return c.execute("CALL social.crear_comunidad(%s, %s, 'Debate sobre cifras económicas del país', NULL, %s, NULL)",
                     (creador, nombre, privacidad)).fetchone()[0]


def publicar(c, autor, comunidad_id, texto="Una opinión"):
    return c.execute("CALL social.publicar_en_comunidad(%s, %s, %s, '{}', NULL)", (autor, comunidad_id, texto)).fetchone()[0]


def test_creator_is_admin_and_counts_are_kept(db):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    com = comunidad(db, ana)
    assert db.execute("SELECT social.mi_papel(%s, %s)", (com, ana)).fetchone()[0] == "administrador"
    assert db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (beto, com)).fetchone()[0] == "integrante"
    assert db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (beto, com)).fetchone()[0] == "ya_integrante"
    assert db.execute("SELECT total_integrantes FROM social.comunidad WHERE id = %s", (com,)).fetchone()[0] == 2
    with pytest.raises(psycopg.errors.UniqueViolation):
        comunidad(db, beto, "  economía COLOMBIANA ")  # el nombre no se repite


def test_never_without_an_administrator(db):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    com = comunidad(db, ana)
    with pytest.raises(psycopg.errors.RaiseException, match="ultimo_administrador"):
        db.execute("CALL social.salir_de_comunidad(%s, %s)", (ana, com))
    db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (beto, com))
    db.execute("CALL social.asignar_papel(%s, %s, %s, 'administrador')", (ana, com, beto))
    db.execute("CALL social.salir_de_comunidad(%s, %s)", (ana, com))  # ahora sí: queda beto
    with pytest.raises(psycopg.errors.RaiseException, match="ultimo_administrador"):
        db.execute("CALL social.asignar_papel(%s, %s, %s, 'integrante')", (beto, com, beto))


def test_two_admins_demoting_each_other_at_once_leave_one(db, test_db_url):
    """El trigger bloquea la comunidad: dos degradaciones simultáneas no la dejan sin administrador."""
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    com = comunidad(db, ana)
    db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (beto, com))
    db.execute("CALL social.asignar_papel(%s, %s, %s, 'administrador')", (ana, com, beto))
    errores, listo = [], threading.Barrier(2)

    def degradar(actor, objetivo):
        with psycopg.connect(test_db_url) as c:
            listo.wait()
            try:
                c.execute("CALL social.asignar_papel(%s, %s, %s, 'integrante')", (actor, com, objetivo))
                c.commit()
            except psycopg.errors.RaiseException as e:
                errores.append(str(e))
    hilos = [threading.Thread(target=degradar, args=(ana, beto)), threading.Thread(target=degradar, args=(beto, ana))]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    administradores = db.execute("SELECT count(*) FROM social.integrante WHERE comunidad_id = %s AND papel = 'administrador'", (com,)).fetchone()[0]
    assert administradores == 1 and len(errores) == 1


def test_roles_do_not_all_do_the_same(db):
    ana, gestora, moderador, dani = (cuenta(db, n) for n in ("ana", "gestora", "moderador", "dani"))
    com = comunidad(db, ana)
    for u in (gestora, moderador, dani):
        db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (u, com))
    db.execute("CALL social.asignar_papel(%s, %s, %s, 'gestor')", (ana, com, gestora))
    db.execute("CALL social.asignar_papel(%s, %s, %s, 'moderador')", (ana, com, moderador))
    # Un moderador no expulsa; un gestor sí, pero con motivo y nunca a un administrador.
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.expulsar_de_comunidad(%s, %s, %s, 'Incumple las reglas del grupo')", (moderador, com, dani))
    with pytest.raises(psycopg.errors.RaiseException, match="motivo_requerido"):
        db.execute("CALL social.expulsar_de_comunidad(%s, %s, %s, 'no')", (gestora, com, dani))
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.expulsar_de_comunidad(%s, %s, %s, 'Quiero quedarme con la comunidad')", (gestora, com, ana))
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.asignar_papel(%s, %s, %s, 'administrador')", (gestora, com, gestora))
    db.execute("CALL social.expulsar_de_comunidad(%s, %s, %s, 'Publicó datos personales de otra persona')", (gestora, com, dani))
    bitacora = db.execute("SELECT accion, motivo FROM social.bitacora_comunidad WHERE comunidad_id = %s AND accion = 'expulsion'", (com,)).fetchall()
    assert bitacora == [("expulsion", "Publicó datos personales de otra persona")]
    with pytest.raises(psycopg.errors.RaiseException, match="prohibir|solo inserción|no se permite"):
        db.execute("DELETE FROM social.bitacora_comunidad WHERE comunidad_id = %s", (com,))


def test_private_community_requests_and_visibility(db):
    ana, beto, carla = cuenta(db, "ana"), cuenta(db, "beto"), cuenta(db, "carla")
    com = comunidad(db, ana, "Seguridad y orden público", "privada")
    assert db.execute("CALL social.entrar_a_comunidad(%s, %s, 'Me interesa el tema', NULL)", (beto, com)).fetchone()[0] == "solicitud"
    publicacion = publicar(db, ana, com, "Solo para integrantes")
    ver = lambda u: db.execute("SELECT social.puede_ver_publicacion(%s, %s)", (publicacion, u)).fetchone()[0]  # noqa: E731
    assert (ver(ana), ver(beto), ver(None)) == (True, False, False)
    with pytest.raises(psycopg.errors.RaiseException, match="no_integrante"):
        publicar(db, beto, com)
    solicitud = db.execute("SELECT id FROM social.solicitud_ingreso WHERE usuario_id = %s", (beto,)).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.resolver_solicitud(%s, %s, true, NULL)", (carla, solicitud))
    db.execute("CALL social.resolver_solicitud(%s, %s, true, NULL)", (ana, solicitud))
    assert ver(beto) is True
    # Lo privado no sale de la comunidad; responder hereda la comunidad.
    with pytest.raises(psycopg.errors.RaiseException, match="publicacion_privada"):
        db.execute("CALL social.publicar(%s, NULL, NULL, %s, '{}', NULL)", (beto, publicacion))
    respuesta = db.execute("CALL social.publicar(%s, 'Respondo', %s, NULL, '{}', NULL)", (beto, publicacion)).fetchone()[0]
    assert db.execute("SELECT comunidad_id FROM social.publicacion WHERE id = %s", (respuesta,)).fetchone()[0] == com
    with pytest.raises(psycopg.errors.RaiseException, match="no_integrante"):
        db.execute("CALL social.publicar(%s, 'Me cuelo', %s, NULL, '{}', NULL)", (carla, publicacion))


def test_moderation_pins_and_retires_with_a_trace(db):
    ana, beto, mod = cuenta(db, "ana"), cuenta(db, "beto"), cuenta(db, "mod")
    com = comunidad(db, ana)
    for u in (beto, mod):
        db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (u, com))
    db.execute("CALL social.asignar_papel(%s, %s, %s, 'moderador')", (ana, com, mod))
    pubs = [publicar(db, beto, com, f"Opinión {i}") for i in range(4)]
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.fijar_publicacion(%s, %s, true)", (beto, pubs[0]))
    for p in pubs[:3]:
        db.execute("CALL social.fijar_publicacion(%s, %s, true)", (mod, p))
    with pytest.raises(psycopg.errors.RaiseException, match="limite_fijadas"):
        db.execute("CALL social.fijar_publicacion(%s, %s, true)", (mod, pubs[3]))
    db.execute("CALL social.retirar_publicacion(%s, %s)", (pubs[0], mod))
    estado, fijada = db.execute("SELECT estado, fijada_en FROM social.publicacion WHERE id = %s", (pubs[0],)).fetchone()
    assert (estado, fijada) == ("retirada_por_moderacion", None)
    acciones = [a for (a,) in db.execute("SELECT accion FROM social.bitacora_comunidad WHERE comunidad_id = %s ORDER BY id", (com,))]
    assert acciones[-1] == "publicacion_retirada" and acciones.count("publicacion_fijada") == 3
    # Un moderador de una comunidad no modera publicaciones de fuera.
    afuera = db.execute("CALL social.publicar(%s, 'Fuera de la comunidad', NULL, NULL, '{}', NULL)", (beto,)).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.retirar_publicacion(%s, %s)", (afuera, mod))


def test_graph_gets_community_events(db):
    ana, beto = cuenta(db, "ana"), cuenta(db, "beto")
    com = comunidad(db, ana)
    db.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (beto, com))
    publicar(db, beto, com)
    db.execute("CALL social.salir_de_comunidad(%s, %s)", (beto, com))
    tipos = [t for (t,) in db.execute("SELECT tipo_evento FROM social.evento_salida WHERE tipo_evento IN"
                                      " ('comunidad_creada', 'integrante_agregado', 'integrante_quitado', 'publicacion_en_comunidad') ORDER BY id")]
    assert tipos == ["comunidad_creada", "integrante_agregado", "integrante_agregado", "publicacion_en_comunidad", "integrante_quitado"]
