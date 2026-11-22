"""API del servicio social contra la base temporal de pruebas.

El grafo se apunta a un puerto cerrado a propósito: el feed debe seguir funcionando
con el respaldo de la base (las pruebas del grafo están en test_grafo.py).
"""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(test_db_url, monkeypatch):
    monkeypatch.setenv("PG_URL_SOCIAL", test_db_url)
    monkeypatch.setenv("GRAFO_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("COOKIE_SEGURA", "false")
    from servicios.social.api import app
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.figura_publica,"
                  " social.evento_salida, social.intento_acceso CASCADE")
    with TestClient(app) as c:
        yield c


def cuenta(cliente, nombre, clave="clave-segura-123"):
    r = cliente.post("/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": nombre.title(),
                                           "correo": f"{nombre}@correo.co", "clave": clave})
    assert r.status_code == 201, r.text
    r = cliente.post("/v1/sesiones", json={"correo": f"{nombre}@correo.co", "clave": clave})
    token = r.cookies["parrhesia_sesion"]
    cliente.cookies.clear()  # cada usuario de la prueba usa su propio token, no la cookie compartida
    return {"Authorization": f"Bearer {token}"}


def test_accounts_sessions_and_errors(cliente, test_db_url):
    ana = cuenta(cliente, "ana")
    assert cliente.get("/v1/yo", headers=ana).json()["nombre_usuario"] == "ana"
    repetida = cliente.post("/v1/cuentas", json={"nombre_usuario": "ana2", "nombre_visible": "Ana",
                                                  "correo": "ANA@correo.co", "clave": "otra-clave-123"})
    assert repetida.status_code == 409 and repetida.json()["error"]["codigo"] == "usuario_correo_key"
    mala = cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "equivocada"})
    assert mala.status_code == 401 and mala.json()["error"]["codigo"] == "credenciales_invalidas"
    assert cliente.get("/v1/yo").status_code == 401
    with psycopg.connect(test_db_url) as c:  # la base guarda la huella argon2id, nunca la clave
        assert c.execute("SELECT clave_hash LIKE '$argon2id$%' FROM social.usuario").fetchone()[0] is True


def test_publish_react_reply_and_thread(cliente):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    p = cliente.post("/v1/publicaciones", json={"texto": "El #desempleo bajó al 8,2 %"}, headers=ana).json()
    assert p["etiquetas"] == ["desempleo"] and p["verificacion"] == "pendiente" and p["totales"]["reacciones"] == 0
    reaccion = cliente.put(f"/v1/publicaciones/{p['id']}/reacciones/yo", json={"tipo": "util"}, headers=beto).json()
    assert reaccion["totales"]["reacciones"] == 1 and reaccion["mi_reaccion"] == "util"
    respuesta = cliente.post("/v1/publicaciones", json={"texto": "¿Fuente?", "responde_a_id": p["id"]}, headers=beto).json()
    hilo = cliente.get(f"/v1/publicaciones/{p['id']}/hilo").json()["hilo"]
    assert [(h["id"], h["profundidad"]) for h in hilo] == [(p["id"], 0), (respuesta["id"], 1)]
    assert cliente.get(f"/v1/publicaciones/{p['id']}").json()["totales"]["respuestas"] == 1


def test_procedure_errors_become_clear_messages(cliente):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    p = cliente.post("/v1/publicaciones", json={"texto": "hola"}, headers=ana).json()
    prohibido = cliente.delete(f"/v1/publicaciones/{p['id']}", headers=beto)
    assert prohibido.status_code == 403 and prohibido.json()["error"]["codigo"] == "sin_permiso"
    assert cliente.delete(f"/v1/publicaciones/{p['id']}", headers=ana).status_code == 204
    retirada = cliente.post("/v1/publicaciones", json={"texto": "respuesta", "responde_a_id": p["id"]}, headers=beto)
    assert retirada.status_code == 404
    assert retirada.json()["error"]["mensaje"] == "La publicación fue retirada y ya no se puede responder ni compartir."
    assert cliente.get(f"/v1/publicaciones/{p['id']}").json()["texto"] is None  # se ve retirada, sin texto
    vacia = cliente.post("/v1/publicaciones", json={"texto": "   "}, headers=ana)
    assert vacia.status_code == 422
    assert cliente.put("/v1/usuarios/ana/seguidores/yo", headers=ana).json()["error"]["codigo"] == "seguimiento_no_a_si_mismo"


def test_feed_falls_back_to_the_database_when_the_graph_is_down(cliente):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    assert cliente.put("/v1/usuarios/beto/seguidores/yo", headers=ana).status_code == 204
    p = cliente.post("/v1/publicaciones", json={"texto": "uno"}, headers=beto).json()
    feed = cliente.get("/v1/feed", headers=ana).json()
    assert feed["fuente"] == "respaldo" and [x["id"] for x in feed["publicaciones"]] == [p["id"]]
    assert cliente.get("/v1/usuarios/beto").json()["estadisticas"] == {"seguidores": 1, "seguidos": 0, "publicaciones": 1}
    assert cliente.get("/v1/sugerencias", headers=ana).json()["sugerencias"] == []


