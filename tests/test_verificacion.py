"""Esquema verificacion (migración 0006): las garantías centrales del proyecto."""

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
        c.execute(
            "TRUNCATE social.cambio_rol, verificacion.entrega_evento, verificacion.evento_salida, verificacion.revision_humana,"
            " verificacion.resultado_prueba, verificacion.evidencia, verificacion.verificacion,"
            " verificacion.afirmacion, verificacion.procesamiento,"
            " oficial.observacion, oficial.descarga, oficial.serie, oficial.indicador, oficial.fuente,"
            " social.usuario, social.publicacion CASCADE"
        )


@pytest.fixture
def oficial(db):
    """Una serie aprobada de desempleo con agosto aceptado y septiembre en cuarentena."""
    fuente = db.execute("INSERT INTO oficial.fuente (codigo, nombre, rol) VALUES ('dane', 'DANE', 'productor')"
                        " RETURNING id").fetchone()[0]
    indicador = db.execute("INSERT INTO oficial.indicador (codigo, categoria) VALUES ('unemployment', 'economia')"
                           " RETURNING id").fetchone()[0]
    serie = db.execute(
        "INSERT INTO oficial.serie (codigo, indicador_id, fuente_productora_id, fuente_canal_id, variante, nombre,"
        " unidad, etiqueta_unidad, frecuencia, geografia, huella_contenido, aprobada)"
        " VALUES ('unemployment_rate_national', %s, %s, %s, 'tasa', 'Desempleo', '%%', '%%', 'mensual', 'national',"
        " 'h', true) RETURNING id", (indicador, fuente, fuente)).fetchone()[0]
    descarga = uuid.uuid4()
    db.execute("INSERT INTO oficial.descarga (id, serie_id, canal, descargado_en) VALUES (%s, %s, 'dane', now())",
               (descarga, serie))
    obs = {}
    for periodo, valor, estado in (("2026-08", "9.3", "aceptada"), ("2026-09", "8.9", "en_cuarentena")):
        obs[periodo] = uuid.uuid4()
        db.execute("INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado,"
                   " estado_contraste) VALUES (%s, %s, %s, %s, 'national', %s, %s, 'paso')",
                   (obs[periodo], serie, descarga, periodo, valor, estado))
    return obs


@pytest.fixture
def publicacion(db):
    autor = db.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', %s, NULL)", (HASH,)).fetchone()[0]
    return db.execute("CALL social.publicar(%s, 'En agosto el desempleo fue 8,1 %%', NULL, NULL, NULL, NULL)",
                      (autor,)).fetchone()[0]


def afirmar(db, publicacion, valor="8.1", periodo="2026-08"):
    db.execute("CALL verificacion.registrar_afirmaciones('publicacion', %s, NULL, %s, NULL)", (publicacion, Jsonb([{
        "texto_citado": "el desempleo fue 8,1 %", "codigo_indicador": "unemployment", "variante": "tasa",
        "periodo_desde": periodo, "periodo_hasta": periodo, "territorio": "national", "valor_dicho": valor,
        "unidad_dicha": "%", "comparacion": "nivel", "confianza": 0.95}])))
    return db.execute("SELECT id FROM verificacion.afirmacion WHERE publicacion_id = %s", (publicacion,)).fetchone()[0]


def verificar(db, afirmacion, evidencia, conclusion="se_debilita", explicacion="El dato oficial de 2026-08 es 9,3 %.",
              serie="unemployment_rate_national", validada=True):
    return db.execute(
        "CALL verificacion.registrar_verificacion(%s, %s, %s, %s, %s, 'motor-1', %s, %s, NULL)",
        (afirmacion, serie, conclusion, explicacion, validada,
         Jsonb([{"observacion_id": str(o), "rol": "citada"} for o in evidencia]),
         Jsonb([{"codigo": "dato_provisional", "resultado": "sin_brecha", "detalle": None}])),
    ).fetchone()[0]


def test_prefilter_lets_through_only_numbers_about_the_indicators(db):
    consulta = "SELECT verificacion.requiere_extraccion(%s)"
    assert db.execute(consulta, ("No me gusta este gobierno",)).fetchone()[0] is False
    assert db.execute(consulta, ("Tengo 3 perros",)).fetchone()[0] is False
    assert db.execute(consulta, ("La INFLACION llegó a 5,2 %",)).fetchone()[0] is True


def test_claim_needs_one_existing_origin(db, publicacion):
    with pytest.raises(psycopg.errors.RaiseException, match="origen_inexistente"):
        afirmar(db, uuid.uuid4())
    with pytest.raises(psycopg.errors.CheckViolation, match="afirmacion_un_solo_origen"):
        db.execute("INSERT INTO verificacion.afirmacion (posicion, texto_citado, confianza_extraccion)"
                   " VALUES (1, 'sin texto de origen', 1)")


