"""De punta a punta: publicación → filtro → dos lecturas → consenso → motor → explicación → API.

La base, el motor y los servicios corren de verdad; solo la IA está simulada (sin llamadas reales).
"""

from __future__ import annotations

import json
import uuid

import httpx
import psycopg
import pytest

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."
TEXTO = "En agosto de 2026 el desempleo bajó a 9,4 %, según el DANE."


class IASimulada:
    """Lee como lo haría un modelo; se puede hacer que un proveedor lea distinto o que la redacción invente cifras."""

    def __init__(self):
        self.valor_openrouter = "9.4"
        self.guia = ("La cifra coincide, pero el dato oficial va en la dirección contraria. Busca el dato del mes "
                     "anterior en el DANE y compáralo tú mismo para ver si subió o bajó.")
        self.neutral = True
        self.explicacion = "Según el DANE, en 2026-08 la tasa fue 9,4 %, frente a 8,1 % en 2026-07 y 8,6 % en 2025-08."

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(peticion.content)
        sistema, usuario = cuerpo["messages"][0]["content"], json.loads(cuerpo["messages"][1]["content"])
        if sistema.startswith("Ayudas a una persona"):
            contenido = {"guia": self.guia}
        elif sistema.startswith("Eres un revisor estricto"):
            contenido = {"neutral": self.neutral, "agrega_hechos": False, "motivo": "prueba"}
        elif sistema.startswith("Eres un lector preciso"):
            afirmaciones = []
            if "desempleo" in usuario["texto"]:
                valor = self.valor_openrouter if peticion.url.host == "openrouter.ai" else "9.4"
                afirmaciones = [{"texto_citado": "el desempleo bajó a 9,4 %", "codigo_indicador": "unemployment",
                                 "variante": "tasa", "periodo_desde": "2026-08", "periodo_hasta": "2026-08",
                                 "territorio": "national", "valor_dicho": valor, "unidad_dicha": "%",
                                 "comparacion": "nivel", "direccion": "baja", "confianza": 0.95}]
            contenido = {"afirmaciones": afirmaciones}
        else:
            contenido = {"explicacion": self.explicacion}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(contenido, ensure_ascii=False)}}]})


@pytest.fixture
def mundo(test_db_url):
    from servicios.ia import trabajador as ia
    from servicios.verificacion import trabajador as verif
    with psycopg.connect(test_db_url, autocommit=True) as pg:
        pg.execute("TRUNCATE social.cambio_rol, verificacion.guia_redactada, verificacion.verificacion_externa, verificacion.consulta_externa,"
                   " verificacion.afirmacion, verificacion.procesamiento, verificacion.evento_salida,"
                   " verificacion.fragmento_enlace, verificacion.enlace,"
                   " ia.intento, ia.trabajo, ia.credencial, social.usuario, social.publicacion, social.evento_salida,"
                   " oficial.observacion, oficial.descarga, oficial.serie, oficial.indicador, oficial.fuente CASCADE")
        dane = pg.execute("INSERT INTO oficial.fuente (codigo, nombre, rol) VALUES ('dane', 'DANE', 'productor') RETURNING id").fetchone()[0]
        ind = pg.execute("INSERT INTO oficial.indicador (codigo, categoria) VALUES ('unemployment', 'economia') RETURNING id").fetchone()[0]
        serie = pg.execute(
            "INSERT INTO oficial.serie (codigo, indicador_id, fuente_productora_id, fuente_canal_id, variante, nombre, unidad,"
            " etiqueta_unidad, frecuencia, geografia, huella_contenido, aprobada) VALUES ('dane_geih_unemployment_rate_national',"
            " %s, %s, %s, 'monthly_rate', 'Tasa de desempleo nacional', 'percent', 'Porcentaje', 'mensual', 'national', 'h', true)"
            " RETURNING id", (ind, dane, dane)).fetchone()[0]
        descarga = uuid.uuid4()
        pg.execute("INSERT INTO oficial.descarga (id, serie_id, canal, descargado_en) VALUES (%s, %s, 'dane', now())", (descarga, serie))
        for periodo, valor in (("2025-08", "8.6"), ("2026-07", "8.1"), ("2026-08", "9.4")):
            pg.execute("INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado,"
                       " estado_contraste) VALUES (%s, %s, %s, %s, 'national', %s, 'aceptada', 'paso')",
                       (uuid.uuid4(), serie, descarga, periodo, valor))
        llaves = {"groq_cuenta_1": ("groq", "x"), "openrouter_1": ("openrouter", "y")}
        for alias, (proveedor, _) in llaves.items():
            pg.execute("CALL ia.configurar_credencial(%s, %s, true)", (alias, proveedor))
        autor = pg.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@correo.co', %s, NULL)", (HASH,)).fetchone()[0]
        simulada = IASimulada()
        with httpx.Client(transport=httpx.MockTransport(simulada)) as http:
            def publicar(texto):
                return str(pg.execute("CALL social.publicar(%s, %s, NULL, NULL, NULL, NULL)", (autor, texto)).fetchone()[0])

            def correr():
                """Hace girar los dos trabajadores hasta que no quede nada por hacer."""
                for _ in range(30):
                    hubo = verif.procesar_textos(pg) + verif.procesar_afirmaciones(pg) + verif.procesar_guias(pg)
                    while ia.procesar_uno(pg, http, llaves) is not None:
                        hubo += 1
                        pg.execute("UPDATE ia.trabajo SET proximo_intento_en = now() WHERE estado = 'en_cola'")
                    if not hubo:
                        return
            yield pg, publicar, correr, simulada