def test_only_verifiers_register_declarations_and_trend_page(cliente, test_db_url):
    ana, vero = cuenta(cliente, "ana"), cuenta(cliente, "vero")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        vid = c.execute("SELECT id FROM social.usuario WHERE nombre_usuario = 'vero'").fetchone()[0]
        c.execute("CALL social.asignar_rol_consola(%s, 'verificador', 'Rol asignado para una prueba automática.')", (vid,))
        figura = c.execute("INSERT INTO social.figura_publica (nombre_completo, cargo) VALUES ('Figura Uno', 'Ministra')"
                           " RETURNING id").fetchone()[0]
    # El rol se lee de la base en cada petición: el cambio aplica sin volver a iniciar sesión.
    declaracion = {"texto": "El desempleo bajó al 8 %", "dicha_el": "2026-11-10", "url_fuente": "https://medio.co/n",
                   "etiquetas": ["Desempleo"]}
    assert cliente.post(f"/v1/figuras/{figura}/declaraciones", json=declaracion, headers=ana).status_code == 403
    assert cliente.post(f"/v1/figuras/{figura}/declaraciones", json=declaracion, headers=vero).status_code == 201
    cliente.post("/v1/publicaciones", json={"texto": "Opino sobre el #desempleo"}, headers=ana)
    pagina = cliente.get("/v1/tendencias/desempleo").json()
    assert len(pagina["declaraciones"]) == 1 and len(pagina["publicaciones"]) == 1
    assert cliente.get(f"/v1/figuras/{figura}").json()["declaraciones"][0]["etiquetas"] == ["desempleo"]
    assert cliente.get("/v1/tendencias").json()["fuente"] == "basica"


# --- Seguridad de la sesión ---------------------------------------------------------------------


def test_session_cookie_is_httponly_strict_and_the_token_is_not_in_the_body(cliente):
    cliente.post("/v1/cuentas", json={"nombre_usuario": "ana", "nombre_visible": "Ana", "correo": "ana@correo.co",
                                      "clave": "clave-segura-123"})
    r = cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "clave-segura-123"})
    galleta = r.headers["set-cookie"].lower()
    assert "httponly" in galleta and "samesite=strict" in galleta and "path=/" in galleta
    assert "token" not in r.json() and r.json()["usuario"]["nombre_usuario"] == "ana"
    assert cliente.get("/v1/yo").status_code == 200  # la cookie basta para leer


def test_writes_with_the_cookie_need_the_app_header(cliente):
    cliente.post("/v1/cuentas", json={"nombre_usuario": "ana", "nombre_visible": "Ana", "correo": "ana@correo.co",
                                      "clave": "clave-segura-123"})
    cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "clave-segura-123"})
    sin_cabecera = cliente.post("/v1/publicaciones", json={"texto": "hola"})
    assert sin_cabecera.status_code == 403 and sin_cabecera.json()["error"]["codigo"] == "origen_no_permitido"
    assert cliente.post("/v1/publicaciones", json={"texto": "hola"}, headers={"X-Parrhesia": "1"}).status_code == 201


def test_logout_revokes_the_session_even_for_a_copied_token(cliente):
    ana = cuenta(cliente, "ana")
    assert cliente.get("/v1/yo", headers=ana).status_code == 200
    assert cliente.delete("/v1/sesiones/actual", headers=ana).status_code == 204
    assert cliente.get("/v1/yo", headers=ana).status_code == 401  # el mismo token, ya revocado en el servidor


def test_a_suspended_account_loses_access_immediately(cliente, test_db_url):
    ana = cuenta(cliente, "ana")
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("UPDATE social.usuario SET estado = 'suspendido' WHERE nombre_usuario = 'ana'")
    assert cliente.get("/v1/yo", headers=ana).status_code == 401


def test_repeated_failures_block_the_account_for_a_while(cliente):
    cuenta(cliente, "ana")
    for _ in range(5):
        assert cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "equivocada"}).status_code == 401
    bloqueado = cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "clave-segura-123"})
    assert bloqueado.status_code == 429 and bloqueado.json()["error"]["codigo"] == "demasiados_intentos"


def test_unknown_email_and_wrong_password_look_the_same(cliente):
    cuenta(cliente, "ana")
    a = cliente.post("/v1/sesiones", json={"correo": "nadie@correo.co", "clave": "lo-que-sea-123"})
    b = cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "lo-que-sea-123"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


@pytest.mark.parametrize("clave", ["12345678", "colombia1", "mi-ana-clave", "anacorreo99"])
def test_weak_passwords_are_refused(cliente, clave):
    r = cliente.post("/v1/cuentas", json={"nombre_usuario": "ana", "nombre_visible": "Ana", "correo": "anacorreo99@correo.co",
                                          "clave": clave})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "clave_debil"


