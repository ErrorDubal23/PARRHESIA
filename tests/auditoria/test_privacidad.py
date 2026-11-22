"""Auditoría, PR-07: lo publicado en una comunidad privada no sale por los caminos que la suite aún no cubría
(hilo, responder, reaccionar, página de una etiqueta). Los demás están en test_api_comunidades.py."""

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
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.comunidad,"
                  " social.evento_salida, social.intento_acceso CASCADE")
    with TestClient(app) as c:
        yield c


def cuenta(cliente, nombre):
    clave = "clave-segura-123"
    cliente.post("/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": nombre.title(),
                                       "correo": f"{nombre}@correo.co", "clave": clave})
    token = cliente.post("/v1/sesiones", json={"correo": f"{nombre}@correo.co", "clave": clave}).cookies["parrhesia_sesion"]
    cliente.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_private_post_does_not_leak_through_thread_reply_reaction_or_hashtag(cliente):
    ana, carla = cuenta(cliente, "ana"), cuenta(cliente, "carla")
    c = cliente.post("/v1/comunidades", json={"nombre": "Círculo cerrado", "descripcion": "Comunidad privada de la auditoría",
                                              "privacidad": "privada"}, headers=ana).json()
    p = cliente.post(f"/v1/comunidades/{c['id']}/publicaciones",
                     json={"texto": "Solo para integrantes #secretoauditoria"}, headers=ana).json()
    assert cliente.get(f"/v1/publicaciones/{p['id']}/hilo", headers=carla).status_code == 404
    assert cliente.get(f"/v1/publicaciones/{p['id']}/difusion", headers=carla).status_code == 404
    assert cliente.get(f"/v1/publicaciones/{p['id']}/hilo").status_code == 404
    respuesta = cliente.post("/v1/publicaciones", json={"texto": "Respondo desde fuera", "responde_a_id": p["id"]}, headers=carla)
    assert respuesta.status_code in (403, 404, 409)
    reaccion = cliente.put(f"/v1/publicaciones/{p['id']}/reacciones/yo", json={"tipo": "util"}, headers=carla)
    assert reaccion.status_code == 404                                  # antes de la 0038: se guardaba y daba 500
    assert cliente.get(f"/v1/publicaciones/{p['id']}", headers=ana).json()["totales"]["reacciones"] == 0
    etiqueta = cliente.get("/v1/tendencias/secretoauditoria", headers=carla).json()
    assert all(x["id"] != p["id"] for x in etiqueta.get("publicaciones", []))
    # La integrante sí lo ve por todos esos caminos.
    assert cliente.get(f"/v1/publicaciones/{p['id']}/hilo", headers=ana).status_code == 200