def estado(pg, publicacion):
    return pg.execute("SELECT verificacion.estado_publicacion(%s)", (publicacion,)).fetchone()[0]


def test_a_claim_that_says_down_when_it_went_up_is_reversed(mundo, test_db_url, monkeypatch):
    pg, publicar, correr, _ = mundo
    p = publicar(TEXTO)
    assert estado(pg, p) == "pendiente"
    correr()
    assert estado(pg, p) == "lista"
    conclusion, explicacion, validada = pg.execute(
        "SELECT v.conclusion, v.explicacion, v.explicacion_validada FROM verificacion.verificacion v"
        " JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id WHERE a.publicacion_id = %s", (p,)).fetchone()
    assert conclusion == "se_invierte" and validada and "9,4" in explicacion
    # Dos lecturas, de proveedores distintos, que coincidieron
    assert pg.execute("SELECT consenso FROM verificacion.afirmacion WHERE publicacion_id = %s", (p,)).fetchone()[0] == "coinciden"
    assert sorted(r[0] for r in pg.execute("SELECT proveedor FROM ia.trabajo WHERE tipo = 'extraer_afirmaciones'")) == ["groq", "openrouter"]

    from fastapi.testclient import TestClient
    from servicios.verificacion.api import app
    monkeypatch.setenv("PG_URL_VERIFICACION", test_db_url)
    with TestClient(app) as cliente:
        r = cliente.get(f"/v1/textos/publicacion/{p}").json()
    assert r["estado"] == "lista"
    v = r["afirmaciones"][0]["verificacion"]
    assert v["conclusion"] == "se_invierte"
    assert [(e["rol"], e["periodo"], e["valor"]) for e in v["evidencia"]] == [
        ("citada", "2026-08", "9.4"), ("completa", "2025-08", "8.6"), ("completa", "2026-07", "8.1")]  # cifras como texto


def test_an_opinion_without_figures_never_reaches_the_ai(mundo):
    pg, publicar, correr, _ = mundo
    p = publicar("No me gusta cómo va el país, la verdad.")
    correr()
    assert estado(pg, p) == "sin_cifras"
    assert pg.execute("SELECT count(*) FROM ia.trabajo").fetchone()[0] == 0


def test_readings_that_disagree_wait_for_a_person(mundo):
    pg, publicar, correr, simulada = mundo
    simulada.valor_openrouter = "9"  # el segundo lector entiende otra cifra
    p = publicar(TEXTO.replace("9,4 %", "9,4 % (casi 9 %)"))
    correr()
    assert estado(pg, p) == "requiere_revision"
    assert pg.execute("SELECT count(*) FROM verificacion.verificacion").fetchone()[0] == 0  # sin conclusión automática


def test_an_explanation_with_an_invented_figure_is_replaced_by_the_rules_one(mundo):
    pg, publicar, correr, simulada = mundo
    simulada.explicacion = "El desempleo subió 1,3 puntos frente a julio."  # 1,3 no está en la evidencia: cálculo propio
    p = publicar(TEXTO)
    correr()
    explicacion = pg.execute("SELECT v.explicacion FROM verificacion.verificacion v JOIN verificacion.afirmacion a"
                             " ON a.id = v.afirmacion_id WHERE a.publicacion_id = %s", (p,)).fetchone()[0]
    assert "1,3" not in explicacion and explicacion.startswith("Según DANE, el texto dice que bajó, pero según los datos oficiales subió")
    fallidos = pg.execute("SELECT count(*) FROM ia.intento WHERE resultado = 'salida_invalida'").fetchone()[0]
    assert fallidos == 5  # la IA lo intentó cinco veces y el validador la rechazó las cinco


def test_a_text_the_database_rejects_goes_to_a_person_and_does_not_block_the_rest(mundo, monkeypatch):
    from servicios.verificacion import trabajador as verif
    pg, publicar, correr, _ = mundo
    rechazada = publicar(TEXTO)
    siguiente = publicar(TEXTO.replace("según el DANE", "dice el DANE"))
    original = verif._resolver_texto

    def con_rechazo(pg_, origen, origen_id, datos):
        if origen_id == rechazada:
            raise psycopg.errors.CheckViolation("lectura que no cumple una restricción")
        return original(pg_, origen, origen_id, datos)

    monkeypatch.setattr(verif, "_resolver_texto", con_rechazo)
    correr()
    assert estado(pg, rechazada) == "requiere_revision"
    assert estado(pg, siguiente) == "lista"


