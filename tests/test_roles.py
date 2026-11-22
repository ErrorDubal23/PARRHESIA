"""Roles por servicio (migración 0007): cada servicio escribe solo en su esquema."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c
        c.execute("RESET ROLE")
        c.execute(
            "TRUNCATE social.cambio_rol, verificacion.evidencia, verificacion.resultado_prueba, verificacion.evento_salida,"
            " verificacion.verificacion, verificacion.afirmacion, verificacion.procesamiento,"
            " oficial.observacion, oficial.descarga, oficial.serie, oficial.indicador, oficial.fuente,"
            " social.usuario, social.publicacion, social.evento_salida, ia.trabajo CASCADE"
        )


def como(db, rol):
    db.execute("RESET ROLE")
    db.execute(f"SET ROLE {rol}")


def test_each_service_cannot_write_in_another_schema(db):
    negados = {
        "svc_social": "INSERT INTO oficial.indicador (codigo, categoria) VALUES ('x', 'economia')",
        "svc_verificacion": "SELECT correo FROM social.usuario",
        "svc_ia": "SELECT * FROM verificacion.afirmacion",
        "svc_temas": "UPDATE ia.trabajo SET estado = 'fallido'",
        "svc_grafo": "INSERT INTO social.seguimiento VALUES (gen_random_uuid(), gen_random_uuid())",
        "svc_oficial": "SELECT * FROM social.publicacion",
    }
    for rol, sql in negados.items():
        como(db, rol)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(sql)


def test_social_service_publishes_through_its_procedures(db):
    como(db, "svc_social")
    autor = db.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', %s, NULL)", (HASH,)).fetchone()[0]
    p = db.execute("CALL social.publicar(%s, 'El #desempleo es 8,1 %%', NULL, NULL, NULL, NULL)", (autor,)).fetchone()[0]
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (p,)).fetchone()[0] == "pendiente"


def test_verification_service_works_only_through_functions(db):
    # Datos de partida, como superusuario: una serie aprobada con un valor aceptado y una publicación.
    f = db.execute("INSERT INTO oficial.fuente (codigo, nombre, rol) VALUES ('dane', 'DANE', 'productor') RETURNING id").fetchone()[0]
    i = db.execute("INSERT INTO oficial.indicador (codigo, categoria) VALUES ('unemployment', 'economia') RETURNING id").fetchone()[0]
    s = db.execute("INSERT INTO oficial.serie (codigo, indicador_id, fuente_productora_id, fuente_canal_id, variante,"
                   " nombre, unidad, etiqueta_unidad, frecuencia, geografia, huella_contenido, aprobada) VALUES"
                   " ('unemployment_rate_national', %s, %s, %s, 'tasa', 'D', '%%', '%%', 'mensual', 'national', 'h', true)"
                   " RETURNING id", (i, f, f)).fetchone()[0]
    d, o = uuid.uuid4(), uuid.uuid4()
    db.execute("INSERT INTO oficial.descarga (id, serie_id, canal, descargado_en) VALUES (%s, %s, 'dane', now())", (d, s))
    db.execute("INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado,"
               " estado_contraste) VALUES (%s, %s, %s, '2026-08', 'national', 9.3, 'aceptada', 'paso')", (o, s, d))
    autor = db.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', %s, NULL)", (HASH,)).fetchone()[0]
    p = db.execute("CALL social.publicar(%s, 'En agosto el desempleo fue 8,1 %%', NULL, NULL, NULL, NULL)", (autor,)).fetchone()[0]

    como(db, "svc_verificacion")
    texto = db.execute("SELECT social.texto_para_verificar('publicacion', %s)", (p,)).fetchone()[0]
    assert db.execute("SELECT verificacion.requiere_extraccion(%s)", (texto,)).fetchone()[0] is True
    trabajo, _ = db.execute("CALL ia.encolar_trabajo('extraer_afirmaciones', 'v1', %s, NULL, NULL, NULL)",
                            (Jsonb({"texto": texto}),)).fetchone()
    assert db.execute("SELECT estado FROM ia.resultado_trabajo(%s)", (trabajo,)).fetchone()[0] == "en_cola"
    db.execute("CALL verificacion.registrar_afirmaciones('publicacion', %s, %s, %s, NULL)", (p, trabajo, Jsonb([{
        "texto_citado": "el desempleo fue 8,1 %", "codigo_indicador": "unemployment", "variante": "tasa",
        "periodo_desde": "2026-08", "periodo_hasta": "2026-08", "territorio": "national", "valor_dicho": 8.1,
        "comparacion": "nivel", "confianza": 0.9}])))
    a = db.execute("SELECT id FROM verificacion.afirmacion").fetchone()[0]
    [vigente] = db.execute("SELECT observacion_id FROM oficial.observacion_en('unemployment_rate_national', '2026-08', 'national')").fetchall()
    db.execute("CALL verificacion.registrar_verificacion(%s, 'unemployment_rate_national', 'se_debilita',"
               " 'El dato oficial de 2026-08 es 9,3 %%.', true, 'motor-1', %s, '[]', NULL)",
               (a, Jsonb([{"observacion_id": str(vigente[0]), "rol": "citada"}])))
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (p,)).fetchone()[0] == "lista"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("SELECT * FROM oficial.observacion")


def test_graph_service_reads_outbox_and_records_trends(db):
    autor = db.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', %s, NULL)", (HASH,)).fetchone()[0]
    db.execute("CALL social.publicar(%s, 'hola #tema', NULL, NULL, NULL, NULL)", (autor,))
    como(db, "svc_grafo")
    ids = [r[0] for r in db.execute(
        "SELECT id FROM social.eventos_pendientes('grafo', ARRAY['usuario_creado','publicacion_creada','publicacion_etiquetada'])")]
    assert len(ids) == 3
    db.execute("CALL social.marcar_entregados('grafo', %s)", (ids,))
    db.execute("CALL social.registrar_tendencias(now() - interval '1 hour', now(), %s)", (Jsonb([{
        "etiqueta": "tema", "total_publicaciones": 5, "total_autores": 3, "diversidad": 0.7, "puntaje": 3.5,
        "posicion": 1}]),))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("SELECT texto FROM social.publicacion")
