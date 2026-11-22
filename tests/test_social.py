"""Esquema social (migración 0003): cada regla tiene una prueba que intenta romperla."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."  # forma de bcrypt, no es una clave real


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c
        c.execute(
            "TRUNCATE social.cambio_rol, social.entrega_evento, social.evento_salida, social.tendencia, social.mencion_usuario,"
            " social.mencion_figura, social.declaracion_etiqueta, social.declaracion, social.bitacora_figura, social.propuesta_figura, social.figura_publica,"
            " social.reaccion, social.publicacion_etiqueta, social.etiqueta, social.publicacion,"
            " social.seguimiento, social.sesion, social.nombre_anterior, social.bitacora_comunidad, social.solicitud_ingreso, social.integrante, social.comunidad, social.usuario RESTART IDENTITY"
        )


def usuario(db, nombre, rol="usuario", creado_en=None):
    uid = db.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
                     (nombre, nombre.title(), f"{nombre}@correo.co", HASH)).fetchone()[0]
    if rol != "usuario":
        db.execute("CALL social.asignar_rol_consola(%s, %s, 'Rol asignado para una prueba automática.')", (uid, rol))
    if creado_en is not None:  # solo para pruebas: simular una cuenta antigua
        db.execute("ALTER TABLE social.usuario DISABLE TRIGGER usuario_normalizar")
        db.execute("UPDATE social.usuario SET creado_en = %s WHERE id = %s", (creado_en, uid))
        db.execute("ALTER TABLE social.usuario ENABLE TRIGGER usuario_normalizar")
    return uid


def publicar(db, autor, texto, responde_a=None, comparte=None, figuras=None):
    return db.execute("CALL social.publicar(%s, %s, %s, %s, %s, NULL)",
                      (autor, texto, responde_a, comparte, figuras)).fetchone()[0]


def eventos(db, tipo):
    return [r[0] for r in db.execute(
        "SELECT datos FROM social.evento_salida WHERE tipo_evento = %s ORDER BY id", (tipo,))]


# Usuarios


def test_password_in_plain_text_is_refused(db):
    with pytest.raises(psycopg.errors.CheckViolation, match="usuario_clave_es_hash"):
        db.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', 'mi_clave_123', NULL)")


def test_email_and_handle_are_unique_ignoring_case(db):
    usuario(db, "ana")
    with pytest.raises(psycopg.errors.UniqueViolation, match="usuario_correo_key"):
        db.execute("CALL social.registrar_usuario('ana2', 'Ana', 'ANA@Correo.co', %s, NULL)", (HASH,))
    with pytest.raises(psycopg.errors.UniqueViolation, match="usuario_nombre_usuario_key"):
        db.execute("CALL social.registrar_usuario('ANA', 'Ana', 'otra@correo.co', %s, NULL)", (HASH,))


def test_new_user_emits_event_without_email(db):
    usuario(db, "ana")
    [evento] = eventos(db, "usuario_creado")
    assert evento["nombre_usuario"] == "ana" and "correo" not in evento and "clave_hash" not in evento


# Publicar



def test_extract_functions(db):
    etiquetas = db.execute("SELECT social.extraer_etiquetas('Hoy #Desempleo y #desempleo, #Reforma_Tributaria #IVA')").fetchone()[0]
    assert etiquetas == ["desempleo", "reforma_tributaria", "iva"]
    menciones = db.execute("SELECT social.extraer_menciones('Hola @Ana y @ana, correo x@y.co, @bo')").fetchone()[0]
    assert menciones == ["ana"]  # sin repetir; un correo no es mención; @bo es muy corto


def test_publish_saves_hashtags_mentions_and_events_in_one_transaction(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    figura = db.execute("INSERT INTO social.figura_publica (nombre_completo) VALUES ('Figura Uno') RETURNING id").fetchone()[0]
    p = publicar(db, ana, "El #desempleo bajó, dice @beto #Desempleo", figuras=[figura])
    assert db.execute(
        "SELECT e.nombre FROM social.publicacion_etiqueta pe JOIN social.etiqueta e ON e.id = pe.etiqueta_id"
        " WHERE pe.publicacion_id = %s", (p,)).fetchall() == [("desempleo",)]
    assert db.execute("SELECT usuario_id FROM social.mencion_usuario WHERE publicacion_id = %s", (p,)).fetchone()[0] == beto
    assert len(eventos(db, "publicacion_creada")) == 1
    assert len(eventos(db, "publicacion_etiquetada")) == 1
    assert {e["tipo_destino"] for e in eventos(db, "publicacion_menciona")} == {"usuario", "figura"}
    assert all("texto" not in e for e in eventos(db, "publicacion_creada"))


def test_failed_publish_leaves_nothing(db):
    ana = usuario(db, "ana")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        publicar(db, ana, "Con #etiqueta y una figura inexistente",
                 figuras=["00000000-0000-0000-0000-000000000000"])
    assert db.execute("SELECT count(*) FROM social.publicacion").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM social.etiqueta").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM social.evento_salida WHERE tipo_entidad = 'publicacion'").fetchone()[0] == 0


def test_suspended_author_cannot_publish(db):
    ana = usuario(db, "ana")
    db.execute("UPDATE social.usuario SET estado = 'suspendido' WHERE id = %s", (ana,))
    with pytest.raises(psycopg.errors.RaiseException, match="autor_inactivo"):
        publicar(db, ana, "hola")


def test_post_text_cannot_be_edited_and_removal_is_one_way(db):
    ana = usuario(db, "ana")
    p = publicar(db, ana, "texto original")
    with pytest.raises(psycopg.errors.RaiseException, match="no se edita"):
        db.execute("UPDATE social.publicacion SET texto = 'otro' WHERE id = %s", (p,))
    db.execute("CALL social.retirar_publicacion(%s, %s)", (p, ana))
    with pytest.raises(psycopg.errors.RaiseException, match="no se permite pasar"):
        db.execute("UPDATE social.publicacion SET estado = 'visible' WHERE id = %s", (p,))
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("DELETE FROM social.publicacion WHERE id = %s", (p,))


def test_only_author_or_admin_can_remove(db):
    ana, beto, admin = usuario(db, "ana"), usuario(db, "beto"), usuario(db, "admin1", rol="admin")
    p, q = publicar(db, ana, "uno"), publicar(db, ana, "dos")
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.retirar_publicacion(%s, %s)", (p, beto))
    db.execute("CALL social.retirar_publicacion(%s, %s)", (q, admin))
    assert db.execute("SELECT estado FROM social.publicacion WHERE id = %s", (q,)).fetchone()[0] == "retirada_por_moderacion"


def test_cannot_reply_to_or_share_a_removed_post(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    p = publicar(db, ana, "original")
    db.execute("CALL social.retirar_publicacion(%s, %s)", (p, ana))
    with pytest.raises(psycopg.errors.RaiseException, match="publicacion_destino_no_visible"):
        publicar(db, beto, "respuesta", responde_a=p)
    with pytest.raises(psycopg.errors.RaiseException, match="publicacion_destino_no_visible"):
        publicar(db, beto, None, comparte=p)


def test_reply_and_share_counters_follow_removals(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    p = publicar(db, ana, "original")
    r = publicar(db, beto, "respuesta", responde_a=p)
    publicar(db, beto, None, comparte=p)  # compartida sin comentario
    assert db.execute("SELECT total_respuestas, total_compartidas FROM social.publicacion WHERE id = %s", (p,)).fetchone() == (1, 1)
    db.execute("CALL social.retirar_publicacion(%s, %s)", (r, beto))
    assert db.execute("SELECT total_respuestas FROM social.publicacion WHERE id = %s", (p,)).fetchone()[0] == 0
    with pytest.raises(psycopg.errors.CheckViolation, match="publicacion_texto_o_compartida"):
        publicar(db, beto, "   ")


def test_thread_is_returned_in_reading_order(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    raiz = publicar(db, ana, "raíz")
    a = publicar(db, beto, "a", responde_a=raiz)
    a1 = publicar(db, ana, "a1", responde_a=a)
    b = publicar(db, beto, "b", responde_a=raiz)
    filas = db.execute("SELECT id, profundidad FROM social.hilo(%s)", (raiz,)).fetchall()
    ids = [i for i, _ in filas]
    assert ids[0] == raiz and ids.index(a) < ids.index(a1) and {a, b} <= set(ids)
    assert dict(filas)[a1] == 2


# Seguir y reaccionar


def test_follow_rules(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    with pytest.raises(psycopg.errors.CheckViolation, match="seguimiento_no_a_si_mismo"):
        db.execute("CALL social.seguir(%s, %s)", (ana, ana))
    db.execute("CALL social.seguir(%s, %s)", (ana, beto))
    db.execute("CALL social.seguir(%s, %s)", (ana, beto))  # dos veces: sin error, sin duplicar
    assert db.execute("SELECT count(*) FROM social.seguimiento").fetchone()[0] == 1
    assert len(eventos(db, "seguimiento_creado")) == 1
    db.execute("CALL social.dejar_de_seguir(%s, %s)", (ana, beto))
    assert len(eventos(db, "seguimiento_borrado")) == 1
    assert db.execute("SELECT * FROM social.estadisticas_usuario(%s)", (beto,)).fetchone() == (0, 0, 0)


def test_changing_reaction_type_does_not_add_a_second_one(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    p = publicar(db, ana, "dato")
    db.execute("CALL social.reaccionar(%s, %s, 'me_gusta')", (p, beto))
    db.execute("CALL social.reaccionar(%s, %s, 'util')", (p, beto))
    assert db.execute("SELECT total_reacciones FROM social.publicacion WHERE id = %s", (p,)).fetchone()[0] == 1
    assert db.execute("SELECT tipo FROM social.reaccion").fetchone()[0] == "util"
    with pytest.raises(psycopg.errors.CheckViolation, match="reaccion_tipo_valido"):
        db.execute("CALL social.reaccionar(%s, %s, 'no_me_gusta')", (p, ana))


def test_counters_match_real_counts_after_many_operations(db):
    rnd = random.Random(7)
    usuarios = [usuario(db, f"u{i:02d}") for i in range(8)]
    pubs = [publicar(db, rnd.choice(usuarios), f"publicación {i}") for i in range(5)]
    for _ in range(200):
        p, u = rnd.choice(pubs), rnd.choice(usuarios)
        accion = rnd.random()
        if accion < 0.4:
            db.execute("CALL social.reaccionar(%s, %s, %s)", (p, u, rnd.choice(["me_gusta", "util"])))
        elif accion < 0.6:
            db.execute("CALL social.quitar_reaccion(%s, %s)", (p, u))
        elif accion < 0.8:
            pubs.append(publicar(db, u, "respuesta", responde_a=p))
        elif accion < 0.9:
            try:   # migración 0027: una sola compartida sin comentario por persona y publicación
                pubs.append(publicar(db, u, None, comparte=p))
            except psycopg.errors.UniqueViolation:
                pass
        else:
            hijo = db.execute("SELECT id, autor_id FROM social.publicacion WHERE estado = 'visible'"
                              " AND responde_a_id IS NOT NULL ORDER BY random() LIMIT 1").fetchone()
            if hijo:
                db.execute("CALL social.retirar_publicacion(%s, %s)", hijo)
        pubs = [x for x in pubs if db.execute(
            "SELECT estado = 'visible' FROM social.publicacion WHERE id = %s", (x,)).fetchone()[0]]
    diferencias = db.execute("""
        SELECT count(*) FROM social.publicacion p
        WHERE p.total_reacciones <> (SELECT count(*) FROM social.reaccion r WHERE r.publicacion_id = p.id)
           OR p.total_respuestas <> (SELECT count(*) FROM social.publicacion h WHERE h.responde_a_id = p.id AND h.estado = 'visible')
           OR p.total_compartidas <> (SELECT count(*) FROM social.publicacion h WHERE h.comparte_id = p.id AND h.estado = 'visible')
    """).fetchone()[0]
    assert diferencias == 0


# Declaraciones y tendencias


def test_only_verifiers_register_declarations(db):
    ana, vero = usuario(db, "ana"), usuario(db, "vero", rol="verificador")
    figura = db.execute("INSERT INTO social.figura_publica (nombre_completo) VALUES ('Figura Uno') RETURNING id").fetchone()[0]
    args = (figura, "El desempleo bajó al 8 %", "2026-11-10", "declaracion", "https://medio.co/nota", ["#Desempleo"])
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL social.registrar_declaracion(%s, %s, %s, %s, %s, %s, %s, NULL)", (ana, *args))
    d = db.execute("CALL social.registrar_declaracion(%s, %s, %s, %s, %s, %s, %s, NULL)", (vero, *args)).fetchone()[0]
    contenido = db.execute("SELECT tipo, id FROM social.contenido_tendencia('desempleo', now() - interval '1 day', now())").fetchall()
    assert contenido == [("declaracion", d)]
    assert len(eventos(db, "declaracion_creada")) == 1
    with pytest.raises(psycopg.errors.RaiseException, match="solo puede cambiar el estado de la promesa"):
        db.execute("UPDATE social.declaracion SET texto = 'otra cosa'")


def test_basic_trends_need_three_old_accounts(db):
    hace_un_mes = datetime.now(timezone.utc) - timedelta(days=30)
    viejos = [usuario(db, f"viejo{i}", creado_en=hace_un_mes) for i in range(3)]
    nuevos = [usuario(db, f"nuevo{i}") for i in range(5)]
    for u in viejos[:2] + nuevos:
        publicar(db, u, "hablando de #reforma")
    desde, hasta = datetime.now(timezone.utc) - timedelta(hours=1), datetime.now(timezone.utc) + timedelta(hours=1)
    assert db.execute("SELECT * FROM social.tendencias_basicas(%s, %s)", (desde, hasta)).fetchall() == []
    publicar(db, viejos[2], "yo también, #Reforma")
    assert db.execute("SELECT etiqueta, total_autores FROM social.tendencias_basicas(%s, %s)",
                      (desde, hasta)).fetchall() == [("reforma", 3)]


def test_trending_window_is_all_or_nothing_and_append_only(db):
    ana = usuario(db, "ana")
    publicar(db, ana, "#uno")
    desde, hasta = datetime(2026, 11, 21, tzinfo=timezone.utc), datetime(2026, 11, 21, 3, tzinfo=timezone.utc)
    fila = {"total_publicaciones": 4, "total_autores": 3, "diversidad": 0.5, "puntaje": 2, "posicion": 1}
    with pytest.raises(psycopg.errors.RaiseException, match="etiqueta_desconocida"):
        db.execute("CALL social.registrar_tendencias(%s, %s, %s)",
                   (desde, hasta, psycopg.types.json.Jsonb([{**fila, "etiqueta": "uno"},
                                                            {**fila, "etiqueta": "no_existe", "posicion": 2}])))
    assert db.execute("SELECT count(*) FROM social.tendencia").fetchone()[0] == 0
    db.execute("CALL social.registrar_tendencias(%s, %s, %s)",
               (desde, hasta, psycopg.types.json.Jsonb([{**fila, "etiqueta": "uno"}])))
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("UPDATE social.tendencia SET puntaje = 100")


# Outbox


def test_each_consumer_receives_every_event(db):
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    db.execute("CALL social.seguir(%s, %s)", (ana, beto))
    publicar(db, ana, "hola")
    grafo = db.execute("SELECT id FROM social.eventos_pendientes('grafo', ARRAY['usuario_creado','seguimiento_creado','publicacion_creada'])").fetchall()
    assert len(grafo) == 4
    db.execute("CALL social.marcar_entregados('grafo', %s)", ([i for (i,) in grafo],))
    assert db.execute("SELECT count(*) FROM social.eventos_pendientes('grafo', ARRAY['publicacion_creada'])").fetchone()[0] == 0
    # El grafo ya los procesó, pero verificación todavía ve la publicación.
    assert db.execute("SELECT count(*) FROM social.eventos_pendientes('verificacion', ARRAY['publicacion_creada'])").fetchone()[0] == 1
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("DELETE FROM social.evento_salida")


def test_verification_reads_text_only_of_visible_posts(db):
    ana = usuario(db, "ana")
    p = publicar(db, ana, "La inflación es 5,2 %")
    assert db.execute("SELECT social.texto_para_verificar('publicacion', %s)", (p,)).fetchone()[0] == "La inflación es 5,2 %"
    db.execute("CALL social.retirar_publicacion(%s, %s)", (p, ana))
    assert db.execute("SELECT social.texto_para_verificar('publicacion', %s)", (p,)).fetchone()[0] is None


def test_a_person_shares_a_post_only_once_without_comment(db):
    # Migración 0027: cada clic creaba otra compartida (una cuenta llegó a 90 de la misma publicación).
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    original = publicar(db, ana, "Hoy llovió en Bogotá")
    primera = publicar(db, beto, None, comparte=original)
    with pytest.raises(psycopg.errors.UniqueViolation, match="publicacion_una_compartida_idx"):
        publicar(db, beto, None, comparte=original)
    publicar(db, beto, "Con comentario sí, las veces que quiera", comparte=original)
    db.execute("CALL social.retirar_publicacion(%s, %s)", (primera, beto))   # deshacer
    publicar(db, beto, None, comparte=original)                              # y volver a compartir
    assert db.execute("SELECT total_compartidas FROM social.publicacion WHERE id = %s", (original,)).fetchone()[0] == 2


def test_share_without_comment_has_empty_text_not_null(db):
    # NULL significa "retirada"; una compartida sin comentario es visible y no tiene cifras (migración 0024).
    ana, beto = usuario(db, "ana"), usuario(db, "beto")
    original = publicar(db, ana, "Hoy llovió en Bogotá")
    compartida = publicar(db, beto, None, comparte=original)
    assert db.execute("SELECT social.texto_para_verificar('publicacion', %s)", (compartida,)).fetchone()[0] == ""
    assert not db.execute("SELECT verificacion.requiere_extraccion('')").fetchone()[0]
