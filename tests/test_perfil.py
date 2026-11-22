"""Perfil editable, foto, búsqueda y desactivación (migración 0014, decisión 30)."""

from __future__ import annotations

from io import BytesIO

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def cliente(test_db_url, monkeypatch, tmp_path):
    monkeypatch.setenv("PG_URL_SOCIAL", test_db_url)
    monkeypatch.setenv("GRAFO_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("COOKIE_SEGURA", "false")
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path / "fotos"))
    from servicios.social.api import app
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.figura_publica,"
                  " social.evento_salida, social.intento_acceso CASCADE")
    with TestClient(app) as c:
        yield c


def cuenta(cliente, nombre, clave="clave-segura-123"):
    assert cliente.post("/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": nombre.title(),
                                             "correo": f"{nombre}@correo.co", "clave": clave}).status_code == 201
    token = cliente.post("/v1/sesiones", json={"correo": f"{nombre}@correo.co", "clave": clave}).cookies["parrhesia_sesion"]
    cliente.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def imagen(formato="PNG", tamano=(900, 600), exif=False) -> bytes:
    salida = BytesIO()
    img = Image.new("RGB", tamano, (200, 180, 150))
    if exif:
        datos = Image.Exif()
        datos[0x010F] = "CamaraDePrueba"  # fabricante: un metadato que no debe sobrevivir
        img.save(salida, formato, exif=datos)
    else:
        img.save(salida, formato)
    return salida.getvalue()


def test_profile_changes_only_own_account_and_notifies_the_graph(cliente, test_db_url):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    ocupado = cliente.patch("/v1/yo", json={"nombre_usuario": "beto"}, headers=ana)
    assert ocupado.status_code == 409 and ocupado.json()["error"]["codigo"] == "usuario_nombre_usuario_key"
    r = cliente.patch("/v1/yo", json={"nombre_visible": "Ana María", "nombre_usuario": "Ana_Maria", "biografia": "Economista"},
                      headers=ana)
    assert r.status_code == 200, r.text
    assert (r.json()["nombre_usuario"], r.json()["nombre_visible"]) == ("ana_maria", "Ana María")
    assert cliente.get("/v1/usuarios/beto").json()["nombre_visible"] == "Beto"  # el id sale de la sesión, no del cuerpo
    assert cliente.patch("/v1/yo", json={"biografia": ""}, headers=ana).json()["biografia"] is None
    with psycopg.connect(test_db_url) as c:
        eventos = c.execute("SELECT datos->>'nombre_usuario' FROM social.evento_salida WHERE tipo_evento = 'usuario_actualizado'").fetchall()
    assert eventos == [("ana_maria",)]  # un solo evento: la biografía no le interesa al grafo
    assert cliente.get("/v1/cuentas/disponible", params={"nombre_usuario": "beto"}).json()["estado"] == "en_uso"
    assert cliente.get("/v1/cuentas/disponible", params={"nombre_usuario": "a b"}).json()["estado"] == "invalido"
    assert cliente.get("/v1/cuentas/disponible", params={"nombre_usuario": "nueva"}).json()["estado"] == "disponible"
    # El nombre anterior sigue llevando a su dueña y nadie más puede tomarlo.
    assert cliente.get("/v1/usuarios/ana").json()["nombre_usuario"] == "ana_maria"
    tomado = cliente.post("/v1/cuentas", json={"nombre_usuario": "ana", "nombre_visible": "Otra",
                                                "correo": "otra@correo.co", "clave": "clave-segura-123"})
    assert tomado.status_code == 409 and tomado.json()["error"]["codigo"] == "nombre_reservado"
    assert cliente.get("/v1/cuentas/disponible", params={"nombre_usuario": "ana"}).json()["estado"] == "en_uso"
    otra_vez = cliente.patch("/v1/yo", json={"nombre_usuario": "ana_m"}, headers=ana)
    assert otra_vez.status_code == 409 and otra_vez.json()["error"]["codigo"] == "cambio_nombre_reciente"
    assert beto  # usado arriba


def test_search_shows_only_active_people_and_who_i_follow(cliente, test_db_url):
    ana = cuenta(cliente, "ana")
    cuenta(cliente, "mariana")
    cuenta(cliente, "marcos")
    cliente.put("/v1/usuarios/mariana/seguidores/yo", headers=ana)
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("UPDATE social.usuario SET estado = 'suspendido' WHERE nombre_usuario = 'marcos'")
    encontrados = cliente.get("/v1/usuarios", params={"q": "mar"}, headers=ana).json()["usuarios"]
    assert [(u["nombre_usuario"], u["lo_sigo"], u["seguidores"]) for u in encontrados] == [("mariana", True, 1)]
    assert "correo" not in encontrados[0]  # solo datos públicos
    assert cliente.get("/v1/usuarios", params={"q": "m"}).status_code == 422