def test_team_roles_only_by_an_admin_with_a_reason_and_a_public_log(cliente, test_db_url):
    jefa, vero = cuenta(cliente, "jefa"), cuenta(cliente, "vero")
    pedido = {"nombre_usuario": "vero", "rol": "verificador", "motivo": "Se suma al equipo de verificación."}
    assert cliente.post("/v1/equipo/roles", json=pedido, headers=vero).status_code == 403      # nadie es admin aún
    with psycopg.connect(test_db_url, autocommit=True) as c:                                     # el primero, por consola
        jid = c.execute("SELECT id FROM social.usuario WHERE nombre_usuario = 'jefa'").fetchone()[0]
        c.execute("CALL social.asignar_rol_consola(%s, 'admin', 'Primera administradora del proyecto.')", (jid,))
    r = cliente.post("/v1/equipo/roles", json=pedido, headers=jefa)
    assert r.status_code == 200, r.text
    assert {(m["nombre_usuario"], m["rol"]) for m in r.json()["miembros"]} == {("jefa", "admin"), ("vero", "verificador")}
    corto = cliente.post("/v1/equipo/roles", json={**pedido, "rol": "usuario", "motivo": "no"}, headers=jefa)
    assert corto.status_code == 422
    ultimo = cliente.post("/v1/equipo/roles", json={"nombre_usuario": "jefa", "rol": "usuario",
                                                    "motivo": "Deja la administración del proyecto."}, headers=jefa)
    assert ultimo.status_code == 409 and ultimo.json()["error"]["codigo"] == "ultimo_admin"
    publico = cliente.get("/v1/equipo").json()                                                   # sin sesión
    assert [(b["nombre_usuario"], b["rol_nuevo"], b["actor"]) for b in publico["bitacora"]] == [
        ("vero", "verificador", "jefa"), ("jefa", "admin", None)]


def test_a_name_that_only_passes_because_of_spaces_gets_a_clear_message(cliente):
    ana = cuenta(cliente, "ana")
    r = cliente.post("/v1/comunidades", json={"nombre": "   ab   ", "descripcion": "Una comunidad para la prueba de auditoría.",
                                              "privacidad": "publica"}, headers=ana)
    assert r.status_code == 422
    assert r.json()["error"]["mensaje"].startswith("El nombre de la comunidad debe tener de 3 a 60 caracteres")


def test_a_write_from_another_site_is_rejected_even_with_the_header(cliente):
    cuenta(cliente, "ana")
    cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "clave-segura-123"})   # queda la cookie
    propio = cliente.post("/v1/publicaciones", json={"texto": "Desde la app"}, headers={"X-Parrhesia": "1", "Origin": "http://testserver"})
    assert propio.status_code == 201
    ajeno = cliente.post("/v1/publicaciones", json={"texto": "Desde otro sitio"},
                         headers={"X-Parrhesia": "1", "Origin": "https://atacante.example"})
    assert ajeno.status_code == 403 and ajeno.json()["error"]["codigo"] == "origen_no_permitido"
    # Como llega por Nginx: Host sin puerto y Origin con puerto. Antes de corregirlo, esto bloqueaba la app real.
    por_nginx = cliente.post("/v1/publicaciones", json={"texto": "Desde la app por Nginx"},
                             headers={"X-Parrhesia": "1", "Origin": "http://127.0.0.1:8080", "Host": "127.0.0.1"})
    assert por_nginx.status_code == 201, por_nginx.text
    mismo_nombre_otro_sitio = cliente.post("/v1/publicaciones", json={"texto": "x"},
                                           headers={"X-Parrhesia": "1", "Origin": "http://127.0.0.1.atacante.example", "Host": "127.0.0.1"})
    assert mismo_nombre_otro_sitio.status_code == 403


def test_a_new_account_sees_its_own_post_in_its_home(cliente):
    ana = cuenta(cliente, "ana")
    p = cliente.post("/v1/publicaciones", json={"texto": "Mi primera publicación"}, headers=ana).json()
    assert [x["id"] for x in cliente.get("/v1/feed", headers=ana).json()["publicaciones"]] == [p["id"]]


def test_a_source_must_be_a_real_web_address(cliente):
    ana = cuenta(cliente, "ana")
    base = {"nombre_completo": "Persona Propuesta", "cargo": "Concejal"}
    for mala in ("https://http://sin-https.example", "https://localhost", "https://sitio con espacio.co", "http://sitio.co"):
        assert cliente.post("/v1/propuestas-figura", json={**base, "url_fuente": mala}, headers=ana).status_code == 422, mala
    assert cliente.post("/v1/propuestas-figura", json={**base, "url_fuente": "https://www.concejobogota.gov.co"}, headers=ana).status_code == 201
