"""Servicio de IA: validación de salidas y trabajador con un proveedor simulado (sin llamadas reales).

La prueba marcada `live` llama de verdad a Groq y OpenRouter con un texto corto
(uv run pytest -m live tests/test_servicio_ia.py).
"""

from __future__ import annotations

import json

import httpx
import psycopg
import pytest
from psycopg.types.json import Jsonb

from servicios.ia.formatos import SalidaInvalida, validar

TEXTO = "Según el DANE, en septiembre de 2026 el desempleo fue de 8,9 %. Me parece preocupante."
AFIRMACION = {"texto_citado": "el desempleo fue de 8,9 %", "codigo_indicador": "unemployment", "variante": "tasa",
              "periodo_desde": "2026-09", "periodo_hasta": "2026-09", "territorio": "national", "valor_dicho": "8.9",
              "unidad_dicha": "%", "comparacion": "nivel", "confianza": 0.95}


def respuesta(datos) -> str:
    return json.dumps(datos, ensure_ascii=False)


# --- Validación ---------------------------------------------------------------------------------


def test_valid_extraction_passes_and_value_is_normalized():
    salida = validar("extraer_afirmaciones", "```json\n" + respuesta({"afirmaciones": [{**AFIRMACION, "valor_dicho": "8,90"}]})
                     + "\n```", {"texto": TEXTO})
    assert salida["afirmaciones"][0]["valor_dicho"] == "8.9"


@pytest.mark.parametrize("cambio, motivo", [
    ({"texto_citado": "el desempleo llegó a 8,9 %"}, "no está textual"),
    ({"valor_dicho": "7.5"}, "no aparece en el texto"),
    ({"codigo_indicador": "pobreza"}, "formato"),
    ({"periodo_desde": "septiembre"}, "formato"),
])
def test_invented_or_malformed_extraction_is_rejected(cambio, motivo):
    with pytest.raises(SalidaInvalida, match=motivo):
        validar("extraer_afirmaciones", respuesta({"afirmaciones": [{**AFIRMACION, **cambio}]}), {"texto": TEXTO})


def test_explanation_cannot_use_numbers_outside_the_evidence():
    entrada = {"cifras_permitidas": ["8.2", "8.9", "2026", "9"]}
    ok = validar("redactar_explicacion", respuesta({"explicacion": "El texto dice 8,2 % y el dato oficial del DANE para 2026-09 es 8,9 %."}), entrada)
    assert "8,9" in ok["explicacion"]
    with pytest.raises(SalidaInvalida, match="no están en la evidencia"):
        validar("redactar_explicacion", respuesta({"explicacion": "Es 0,7 puntos más que lo dicho, según el DANE."}), entrada)