def test_password_change_requires_current_one_and_closes_other_sessions(cliente):
    ana_movil = cuenta(cliente, "ana")
    ana_pc = {"Authorization": cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "clave-segura-123"})
              .cookies["parrhesia_sesion"].join(["Bearer ", ""])}
    cliente.cookies.clear()
    mala = cliente.put("/v1/yo/clave", json={"clave_actual": "otra", "clave_nueva": "nueva-clave-456"}, headers=ana_pc)
    assert mala.status_code == 403 and mala.json()["error"]["codigo"] == "clave_incorrecta"
    debil = cliente.put("/v1/yo/clave", json={"clave_actual": "clave-segura-123", "clave_nueva": "ana12345"}, headers=ana_pc)
    assert debil.status_code == 422
    ok = cliente.put("/v1/yo/clave", json={"clave_actual": "clave-segura-123", "clave_nueva": "nueva-clave-456"}, headers=ana_pc)
    assert ok.json() == {"sesiones_cerradas": 1}
    assert cliente.get("/v1/yo", headers=ana_movil).status_code == 401  # la otra sesión quedó cerrada
    assert cliente.get("/v1/yo", headers=ana_pc).status_code == 200    # la actual sigue
    assert cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "nueva-clave-456"}).status_code == 200


def test_wrong_current_password_counts_towards_the_lock(cliente):
    ana = cuenta(cliente, "ana")
    for _ in range(5):
        assert cliente.put("/v1/yo/correo", json={"correo": "x@correo.co", "clave_actual": "mala"}, headers=ana).status_code == 403
    bloqueada = cliente.put("/v1/yo/correo", json={"correo": "x@correo.co", "clave_actual": "clave-segura-123"}, headers=ana)
    assert bloqueada.status_code == 429


def test_photo_is_reencoded_without_metadata_and_replaced(cliente, tmp_path):
    ana = cuenta(cliente, "ana")
    r = cliente.put("/v1/yo/foto", files={"foto": ("yo.jpg", imagen("JPEG", exif=True), "image/jpeg")}, headers=ana)
    assert r.status_code == 200, r.text
    url = r.json()["foto"]
    archivo = cliente.get(url.removeprefix("/api/social"))
    assert archivo.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(archivo.content)) as guardada:
        assert guardada.format == "WEBP" and guardada.size == (400, 400)
        assert not guardada.getexif()  # sin metadatos de la cámara
    assert cliente.get("/v1/yo", headers=ana).json()["foto"] == url
    otra = cliente.put("/v1/yo/foto", files={"foto": ("b.png", imagen(), "image/png")}, headers=ana).json()["foto"]
    assert sorted(p.name for p in (tmp_path / "fotos").iterdir()) == [otra.rsplit("/", 1)[1]]  # la anterior se borró
    falsa = cliente.put("/v1/yo/foto", files={"foto": ("x.png", b"<svg onload=alert(1)>", "image/png")}, headers=ana)
    assert falsa.status_code == 415
    grande = cliente.put("/v1/yo/foto", files={"foto": ("g.png", b"\0" * (2 * 1024 * 1024 + 10), "image/png")}, headers=ana)
    assert grande.status_code == 413
    assert cliente.get("/v1/fotos/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert cliente.delete("/v1/yo/foto", headers=ana).status_code == 204
    assert cliente.get("/v1/yo", headers=ana).json()["foto"] is None and not list((tmp_path / "fotos").iterdir())


def test_deactivation_keeps_posts_and_cannot_be_undone_from_the_app(cliente, test_db_url):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    p = cliente.post("/v1/publicaciones", json={"texto": "Una opinión"}, headers=ana).json()
    respuesta = cliente.post("/v1/publicaciones", json={"texto": "Respuesta", "responde_a_id": p["id"]}, headers=beto).json()
    assert cliente.post("/v1/yo/desactivacion", json={"clave_actual": "mala"}, headers=ana).status_code == 403
    assert cliente.post("/v1/yo/desactivacion", json={"clave_actual": "clave-segura-123"}, headers=ana).status_code == 204
    assert cliente.get("/v1/yo", headers=ana).status_code == 401
    assert cliente.post("/v1/sesiones", json={"correo": "ana@correo.co", "clave": "clave-segura-123"}).status_code == 401
    hilo = cliente.get(f"/v1/publicaciones/{p['id']}/hilo").json()["hilo"]
    assert [h["id"] for h in hilo] == [p["id"], respuesta["id"]]  # el hilo de beto sigue completo
    assert cliente.get("/v1/usuarios/ana").json()["estado"] == "desactivada"
    with psycopg.connect(test_db_url, autocommit=True) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="cuenta_desactivada"):
            c.execute("UPDATE social.usuario SET estado = 'activo' WHERE nombre_usuario = 'ana'")


def test_own_email_is_private_and_follow_state_is_known(cliente):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    assert cliente.get("/v1/yo", headers=ana).json()["correo"] == "ana@correo.co"
    assert "correo" not in cliente.get("/v1/usuarios/ana", headers=beto).json()
    assert cliente.get("/v1/usuarios/ana", headers=beto).json()["lo_sigo"] is False
    cliente.put("/v1/usuarios/ana/seguidores/yo", headers=beto)
    assert cliente.get("/v1/usuarios/ana", headers=beto).json()["lo_sigo"] is True
    assert cliente.get("/v1/usuarios/ana").json()["lo_sigo"] is False  # sin sesión