def test_verification_flow_and_post_status(db, oficial, publicacion):
    estado = "SELECT verificacion.estado_publicacion(%s)"
    assert db.execute(estado, (publicacion,)).fetchone()[0] == "pendiente"
    a = afirmar(db, publicacion)
    assert db.execute(estado, (publicacion,)).fetchone()[0] == "pendiente"
    v = verificar(db, a, [oficial["2026-08"]])
    assert db.execute(estado, (publicacion,)).fetchone()[0] == "lista"
    assert db.execute("SELECT version, conclusion FROM verificacion.verificacion_vigente(%s)", (a,)).fetchone() == (1, "se_debilita")
    [evento] = db.execute("SELECT datos FROM verificacion.evento_salida").fetchall()
    assert evento[0]["publicacion"] == str(publicacion) and evento[0]["conclusion"] == "se_debilita"
    v2 = verificar(db, a, [oficial["2026-08"]], conclusion="se_invierte")
    assert v2 != v and db.execute("SELECT version FROM verificacion.verificacion_vigente(%s)", (a,)).fetchone()[0] == 2
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("UPDATE verificacion.verificacion SET conclusion = 'se_sostiene'")


def test_opinion_without_numbers_is_marked_and_not_pending(db, publicacion):
    db.execute("CALL verificacion.registrar_procesamiento('publicacion', %s, 'sin_cifras')", (publicacion,))
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (publicacion,)).fetchone()[0] == "sin_cifras"


def test_quarantined_observation_cannot_be_evidence(db, oficial, publicacion):
    a = afirmar(db, publicacion, periodo="2026-09")
    with pytest.raises(psycopg.errors.RaiseException, match="evidencia_no_aceptada"):
        verificar(db, a, [oficial["2026-09"]], explicacion="El dato oficial es 8,9 %.")


def test_conclusion_without_evidence_is_refused_at_commit(db, oficial, publicacion):
    a = afirmar(db, publicacion)
    with pytest.raises(psycopg.errors.RaiseException, match="sin_evidencia"):
        verificar(db, a, [], explicacion="Se sostiene.")
    assert db.execute("SELECT count(*) FROM verificacion.verificacion").fetchone()[0] == 0
    assert db.execute("SELECT estado FROM verificacion.afirmacion WHERE id = %s", (a,)).fetchone()[0] == "extraida"


def test_explanation_with_an_unsupported_number_is_refused(db, oficial, publicacion):
    a = afirmar(db, publicacion)
    with pytest.raises(psycopg.errors.RaiseException, match="cifra_sin_respaldo"):
        verificar(db, a, [oficial["2026-08"]], explicacion="El dato oficial es 9,3 %, unos 1,2 puntos más.")
    assert db.execute("SELECT count(*) FROM verificacion.verificacion").fetchone()[0] == 0
    # Las cifras permitidas: el valor oficial, el valor dicho y los números del periodo.
    verificar(db, a, [oficial["2026-08"]], explicacion="Para 2026-08 el texto dice 8,1 % y el dato oficial es 9,3 %.")


def test_no_comparable_data_has_no_series_and_needs_no_evidence(db, oficial, publicacion):
    a = afirmar(db, publicacion)
    with pytest.raises(psycopg.errors.CheckViolation, match="verificacion_serie_si_hay_dato"):
        verificar(db, a, [], conclusion="sin_dato_comparable", explicacion="No hay dato comparable.")
    verificar(db, a, [], conclusion="sin_dato_comparable", explicacion="No hay dato comparable.", serie=None)
    assert db.execute("SELECT estado FROM verificacion.afirmacion WHERE id = %s", (a,)).fetchone()[0] == "no_verificable"
    with pytest.raises(psycopg.errors.RaiseException, match="serie_no_aprobada"):
        verificar(db, a, [oficial["2026-08"]], serie="serie_que_no_existe")


def test_only_verifiers_review_and_a_correction_reopens_the_claim(db, oficial, publicacion):
    a = afirmar(db, publicacion)
    v = verificar(db, a, [oficial["2026-08"]])
    ana = db.execute("SELECT id FROM social.usuario WHERE nombre_usuario = 'ana'").fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="sin_permiso"):
        db.execute("CALL verificacion.registrar_revision(%s, %s, 'confirmada', 'Revisado')", (v, ana))
    db.execute("CALL social.asignar_rol_consola(%s, 'verificador', 'Rol asignado para una prueba automática.')", (ana,))
    db.execute("CALL verificacion.registrar_revision(%s, %s, 'corregida', 'La variante es otra')", (v, ana))
    assert db.execute("SELECT verificacion.estado_publicacion(%s)", (publicacion,)).fetchone()[0] == "requiere_revision"
    with pytest.raises(psycopg.errors.RaiseException, match="solo puede cambiar el estado"):
        db.execute("UPDATE verificacion.afirmacion SET valor_dicho = 9.3")


def test_conclusion_summary_counts_current_versions(db, oficial, publicacion):
    a = afirmar(db, publicacion)
    verificar(db, a, [oficial["2026-08"]], conclusion="se_debilita")
    verificar(db, a, [oficial["2026-08"]], conclusion="se_invierte")  # la vigente
    filas = db.execute("SELECT conclusion, total, series FROM verificacion.resumen_conclusiones(%s, NULL, NULL)",
                       ([publicacion],)).fetchall()
    assert filas == [("se_invierte", 1, ["unemployment_rate_national"])]
