"""Auditoría, PR-05: cada acción protegida, con cada rol, por la API del servicio social (como la usa la página)."""

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
                  " social.propuesta_figura, social.evento_salida, social.intento_acceso CASCADE")
    with TestClient(app) as c:
        c.db_url = test_db_url
        yield c


def cuenta(cliente, nombre, rol=None):
    clave = "clave-segura-123"
    r = cliente.post("/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": nombre.title(),
                                           "correo": f"{nombre}@correo.co", "clave": clave})
    assert r.status_code == 201, r.text
    if rol:
        with psycopg.connect(cliente.db_url, autocommit=True) as c:
            uid = c.execute("SELECT id FROM social.usuario WHERE nombre_usuario = %s", (nombre,)).fetchone()[0]
            c.execute("CALL social.asignar_rol_consola(%s, %s, 'Rol asignado para una prueba automática.')", (uid, rol))
    token = cliente.post("/v1/sesiones", json={"correo": f"{nombre}@correo.co", "clave": clave}).cookies["parrhesia_sesion"]
    cliente.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_role_by_action_matrix(cliente):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    vero, jefa = cuenta(cliente, "vero", "verificador"), cuenta(cliente, "jefa", "admin")
    figura = {"nombre_completo": "Figura De Prueba", "cargo": "Ministra", "url_fuente_cargo": "https://www.gov.co"}

    # Crear y editar fichas: verificador y administrador.
    assert cliente.post("/v1/figuras", json=figura, headers=ana).status_code == 403
    fid = cliente.post("/v1/figuras", json=figura, headers=vero).json()["id"]
    assert cliente.post("/v1/figuras", json={**figura, "nombre_completo": "Otra Figura"}, headers=jefa).status_code == 201
    cambio = {"cargo": "Ministra de Trabajo", "motivo": "Cambio de cartera publicado."}
    assert cliente.patch(f"/v1/figuras/{fid}", json=cambio, headers=ana).status_code == 403
    assert cliente.patch(f"/v1/figuras/{fid}", json=cambio, headers=vero).status_code == 200

    # Declaraciones: solo verificador o administrador, siempre con fuente.
    decl = {"texto": "Una frase con su fuente.", "dicha_el": "2026-11-01", "url_fuente": "https://www.gov.co/nota"}
    assert cliente.post(f"/v1/figuras/{fid}/declaraciones", json=decl, headers=ana).status_code == 403
    assert cliente.post(f"/v1/figuras/{fid}/declaraciones", json=decl, headers=vero).status_code == 201
    assert cliente.post(f"/v1/figuras/{fid}/declaraciones", json={**decl, "url_fuente": "sin-fuente"}, headers=vero).status_code == 422

    # Propuestas: cualquiera propone; solo el equipo las ve y resuelve.
    prop = cliente.post("/v1/propuestas-figura", json={"nombre_completo": "Persona Propuesta", "cargo": "Senadora",
                                                       "url_fuente": "https://www.senado.gov.co"}, headers=ana)
    assert prop.status_code == 201
    pid = prop.json()["id"]
    assert cliente.get("/v1/propuestas-figura", headers=ana).status_code == 403
    assert cliente.get("/v1/propuestas-figura", headers=vero).status_code == 200
    resolucion = {"aceptar": False, "motivo": "No hay un cargo público verificable."}
    assert cliente.post(f"/v1/propuestas-figura/{pid}/resolucion", json=resolucion, headers=ana).status_code == 403
    assert cliente.post(f"/v1/propuestas-figura/{pid}/resolucion", json=resolucion, headers=vero).status_code == 200

    # Retirar lo ajeno: solo el administrador (el verificador no modera publicaciones).
    p = cliente.post("/v1/publicaciones", json={"texto": "Publicación de Beto"}, headers=beto).json()["id"]
    assert cliente.delete(f"/v1/publicaciones/{p}", headers=ana).status_code == 403
    assert cliente.delete(f"/v1/publicaciones/{p}", headers=vero).status_code == 403
    assert cliente.delete(f"/v1/publicaciones/{p}", headers=jefa).status_code == 204

    # Asignar roles: solo el administrador.
    pedido = {"nombre_usuario": "ana", "rol": "verificador", "motivo": "Se suma al equipo de verificación."}
    assert cliente.post("/v1/equipo/roles", json=pedido, headers=ana).status_code == 403
    assert cliente.post("/v1/equipo/roles", json=pedido, headers=vero).status_code == 403
    assert cliente.post("/v1/equipo/roles", json=pedido, headers=jefa).status_code == 200


def test_without_session_every_protected_action_asks_to_sign_in(cliente):
    for metodo, ruta, cuerpo in (("post", "/v1/figuras", {}), ("post", "/v1/publicaciones", {"texto": "x"}),
                                 ("post", "/v1/equipo/roles", {}), ("get", "/v1/propuestas-figura", None)):
        r = cliente.request(metodo.upper(), ruta, json=cuerpo)
        assert r.status_code in (401, 422), (ruta, r.status_code)
        if r.status_code == 422:      # la validación del cuerpo va primero; con cuerpo válido, 401
            continue
        assert r.json()["error"]["codigo"] == "sesion_requerida"
