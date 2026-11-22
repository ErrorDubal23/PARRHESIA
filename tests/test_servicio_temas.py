"""Servicio de temas: lectura de RSS, agrupación y declaraciones, con medios e IA simulados."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from defusedxml.common import EntitiesForbidden

from servicios.temas import recolector, trabajador

AHORA = datetime.now(timezone.utc)


def rss(medio: str, items: list[tuple[str, str]]) -> bytes:
    fecha = (AHORA - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    cuerpo = "".join(f"<item><title>{t}</title><link>https://{medio}.co/{i}</link><description><![CDATA[<p>{d}</p>]]>"
                     f"</description><pubDate>{fecha}</pubDate></item>" for i, (t, d) in enumerate(items))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>{medio}</title>{cuerpo}</channel></rss>'.encode()


def test_reads_rss_and_atom_and_strips_html():
    articulos = recolector.leer_rss(rss("medio", [("Reforma &amp; IVA", "El ministro dijo: <b>el IVA baja</b>")]))
    assert articulos[0]["titulo"] == "Reforma & IVA" and articulos[0]["resumen"] == "El ministro dijo: el IVA baja"
    atom = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Tema</title><link href="https://x.co/1"/>'
            b'<summary>Resumen</summary><updated>2026-11-21T10:00:00Z</updated></entry></feed>')
    assert recolector.leer_rss(atom)[0]["url"] == "https://x.co/1"


def test_malicious_xml_is_refused():
    bomba = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel><item><title>&b;</title></item></channel></rss>'
    with pytest.raises(EntitiesForbidden):
        recolector.leer_rss(bomba)


def test_window_ends_at_the_last_three_hour_cut():
    desde, hasta = trabajador.ventana(datetime(2026, 11, 21, 14, 37, tzinfo=timezone.utc))
    assert hasta == datetime(2026, 11, 21, 12, tzinfo=timezone.utc) and hasta - desde == timedelta(hours=24)


class Mundo:
    """Tres medios que hablan de la reforma y una IA que agrupa y extrae como lo haría un modelo."""

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        if peticion.url.host.endswith(".co") and peticion.url.host not in ("openrouter.ai",):
            medio = peticion.url.host.split(".")[0]
            items = [("La reforma tributaria llega al Congreso",
                      f"El ministro dijo que \"el recaudo subirá 2,3 %\" según {medio}"),
                     ("Partido de fútbol", "Resultado del domingo")]
            return httpx.Response(200, content=rss(medio, items))
        cuerpo = json.loads(peticion.content)
        entrada = json.loads(cuerpo["messages"][1]["content"])
        if "articulos" in entrada:
            ids = [a["id"] for a in entrada["articulos"] if "reforma" in a["titulo"].lower()]
            contenido = {"grupos": [{"titulo": "Reforma tributaria en el Congreso", "etiqueta": "reforma_tributaria", "articulos": ids}]}
        else:
            contenido = {"declaraciones": [{"actor": "el ministro", "texto_citado": "el recaudo subirá 2,3 %"}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(contenido, ensure_ascii=False)}}]})


@pytest.fixture
def entorno(test_db_url, monkeypatch):
    from servicios.ia import trabajador as ia
    monkeypatch.setattr(recolector, "MEDIOS", [(m, f"https://{m}.co", f"https://{m}.co/rss") for m in ("uno", "dos", "tres")])
    with psycopg.connect(test_db_url, autocommit=True) as pg:
        pg.execute("TRUNCATE temas.entrega_evento, temas.evento_salida, temas.declaracion_reportada, temas.tema_articulo,"
                   " temas.tema, temas.articulo, temas.medio, ia.intento, ia.trabajo, ia.credencial CASCADE")
        pg.execute("CALL ia.configurar_credencial('groq_cuenta_1', 'groq', true)")
        with httpx.Client(transport=httpx.MockTransport(Mundo())) as http:
            yield pg, http, (lambda: ia.procesar_uno(pg, http, {"groq_cuenta_1": ("groq", "x")}))


def test_collect_group_and_extract_with_verbatim_quotes(entorno):
    pg, http, correr_ia = entorno
    trabajador.registrar_medios(pg)
    assert trabajador.recolectar(pg, http) == 6
    assert trabajador.recolectar(pg, http) == 0          # los repetidos se ignoran
    desde, hasta = trabajador.ventana(AHORA + timedelta(hours=3))
    assert trabajador.agrupar(pg, desde, hasta) == "esperando"
    assert correr_ia() == "ok"
    assert trabajador.agrupar(pg, desde, hasta) == "hecho"
    temas = pg.execute("SELECT titulo, total_medios, total_articulos FROM temas.temas_actuales()").fetchall()
    assert temas == [("Reforma tributaria en el Congreso", 3, 3)]  # el fútbol no es un tema
    assert trabajador.extraer_declaraciones(pg, desde, hasta) == 3
    while correr_ia() is not None:
        pass
    assert trabajador.extraer_declaraciones(pg, desde, hasta) == 0
    citas = pg.execute("SELECT actor, texto_citado FROM temas.declaracion_reportada").fetchall()
    assert citas == [("el ministro", "el recaudo subirá 2,3 %")] * 3
    # Cada declaración queda en el outbox para el servicio de verificación
    assert pg.execute("SELECT count(*) FROM temas.eventos_pendientes('verificacion', ARRAY['declaracion_reportada_creada'])").fetchone()[0] == 3


def test_api_lists_topics_and_their_page(entorno, test_db_url, monkeypatch):
    pg, http, correr_ia = entorno
    trabajador.registrar_medios(pg)
    trabajador.recolectar(pg, http)
    desde, hasta = trabajador.ventana(AHORA + timedelta(hours=3))
    trabajador.agrupar(pg, desde, hasta)
    correr_ia()
    trabajador.agrupar(pg, desde, hasta)
    from fastapi.testclient import TestClient
    from servicios.temas.api import app
    monkeypatch.setenv("PG_URL_TEMAS", test_db_url)
    with TestClient(app) as cliente:
        [tema] = cliente.get("/v1/temas").json()["temas"]
        pagina = cliente.get(f"/v1/temas/{tema['id']}").json()
        assert tema["etiqueta"] == "reforma_tributaria" and len(pagina["articulos"]) == 3
        assert {m["nombre"] for m in cliente.get("/v1/medios").json()["medios"]} == {"uno", "dos", "tres"}
