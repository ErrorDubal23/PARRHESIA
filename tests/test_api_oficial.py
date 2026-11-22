"""API de datos oficiales contra la base temporal: serie completa, trazabilidad y cierre de alertas."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from servicios.comun.sesion import emitir


HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."


def sesion(pg, nombre, rol):
    """Una cuenta con una sesión real (las sesiones se revisan en la base en cada petición)."""
    uid = pg.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)", (nombre, nombre, f"{nombre}@x.co", HASH)).fetchone()[0]
    if rol != "usuario":
        pg.execute("CALL social.asignar_rol_consola(%s, %s, 'Rol asignado para una prueba automática.')", (uid, rol))
    jti, vence = pg.execute("CALL social.iniciar_sesion(%s, 'pruebas', interval '1 hour', NULL, NULL)", (uid,)).fetchone()
    return {"Authorization": f"Bearer {emitir(str(jti), str(uid), vence)}"}


@pytest.fixture
def mundo(test_db_url, monkeypatch):
    monkeypatch.setenv("PG_URL_OFICIAL", test_db_url)
    with psycopg.connect(test_db_url, autocommit=True) as pg:
        pg.execute("TRUNCATE social.cambio_rol, social.usuario CASCADE")
        pg.execute("TRUNCATE oficial.evento_alerta, oficial.alerta, oficial.comparacion_contraste, oficial.observacion,"
                   " oficial.archivo_original, oficial.descarga, oficial.serie, oficial.indicador, oficial.fuente CASCADE")
        f = pg.execute("INSERT INTO oficial.fuente (codigo, nombre, rol) VALUES ('dane', 'DANE', 'productor') RETURNING id").fetchone()[0]
        i = pg.execute("INSERT INTO oficial.indicador (codigo, categoria) VALUES ('inflation', 'economia') RETURNING id").fetchone()[0]
        s = pg.execute("INSERT INTO oficial.serie (codigo, indicador_id, fuente_productora_id, fuente_canal_id, variante, nombre,"
                       " unidad, etiqueta_unidad, frecuencia, geografia, huella_contenido, aprobada) VALUES ('ipc', %s, %s, %s,"
                       " 'annual', 'IPC anual', 'percent', 'Variación anual', 'mensual', 'national', 'h', true) RETURNING id",
                       (i, f, f)).fetchone()[0]
        d = uuid.uuid4()
        pg.execute("INSERT INTO oficial.descarga (id, serie_id, canal, descargado_en) VALUES (%s, %s, 'dane', now())", (d, s))
        pg.execute("INSERT INTO oficial.archivo_original (descarga_id, nombre, url, sha256, ubicacion) VALUES"
                   " (%s, 'anexo', 'https://dane.gov.co/anexo.xlsx', 'abc123', 'data/x')", (d,))
        obs = {}
        for periodo, valor, estado in (("2026-08", "6.24", "aceptada"), ("2026-09", "6.29", "aceptada"), ("2026-09", "6.30", "en_cuarentena")):
            obs[(periodo, estado)] = uuid.uuid4()
            pg.execute("INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado,"
                       " estado_contraste) VALUES (%s, %s, %s, %s, 'national', %s, %s, 'paso')",
                       (obs[(periodo, estado)], s, d, periodo, valor, estado))
        alerta = pg.execute("INSERT INTO oficial.alerta (serie_id, observacion_id, periodo, territorio, tipo, valor)"
                            " VALUES (%s, %s, '2026-09', 'national', 'historia_cambio', 6.30) RETURNING id",
                            (s, obs[("2026-09", "en_cuarentena")])).fetchone()[0]
        from servicios.oficial.api import app
        with TestClient(app) as cliente:
            yield cliente, obs, alerta, pg


def test_series_and_exact_values_as_text(mundo):
    cliente, _, _, _ = mundo
    assert [s["codigo"] for s in cliente.get("/v1/series").json()["series"]] == ["ipc"]
    serie = cliente.get("/v1/series/ipc").json()
    # 2026-09 cambió y quedó en cuarentena: no se muestra un valor anterior en su lugar
    assert [(v["periodo"], v["valor"]) for v in serie["valores"]] == [("2026-08", "6.24")]
    assert serie["alertas_abiertas"][0]["tipo"] == "historia_cambio"


def test_traceability_down_to_the_original_file(mundo):
    cliente, obs, _, _ = mundo
    dato = cliente.get(f"/v1/observaciones/{obs[('2026-09', 'aceptada')]}").json()
    assert dato["archivos_originales"] == [{"nombre": "anexo", "url": "https://dane.gov.co/anexo.xlsx", "sha256": "abc123"}]
    assert [(v["valor"], v["estado"]) for v in dato["versiones"]] == [("6.29", "aceptada"), ("6.30", "en_cuarentena")]


def test_only_verifiers_close_alerts_and_with_a_reason(mundo):
    cliente, _, alerta, pg = mundo
    usuario, vero = sesion(pg, "ana", "usuario"), sesion(pg, "vero", "verificador")
    assert cliente.post(f"/v1/alertas/{alerta}/cierre", json={"motivo": "Revisado"}, headers=usuario).status_code == 403
    assert cliente.post(f"/v1/alertas/{alerta}/cierre", json={"motivo": "El boletín confirma 6,30"}, headers=vero).status_code == 200
    otra_vez = cliente.post(f"/v1/alertas/{alerta}/cierre", json={"motivo": "otra vez"}, headers=vero)
    assert otra_vez.status_code == 409 and otra_vez.json()["error"]["codigo"] == "alerta_no_abierta"


def test_summary_shows_published_values_without_calculating(mundo):
    """El resumen trae el último valor vigente, el anterior y el de hace un año tal como se publicaron."""
    cliente, _, _, pg = mundo
    s = pg.execute("SELECT id FROM oficial.serie WHERE codigo = 'ipc'").fetchone()[0]
    # Las descargas son de solo inserción: la fecha de la fuente llega con una descarga nueva.
    d = pg.execute("INSERT INTO oficial.descarga (id, serie_id, canal, descargado_en, actualizado_fuente)"
                   " VALUES (gen_random_uuid(), %s, 'dane', now(), '2026-09-05') RETURNING id", (s,)).fetchone()[0]
    for periodo, valor in (("2025-08", 10.84), ("2026-08", 6.24)):
        pg.execute("INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado,"
                   " estado_contraste) VALUES (gen_random_uuid(), %s, %s, %s, 'national', %s, 'aceptada', 'paso')",
                   (s, d, periodo, valor))
    resumen = cliente.get("/v1/series").json()["series"][0]["resumen"]
    # 2026-09 quedó en cuarentena: el último vigente es 2026-08 y no se inventa otro
    assert (resumen["ultimo"]["periodo"], resumen["ultimo"]["valor"]) == ("2026-08", "6.24")
    assert resumen["ultimo"]["actualizado_fuente"] == "2026-09-05"
    assert resumen["ultimo"]["provisional"] is False  # la inflación no es provisional
    assert resumen["anterior"] == {"periodo": "2025-08", "valor": "10.84"}
    assert resumen["hace_un_anio"] == {"periodo": "2025-08", "valor": "10.84"}
    assert "diferencia" not in str(resumen)  # nada calculado
    detalle = cliente.get("/v1/series/ipc").json()
    assert detalle["indicador"] == "inflation" and detalle["resumen"] == resumen


def test_provisional_rule_is_shared():
    from datetime import date

    from servicios.comun.reglas_datos import es_provisional, hace_un_anio
    assert es_provisional("homicides", "2026-09", date(2026, 11, 21))
    assert not es_provisional("homicides", "2025-09", date(2026, 11, 21))
    assert not es_provisional("inflation", "2026-09", date(2026, 11, 21))
    assert hace_un_anio("2026-08") == "2025-08" and hace_un_anio("2026") == "2025"


def test_source_dates_are_normalized_or_left_out():
    from servicios.comun.reglas_datos import fecha_fuente
    assert fecha_fuente("2026-10-07") == "2026-10-07"
    assert fecha_fuente("2026-10-21T14:30:57+00:00") == "2026-10-21"
    assert fecha_fuente("08 de octubre de 2026") == "2026-10-08"
    assert fecha_fuente("pronto") is None and fecha_fuente(None) is None


def test_the_same_series_through_another_channel_is_listed_once(mundo):
    # Migración 0029: la inflación del DANE leída vía el Banco de la República no es otra serie.
    cliente, _, _, pg = mundo
    banrep = pg.execute("INSERT INTO oficial.fuente (codigo, nombre, rol) VALUES ('banrep_suameca', 'Banco de la República',"
                        " 'canal_acceso') RETURNING id").fetchone()[0]
    dane, ind = pg.execute("SELECT fuente_productora_id, indicador_id FROM oficial.serie WHERE codigo = 'ipc'").fetchone()
    pg.execute("INSERT INTO oficial.serie (codigo, indicador_id, fuente_productora_id, fuente_canal_id, variante, nombre,"
               " unidad, etiqueta_unidad, frecuencia, geografia, huella_contenido, aprobada) VALUES ('ipc_suameca', %s, %s,"
               " %s, 'annual', 'IPC anual', 'percent', 'Variación anual', 'mensual', 'national', 'h', true)", (ind, dane, banrep))
    series = cliente.get("/v1/series").json()["series"]
    assert [(s["codigo"], s["otros_canales"]) for s in series] == [
        ("ipc", [{"codigo": "ipc_suameca", "canal": "Banco de la República"}])]