def test_a_pasted_news_text_goes_through_the_same_engine(mundo):
    # Decisión 29: un enlace o texto pegado se corta en fragmentos con cifras y cada uno se verifica igual.
    from servicios.verificacion import enlaces
    pg, _, correr, _ = mundo
    autor = pg.execute("SELECT id FROM social.usuario WHERE nombre_usuario = 'ana'").fetchone()[0]
    lectura = enlaces.leer_texto("Un párrafo de contexto sin números.\n\n" + TEXTO)
    enlace, _ = pg.execute("CALL verificacion.registrar_enlace(%s, NULL, '{}', %s, %s, %s, NULL, NULL)",
                           (autor, lectura.fecha_referencia, lectura.huella, lectura.candidatos)).fetchone()
    assert pg.execute("SELECT verificacion.estado_enlace(%s)", (enlace,)).fetchone()[0] == "pendiente"
    correr()
    assert pg.execute("SELECT verificacion.estado_enlace(%s)", (enlace,)).fetchone()[0] == "lista"
    assert pg.execute(
        "SELECT v.conclusion FROM verificacion.verificacion v JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id"
        " JOIN verificacion.fragmento_enlace f ON f.id = a.fragmento_enlace_id WHERE f.enlace_id = %s",
        (enlace,)).fetchone()[0] == "se_invierte"
    # La IA solo recibió el fragmento, nunca el texto completo.
    assert all("contexto sin números" not in r[0] for r in pg.execute("SELECT entrada::text FROM ia.trabajo"))


def guia(pg, publicacion):
    return pg.execute("SELECT verificacion.guia_de(a.id) FROM verificacion.afirmacion a WHERE a.publicacion_id = %s",
                      (publicacion,)).fetchone()[0]


def test_every_analysis_explains_why_and_how_to_check_it(mundo):
    # Decisión 34: por qué (consejos de reglas), cómo comprobarlo (pasos y fuente oficial) y la redacción
    # de la IA, publicada solo porque el juez de otro proveedor la consideró neutral.
    pg, publicar, correr, _ = mundo
    p = publicar(TEXTO)
    correr()
    g = guia(pg, p)
    assert [c["codigo"] for c in g["consejos"]] == ["se_invierte", "antes_de_compartir"]
    assert g["redaccion"].startswith("La cifra coincide")
    assert sorted(r[0] for r in pg.execute("SELECT proveedor FROM ia.trabajo WHERE tipo IN ('redactar_guia', 'juzgar_neutralidad')")) == [
        "groq", "openrouter"]


def test_a_guide_the_judge_finds_partial_is_not_published(mundo):
    pg, publicar, correr, simulada = mundo
    simulada.neutral = False
    p = publicar(TEXTO)
    correr()
    assert guia(pg, p)["redaccion"] is None                       # se muestra la guía por reglas
    assert pg.execute("SELECT neutral FROM verificacion.guia_redactada").fetchone()[0] is False


def test_a_guide_with_figures_never_reaches_the_database(mundo):
    pg, publicar, correr, simulada = mundo
    simulada.guia = "El desempleo fue de nueve coma cuatro, es decir 9,4 %, y conviene revisar el boletín del DANE."
    p = publicar(TEXTO)
    correr()
    assert guia(pg, p)["redaccion"] is None
    assert pg.execute("SELECT count(*) FROM verificacion.guia_redactada").fetchone()[0] == 0


def test_related_checks_from_other_outlets_keep_the_link_but_not_the_rating(mundo, monkeypatch):
    from servicios.verificacion import trabajador as verif
    pg, publicar, correr, _ = mundo
    p = publicar(TEXTO)
    correr()
    monkeypatch.setenv("GOOGLE_FACTCHECK_KEY", "llave-de-prueba")
    respuesta = {"claims": [{"text": "el desempleo bajó", "claimReview": [{
        "publisher": {"name": "Colombiacheck"}, "url": "https://colombiacheck.com/chequeos/desempleo",
        "title": "¿Bajó el desempleo en agosto?", "reviewDate": "2026-09-30T00:00:00Z", "textualRating": "Falso"}]}]}
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=respuesta))) as http:
        assert verif.procesar_otros_medios(pg, http) == 1
        assert verif.procesar_otros_medios(pg, http) == 0           # se consulta una sola vez
    medios = guia(pg, p)["otros_medios"]
    assert medios == [{"medio": "Colombiacheck", "titulo": "¿Bajó el desempleo en agosto?",
                       "url": "https://colombiacheck.com/chequeos/desempleo", "publicada_en": "2026-09-30"}]
    assert "Falso" not in str(medios)
