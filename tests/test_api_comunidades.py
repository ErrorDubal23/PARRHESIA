"""API de comunidades: flujos completos y que nada privado se filtre (feed, perfil, hilo, verificación)."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(test_db_url, monkeypatch, tmp_path):
    monkeypatch.setenv("PG_URL_SOCIAL", test_db_url)
    monkeypatch.setenv("PG_URL_VERIFICACION", test_db_url)
    monkeypatch.setenv("GRAFO_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("COOKIE_SEGURA", "false")
    monkeypatch.setenv("FOTOS_DIR", str(tmp_path))
    from servicios.social.api import app
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida, social.comunidad,"
                  " social.intento_acceso CASCADE")
    with TestClient(app) as c:
        yield c


def cuenta(cliente, nombre):
    clave = "clave-segura-123"
    cliente.post("/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": nombre.title(),
                                      "correo": f"{nombre}@correo.co", "clave": clave})
    token = cliente.post("/v1/sesiones", json={"correo": f"{nombre}@correo.co", "clave": clave}).cookies["parrhesia_sesion"]
    cliente.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_public_community_flow(cliente):
    ana, beto = cuenta(cliente, "ana"), cuenta(cliente, "beto")
    c = cliente.post("/v1/comunidades", json={"nombre": "Economía colombiana", "descripcion": "Cifras y debate sobre la economía",
                                              "privacidad": "publica"}, headers=ana).json()
    assert c["mi_papel"] == "administrador" and c["permisos"]["configurar"] is True
    assert cliente.post(f"/v1/comunidades/{c['id']}/publicaciones", json={"texto": "Hola"}, headers=beto).status_code == 403
    assert cliente.post(f"/v1/comunidades/{c['id']}/ingreso", json={}, headers=beto).json() == {"resultado": "integrante"}
    p = cliente.post(f"/v1/comunidades/{c['id']}/publicaciones", json={"texto": "La **inflación** bajó"}, headers=beto).json()
    assert p["comunidad"]["nombre"] == "Economía colombiana"
    assert [x["id"] for x in cliente.get(f"/v1/comunidades/{c['id']}/publicaciones").json()["publicaciones"]] == [p["id"]]
    assert cliente.put(f"/v1/publicaciones/{p['id']}/fijada", headers=beto).status_code == 403
    assert cliente.put(f"/v1/publicaciones/{p['id']}/fijada", headers=ana).status_code == 204
    assert cliente.get(f"/v1/publicaciones/{p['id']}").json()["fijada"] is True
    salida = cliente.delete(f"/v1/comunidades/{c['id']}/integrantes/yo", headers=ana)
    assert salida.status_code == 409 and salida.json()["error"]["codigo"] == "ultimo_administrador"
    acciones = [b["accion"] for b in cliente.get(f"/v1/comunidades/{c['id']}/bitacora").json()["bitacora"]]
    assert acciones[:2] == ["publicacion_fijada", "ingreso"]
    repetida = cliente.post("/v1/comunidades", json={"nombre": "ECONOMÍA colombiana", "descripcion": "Otra con el mismo nombre"}, headers=beto)
    assert repetida.status_code == 409 and repetida.json()["error"]["codigo"] == "comunidad_nombre_key"


def test_private_content_never_leaks(cliente):
    ana, beto, carla = cuenta(cliente, "ana"), cuenta(cliente, "beto"), cuenta(cliente, "carla")
    cliente.put("/v1/usuarios/ana/seguidores/yo", headers=carla)  # carla sigue a ana
    c = cliente.post("/v1/comunidades", json={"nombre": "Política fiscal", "descripcion": "Debate cerrado sobre el presupuesto",
                                              "reglas": "Cita tus fuentes", "privacidad": "privada"}, headers=ana).json()
    p = cliente.post(f"/v1/comunidades/{c['id']}/publicaciones", json={"texto": "El desempleo fue 9,4 % en agosto"}, headers=ana).json()
    # Quien no es integrante: ni en la comunidad, ni en el feed, ni en el perfil, ni en el hilo, ni en la verificación.
    assert cliente.get(f"/v1/comunidades/{c['id']}/publicaciones", headers=carla).status_code == 403
    assert cliente.get(f"/v1/comunidades/{c['id']}", headers=carla).json()["reglas"] is None
    assert cliente.get("/v1/feed", headers=carla).json()["publicaciones"] == []
    assert cliente.get("/v1/usuarios/ana/publicaciones", headers=carla).json()["publicaciones"] == []
    assert cliente.get(f"/v1/publicaciones/{p['id']}", headers=carla).status_code == 404
    assert cliente.get(f"/v1/publicaciones/{p['id']}").status_code == 404
    from servicios.verificacion.api import app as verificacion
    with TestClient(verificacion) as v:
        assert v.get(f"/v1/textos/publicacion/{p['id']}", headers=carla).status_code == 404
        assert v.get(f"/v1/textos/publicacion/{p['id']}", headers=ana).status_code == 200
    # Solicitud, aceptación y desde entonces sí lo ve.
    assert cliente.post(f"/v1/comunidades/{c['id']}/ingreso", json={"mensaje": "Soy economista"}, headers=beto).json()["resultado"] == "solicitud"
    assert cliente.get(f"/v1/comunidades/{c['id']}/solicitudes", headers=beto).status_code == 403
    solicitud = cliente.get(f"/v1/comunidades/{c['id']}/solicitudes", headers=ana).json()["solicitudes"][0]
    assert solicitud["mensaje"] == "Soy economista"
    assert cliente.post(f"/v1/comunidades/{c['id']}/solicitudes/{solicitud['id']}/resolucion", json={"aceptar": True}, headers=ana).status_code == 204
    assert cliente.get(f"/v1/publicaciones/{p['id']}", headers=beto).status_code == 200
    # Lo privado no se comparte fuera.
    compartir = cliente.post("/v1/publicaciones", json={"comparte_id": p["id"]}, headers=beto)
    assert compartir.status_code == 409 and compartir.json()["error"]["codigo"] == "publicacion_privada"


def test_roles_via_api(cliente):
    ana, beto, carla = cuenta(cliente, "ana"), cuenta(cliente, "beto"), cuenta(cliente, "carla")
    c = cliente.post("/v1/comunidades", json={"nombre": "Educación", "descripcion": "Datos y debate sobre educación"}, headers=ana).json()
    for u in (beto, carla):
        cliente.post(f"/v1/comunidades/{c['id']}/ingreso", json={}, headers=u)
    assert cliente.put(f"/v1/comunidades/{c['id']}/integrantes/beto/papel", json={"papel": "gestor"}, headers=carla).status_code == 403
    assert cliente.put(f"/v1/comunidades/{c['id']}/integrantes/beto/papel", json={"papel": "gestor"}, headers=ana).status_code == 200
    corta = cliente.post(f"/v1/comunidades/{c['id']}/expulsiones", json={"nombre_usuario": "carla", "motivo": "no"}, headers=beto)
    assert corta.status_code == 422
    assert cliente.post(f"/v1/comunidades/{c['id']}/expulsiones", json={"nombre_usuario": "carla", "motivo": "Insultos reiterados a otras personas"},
                        headers=beto).status_code == 204
    papeles = {i["nombre_usuario"]: i["papel"] for i in cliente.get(f"/v1/comunidades/{c['id']}/integrantes").json()["integrantes"]}
    assert papeles == {"ana": "administrador", "beto": "gestor"}
    assert cliente.get("/v1/comunidades", params={"mias": True}, headers=carla).json()["comunidades"] == []
    assert [x["nombre"] for x in cliente.get("/v1/comunidades", params={"q": "educ"}).json()["comunidades"]] == ["Educación"]
