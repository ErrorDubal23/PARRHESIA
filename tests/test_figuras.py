"""Gestión de figuras públicas (migración 0019): permisos, fuentes, duplicados, bitácora y propuestas."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

FUENTE = "https://www.camara.gov.co/representantes"


@pytest.fixture
def cliente(test_db_url, monkeypatch, tmp_path):
    monkeypatch.setenv("PG_URL_SOCIAL", test_db_url)
    monkeypatch.setenv("GRAFO_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("COOKIE_SEGURA", "false")
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    from servicios.social.api import app
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida, social.figura_publica,"
                  " social.intento_acceso CASCADE")
    with TestClient(app) as c:
        c.db_url = test_db_url
        yield c


def cuenta(cliente, nombre, rol="usuario"):
    clave = "clave-segura-123"
    cliente.post("/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": nombre.title(),
                                      "correo": f"{nombre}@correo.co", "clave": clave})
    with psycopg.connect(cliente.db_url, autocommit=True) as c:
        if rol != "usuario":
            uid = c.execute("SELECT id FROM social.usuario WHERE nombre_usuario = %s", (nombre,)).fetchone()[0]
            c.execute("CALL social.asignar_rol_consola(%s, %s, 'Rol asignado para una prueba automática.')", (uid, rol))
    token = cliente.post("/v1/sesiones", json={"correo": f"{nombre}@correo.co", "clave": clave}).cookies["parrhesia_sesion"]
    cliente.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_only_verifiers_create_and_every_fact_has_a_source(cliente):
    ana, vero = cuenta(cliente, "ana"), cuenta(cliente, "vero", "verificador")
    datos = {"nombre_completo": "María  Pérez Gómez", "cargo": "Representante a la Cámara", "url_fuente_cargo": FUENTE}
    assert cliente.post("/v1/figuras", json=datos, headers=ana).status_code == 403
    sin_fuente = cliente.post("/v1/figuras", json={**datos, "url_fuente_cargo": "http://inseguro.co"}, headers=vero)
    assert sin_fuente.status_code == 422
    partido_sin_fuente = cliente.post("/v1/figuras", json={**datos, "partido": "Un partido"}, headers=vero)
    assert partido_sin_fuente.status_code == 422 and partido_sin_fuente.json()["error"]["codigo"] == "figura_publica_partido_con_fuente"
    f = cliente.post("/v1/figuras", json=datos, headers=vero).json()
    assert f["nombre_completo"] == "María Pérez Gómez" and f["url_fuente_cargo"] == FUENTE
    duplicada = cliente.post("/v1/figuras", json={**datos, "nombre_completo": "maria perez  GOMEZ"}, headers=vero)
    assert duplicada.status_code == 409 and duplicada.json()["error"]["codigo"] == "figura_publica_nombre_comparable_key"
    assert [p["nombre_completo"] for p in cliente.get("/v1/figuras/parecidas", params={"nombre": "Maria Perez"}).json()["parecidas"]] == ["María Pérez Gómez"]


def test_edits_keep_before_and_after_and_archived_ones_leave_the_list(cliente):
    vero = cuenta(cliente, "vero", "verificador")
    f = cliente.post("/v1/figuras", json={"nombre_completo": "Juan Ruiz", "cargo": "Senador", "url_fuente_cargo": FUENTE}, headers=vero).json()
    cliente.patch(f"/v1/figuras/{f['id']}", json={"cargo": "Ministro de Hacienda", "url_fuente_cargo": "https://www.minhacienda.gov.co",
                                                  "motivo": "Nombramiento publicado"}, headers=vero)
    cliente.patch(f"/v1/figuras/{f['id']}", json={"estado": "archivada", "motivo": "Dejó el cargo"}, headers=vero)
    bitacora = cliente.get(f"/v1/figuras/{f['id']}/bitacora").json()["bitacora"]
    assert [b["accion"] for b in bitacora] == ["archivada", "editada", "creada"]
    assert bitacora[1]["cambios"]["cargo"] == {"antes": "Senador", "despues": "Ministro de Hacienda"}
    assert bitacora[1]["motivo"] == "Nombramiento publicado"
    assert cliente.get("/v1/figuras").json()["figuras"] == []
    assert len(cliente.get("/v1/figuras", params={"archivadas": True}).json()["figuras"]) == 1


def test_anyone_proposes_and_a_verifier_decides(cliente):
    ana, vero = cuenta(cliente, "ana"), cuenta(cliente, "vero", "verificador")
    propuesta = {"nombre_completo": "Laura Díaz", "cargo": "Alcaldesa", "url_fuente": "https://www.alcaldia.gov.co/alcaldesa"}
    p = cliente.post("/v1/propuestas-figura", json=propuesta, headers=ana).json()
    assert cliente.get("/v1/propuestas-figura", headers=ana).status_code == 403
    pendientes = cliente.get("/v1/propuestas-figura", headers=vero).json()["propuestas"]
    assert [x["propuesta_por"] for x in pendientes] == ["ana"]
    sin_motivo = cliente.post(f"/v1/propuestas-figura/{p['id']}/resolucion", json={"aceptar": False}, headers=vero)
    assert sin_motivo.status_code == 409
    figura_id = cliente.post(f"/v1/propuestas-figura/{p['id']}/resolucion", json={"aceptar": True}, headers=vero).json()["figura_id"]
    assert cliente.get(f"/v1/figuras/{figura_id}").json()["cargo"] == "Alcaldesa"
    otra_vez = cliente.post("/v1/propuestas-figura", json={**propuesta, "nombre_completo": "laura diaz"}, headers=ana)
    assert otra_vez.status_code == 409 and otra_vez.json()["error"]["codigo"] == "figura_ya_registrada"


def test_topic_actors_still_match_exactly(cliente):
    """Los temas del día siguen ligando un actor solo si el nombre coincide exactamente (sin tildes ni mayúsculas)."""
    vero = cuenta(cliente, "vero", "verificador")
    f = cliente.post("/v1/figuras", json={"nombre_completo": "Ana María Ruiz", "cargo": "Ministra", "url_fuente_cargo": FUENTE}, headers=vero).json()
    with psycopg.connect(cliente.db_url) as c:
        assert str(c.execute("SELECT temas.buscar_figura('ana maria ruiz')").fetchone()[0]) == f["id"]
        assert c.execute("SELECT temas.buscar_figura('Ana Ruiz')").fetchone()[0] is None