def test_grouping_cannot_invent_articles_or_put_numbers_in_titles():
    entrada = {"articulos": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    assert validar("agrupar_temas", respuesta({"grupos": [{"titulo": "Reforma tributaria", "etiqueta": "reforma_tributaria",
                                                           "articulos": ["a", "b"]}]}), entrada)["grupos"]
    with pytest.raises(SalidaInvalida, match="no estaba en la entrada"):
        validar("agrupar_temas", respuesta({"grupos": [{"titulo": "Reforma", "etiqueta": "reforma", "articulos": ["z"]}]}), entrada)
    with pytest.raises(SalidaInvalida, match="formato"):
        validar("agrupar_temas", respuesta({"grupos": [{"titulo": "IVA del 19 %", "etiqueta": "iva", "articulos": ["a"]}]}), entrada)


def test_not_json_is_invalid():
    with pytest.raises(SalidaInvalida, match="no contiene JSON"):
        validar("extraer_afirmaciones", "No encontré afirmaciones.", {"texto": TEXTO})


# --- Trabajador con proveedor simulado ---------------------------------------------------------


class ProveedorSimulado:
    """Responde según la llave usada: así se simula que una cuenta llegó a su límite."""

    def __init__(self):
        self.agotadas: set[str] = set()
        self.llamadas: list[tuple[str, str]] = []
        self.contenido = respuesta({"afirmaciones": [AFIRMACION]})
        self.por_modelo: dict[str, int] = {}   # modelo -> código de respuesta (404 retirado, 429 sin cupo)

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        llave = peticion.headers["Authorization"].removeprefix("Bearer ")
        modelo = json.loads(peticion.content)["model"]
        self.llamadas.append((peticion.url.host, modelo))
        if modelo in self.por_modelo:
            return httpx.Response(self.por_modelo[modelo], headers={"retry-after": "60"})
        if llave in self.agotadas:
            return httpx.Response(429, headers={"retry-after": "600"})
        return httpx.Response(200, json={"choices": [{"message": {"content": self.contenido}}],
                                         "usage": {"prompt_tokens": 120, "completion_tokens": 40}})


@pytest.fixture
def entorno(test_db_url):
    from servicios.ia import trabajador
    with psycopg.connect(test_db_url, autocommit=True) as pg:
        pg.execute("TRUNCATE ia.intento, ia.trabajo, ia.credencial")
        llaves = {"groq_cuenta_1": ("groq", "llave-1"), "groq_cuenta_2": ("groq", "llave-2"),
                  "openrouter_1": ("openrouter", "llave-or")}
        for alias, (proveedor, _) in llaves.items():
            pg.execute("CALL ia.configurar_credencial(%s, %s, true)", (alias, proveedor))
        simulado = ProveedorSimulado()
        with httpx.Client(transport=httpx.MockTransport(simulado)) as http:
            yield pg, http, llaves, simulado, trabajador


def encolar(pg, proveedor=None, entrada=None):
    return pg.execute("CALL ia.encolar_trabajo('extraer_afirmaciones', 'extraer_afirmaciones.v1', %s, %s, NULL, NULL)",
                      (Jsonb(entrada or {"texto": TEXTO}), proveedor)).fetchone()[0]


def test_worker_resolves_a_job_and_stores_the_validated_output(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    t = encolar(pg)
    assert trabajador.procesar_uno(pg, http, llaves) == "ok"
    estado, salida = pg.execute("SELECT estado, salida FROM ia.trabajo WHERE id = %s", (t,)).fetchone()
    assert estado == "terminado" and salida["afirmaciones"][0]["valor_dicho"] == "8.9"
    assert simulado.llamadas == [("api.groq.com", "openai/gpt-oss-120b")]
    assert trabajador.procesar_uno(pg, http, llaves) is None  # no queda trabajo


def test_exhausted_account_is_paused_and_the_job_moves_to_the_other(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    simulado.agotadas.add("llave-1")
    t = encolar(pg)
    assert trabajador.procesar_uno(pg, http, llaves) == "limite_alcanzado"
    assert trabajador.procesar_uno(pg, http, llaves) == "ok"  # la otra cuenta de Groq
    cuentas = pg.execute("SELECT credencial_alias, resultado FROM ia.intento WHERE trabajo_id = %s ORDER BY numero", (t,)).fetchall()
    assert cuentas == [("groq_cuenta_1", "limite_alcanzado"), ("groq_cuenta_2", "ok")]


def test_consensus_jobs_go_to_their_own_provider(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    encolar(pg, "groq")
    encolar(pg, "openrouter")
    assert trabajador.procesar_uno(pg, http, llaves) == "ok"
    assert trabajador.procesar_uno(pg, http, llaves) == "ok"
    assert sorted(simulado.llamadas) == [("api.groq.com", "openai/gpt-oss-120b"),
                                         ("openrouter.ai", "nvidia/nemotron-3-ultra-550b-a55b:free")]


def test_invalid_output_is_retried_later(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    simulado.contenido = respuesta({"afirmaciones": [{**AFIRMACION, "valor_dicho": "12"}]})  # cifra que no está
    t = encolar(pg)
    assert trabajador.procesar_uno(pg, http, llaves) == "salida_invalida"
    assert pg.execute("SELECT estado FROM ia.trabajo WHERE id = %s", (t,)).fetchone()[0] == "en_cola"


# --- En vivo -----------------------------------------------------------------------------------


@pytest.mark.live
def test_live_both_providers_read_the_same_claim():
    from servicios.ia.cliente import llamar
    from servicios.ia.proveedores import PROVEEDORES, cuentas
    from servicios.ia.trabajador import prompt
    llaves = cuentas()
    lecturas = {}
    with httpx.Client() as http:
        for nombre in ("groq", "openrouter"):
            alias = next(a for a, (p, _) in llaves.items() if p == nombre)
            r = llamar(http, PROVEEDORES[nombre], llaves[alias][1], PROVEEDORES[nombre].modelos["extraer_afirmaciones"][0],
                       prompt("extraer_afirmaciones.v1"), json.dumps({"texto": TEXTO, "fecha": "2026-11-21"}, ensure_ascii=False))
            lecturas[nombre] = validar("extraer_afirmaciones", r.texto, {"texto": TEXTO})["afirmaciones"]
    clave = lambda a: (a["codigo_indicador"], a["variante"], a["periodo_desde"], a["valor_dicho"])
    assert [clave(a) for a in lecturas["groq"]] == [("unemployment", "tasa", "2026-09", "8.9")]
    assert [clave(a) for a in lecturas["openrouter"]] == [("unemployment", "tasa", "2026-09", "8.9")]


def test_saturated_free_model_falls_back_to_the_next_one(entorno):
    pg, http_simulado, llaves, simulado, trabajador = entorno
    def saturar_el_primero(peticion: httpx.Request) -> httpx.Response:
        modelo = json.loads(peticion.content)["model"]
        simulado.llamadas.append((peticion.url.host, modelo))
        if modelo == "nvidia/nemotron-3-ultra-550b-a55b:free":
            return httpx.Response(429, text='{"error": "temporarily rate-limited upstream"}')
        return httpx.Response(200, json={"choices": [{"message": {"content": simulado.contenido}}]})
    encolar(pg, "openrouter")
    with httpx.Client(transport=httpx.MockTransport(saturar_el_primero)) as http:
        assert trabajador.procesar_uno(pg, http, llaves) == "ok"
    assert [m for _, m in simulado.llamadas] == ["nvidia/nemotron-3-ultra-550b-a55b:free", "baidu/ernie-5.5-flash-preview:free"]


def test_whole_month_or_year_written_as_days_is_normalized():
    from servicios.ia.formatos import periodo_canonico
    assert periodo_canonico("2026-08-01", "2026-08-31") == ("2026-08", "2026-08")
    assert periodo_canonico("2024-02-01", "2024-02-29") == ("2024-02", "2024-02")   # año bisiesto
    assert periodo_canonico("2025-01-01", "2025-12-31") == ("2025", "2025")
    assert periodo_canonico("2026-08-01", "2026-08-15") == ("2026-08-01", "2026-08-15")  # medio mes: no se toca
    salida = validar("extraer_afirmaciones", respuesta({"afirmaciones": [
        {**AFIRMACION, "periodo_desde": "2026-09-01", "periodo_hasta": "2026-09-30"}]}), {"texto": TEXTO})
    assert (salida["afirmaciones"][0]["periodo_desde"], salida["afirmaciones"][0]["periodo_hasta"]) == ("2026-09", "2026-09")


def test_a_reading_with_the_period_backwards_is_invalid():
    # "agosto de 2026 frente a agosto de 2025" leído como desde 2026-08 hasta 2025-08 (evaluación v1, 21 nov 2026):
    # se rechaza aquí, como lo haría la restricción afirmacion_periodos_validos de la base.
    with pytest.raises(SalidaInvalida):
        validar("extraer_afirmaciones", respuesta({"afirmaciones": [
            {**AFIRMACION, "periodo_desde": "2026-08", "periodo_hasta": "2025-08"}]}), {"texto": TEXTO})


# --- Migración 0034: prioridad, segundo lector y un hilo por proveedor ------------------------------


def test_queue_serves_what_a_person_waits_for_before_guides_and_judges(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    juez = pg.execute("CALL ia.encolar_trabajo('juzgar_neutralidad', 'juzgar_neutralidad.v2', %s, NULL, NULL, NULL)",
                      (Jsonb({"guia": "x"}),)).fetchone()[0]
    cifra = encolar(pg)        # llega después, pero alguien espera su conclusión
    tomado = pg.execute("SELECT id FROM ia.tomar_trabajo(%s, %s)", (trabajador.TIPOS, ["groq"])).fetchone()[0]
    assert tomado == cifra and tomado != juez
    assert pg.execute("SELECT ia.prioridad_trabajo('extraer_afirmaciones') < ia.prioridad_trabajo('redactar_guia')").fetchone()[0]


def test_second_reader_is_the_first_provider_with_an_enabled_account(entorno):
    pg, *_ = entorno
    elegir = lambda: pg.execute("SELECT ia.primer_proveedor_habilitado(ARRAY['gemini', 'openrouter'])").fetchone()[0]
    assert elegir() == "openrouter"                  # sin cuenta de Gemini, nunca se encola para Gemini
    pg.execute("CALL ia.configurar_credencial('gemini_1', 'gemini', true)")
    assert elegir() == "gemini"
    pg.execute("CALL ia.configurar_credencial('gemini_1', 'gemini', false)")
    pg.execute("CALL ia.configurar_credencial('openrouter_1', 'openrouter', false)")
    assert elegir() is None


def test_gemini_tries_the_next_model_when_one_is_retired_or_out_of_quota(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    pg.execute("CALL ia.configurar_credencial('gemini_1', 'gemini', true)")
    llaves = {**llaves, "gemini_1": ("gemini", "llave-gemini")}
    from servicios.ia.proveedores import GRATUITOS_GEMINI
    simulado.por_modelo = {GRATUITOS_GEMINI[0]: 404, GRATUITOS_GEMINI[1]: 429, GRATUITOS_GEMINI[2]: 503}
    encolar(pg, "gemini")
    assert trabajador.procesar_uno(pg, http, llaves) == "ok"
    assert [m for _, m in simulado.llamadas] == list(GRATUITOS_GEMINI[:4])
    assert pg.execute("SELECT pausada_hasta FROM ia.credencial WHERE alias = 'gemini_1'").fetchone()[0] is None


def test_each_provider_thread_only_takes_jobs_its_provider_can_do(entorno):
    pg, http, llaves, simulado, trabajador = entorno
    encolar(pg, "openrouter")
    assert trabajador.procesar_uno(pg, http, llaves, solo="groq") is None
    assert trabajador.procesar_uno(pg, http, llaves, solo="openrouter") == "ok"


def test_an_account_whose_key_is_gone_is_disabled(entorno, monkeypatch):
    pg, http, llaves, simulado, trabajador = entorno
    pg.execute("CALL ia.configurar_credencial('gemini_1', 'gemini', true)")
    monkeypatch.setattr(trabajador, "cuentas", lambda: {"groq_cuenta_1": ("groq", "x")})
    trabajador.sincronizar_cuentas(pg)
    habilitadas = {a for (a,) in pg.execute("SELECT alias FROM ia.credencial WHERE habilitada")}
    assert habilitadas == {"groq_cuenta_1"}
