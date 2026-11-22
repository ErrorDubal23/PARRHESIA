"""Análisis de enlaces externos (decisión 29, migración 0025): lectura en memoria, SSRF, robots.txt,
fragmentos con cifras, procedimiento en la base (filtro, límite, reutilización) y API. Sin red real ni IA."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient
import httpx

from servicios.comun.sesion import emitir
from servicios.verificacion import enlaces
from servicios.verificacion.enlaces import EnlaceNoLeido

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."
CUERPO_PRIVADO = "Este párrafo largo es el cuerpo del artículo y no tiene cifras ni debe quedar guardado en ninguna parte"
PAGINA = f"""<html><head><title>Título de la etiqueta</title>
<meta property="og:title" content="El desempleo en agosto">
<meta property="og:site_name" content="Diario de Prueba">
<meta name="author" content="Redacción">
<meta property="article:published_time" content="2026-09-30T10:00:00-05:00">
<script>var desempleo = 99;</script></head><body>
<nav>Inicio · Desempleo 2026 · Menú</nav>
<p>{CUERPO_PRIVADO}.</p>
<p>Según el DANE, en agosto de 2026 el desempleo bajó a 9,4 %. El ministro habló en Bogotá.</p>
<p>La reunión empezó a las 10 de la mañana con 30 asistentes.</p>
<footer>Contacto 601 555 0000 desempleo</footer></body></html>"""
PUBLICAS = {"diario.co": ["93.184.216.34"], "otro.co": ["93.184.216.35"], "interno.co": ["10.0.0.5"],
            "metadatos.co": ["169.254.169.254"]}


def resolver(anfitrion):
    return PUBLICAS.get(anfitrion, ["127.0.0.1"])


def sitio(peticion: httpx.Request) -> httpx.Response:
    ruta, anfitrion = peticion.url.path, peticion.url.host
    if ruta == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /privado\n")
    if anfitrion == "diario.co" and ruta == "/nota":
        return httpx.Response(200, html=PAGINA)
    if ruta == "/salta-afuera":
        return httpx.Response(302, headers={"location": "http://interno.co/admin"})
    if ruta == "/salta":
        return httpx.Response(301, headers={"location": "https://diario.co/nota"})
    if ruta == "/pdf":
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    return httpx.Response(404)


@pytest.fixture
def http():
    with httpx.Client(transport=httpx.MockTransport(sitio)) as c:
        yield c


# --- Lectura en memoria ----------------------------------------------------------------------------

def test_reads_only_declared_metadata_and_paragraphs():
    metadatos, parrafos = enlaces.leer_html(PAGINA)
    assert metadatos == {"titulo": "El desempleo en agosto", "sitio": "Diario de Prueba", "autor": "Redacción",
                         "publicado": "2026-09-30T10:00:00-05:00"}
    assert not any("var desempleo" in p or "Menú" in p or "Contacto" in p for p in parrafos)  # script, nav, footer


def test_fragments_keep_sentences_with_digits_only():
    _, parrafos = enlaces.leer_html(PAGINA)
    assert enlaces.fragmentos(parrafos) == ["Según el DANE, en agosto de 2026 el desempleo bajó a 9,4 %.",
                                            "La reunión empezó a las 10 de la mañana con 30 asistentes."]


def test_follows_a_safe_redirect_and_reads(http):
    lectura = enlaces.leer_enlace(http, "https://DIARIO.co/salta#arriba", resolver)
    assert lectura.url == "https://diario.co/nota"
    assert str(lectura.fecha_referencia) == "2026-09-30"


@pytest.mark.parametrize("url, codigo", [
    ("ftp://diario.co/nota", "url_invalida"),
    ("https://usuario:clave@diario.co/nota", "url_invalida"),
    ("http://localhost:8000/v1/reconstruir", "destino_no_permitido"),
    ("http://interno.co/", "destino_no_permitido"),
    ("http://metadatos.co/latest/meta-data", "destino_no_permitido"),   # metadatos de la nube
    ("https://diario.co/salta-afuera", "destino_no_permitido"),          # redirección hacia adentro
    ("https://x.com/alguien/status/1", "red_cerrada"),
    ("https://m.facebook.com/post/1", "red_cerrada"),
    ("https://diario.co/privado/nota", "robots"),
    ("https://diario.co/pdf", "ilegible"),
])
def test_refuses_what_must_not_be_read(http, url, codigo):
    with pytest.raises(EnlaceNoLeido) as e:
        enlaces.leer_enlace(http, url, resolver)
    assert e.value.codigo == codigo


# --- Procedimiento en la base ----------------------------------------------------------------------

@pytest.fixture
def pg(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, verificacion.afirmacion, verificacion.procesamiento, verificacion.evento_salida,"
                  " verificacion.fragmento_enlace, verificacion.enlace, social.usuario CASCADE")
        yield c


def usuario(pg, nombre):
    return pg.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
                      (nombre, nombre, f"{nombre}@x.co", HASH)).fetchone()[0]


def registrar(pg, quien, lectura):
    return pg.execute("CALL verificacion.registrar_enlace(%s, %s, %s, %s, %s, %s, NULL, NULL)",
                      (quien, lectura.url, psycopg.types.json.Jsonb(lectura.metadatos), lectura.fecha_referencia,
                       lectura.huella, lectura.candidatos)).fetchone()


def test_the_database_keeps_only_fragments_that_pass_the_filter_and_never_the_body(pg, http):
    ana = usuario(pg, "ana")
    enlace, reutilizado = registrar(pg, ana, enlaces.leer_enlace(http, "https://diario.co/nota", resolver))
    assert not reutilizado
    assert [r[0] for r in pg.execute("SELECT texto FROM verificacion.fragmento_enlace WHERE enlace_id = %s"
                                     " ORDER BY posicion", (enlace,))] == [
        "Según el DANE, en agosto de 2026 el desempleo bajó a 9,4 %."]     # "10 de la mañana" no es de los 8
    eventos = pg.execute("SELECT tipo_evento FROM verificacion.evento_salida").fetchall()
    assert eventos == [("fragmento_enlace_creado",)]
    assert pg.execute("SELECT verificacion.estado_enlace(%s)", (enlace,)).fetchone()[0] == "pendiente"
    # El cuerpo no queda en ninguna tabla del esquema.
    volcado = pg.execute("SELECT string_agg(t::text, ' ') FROM (SELECT e::text AS t FROM verificacion.enlace e"
                         " UNION ALL SELECT f::text FROM verificacion.fragmento_enlace f"
                         " UNION ALL SELECT s::text FROM verificacion.evento_salida s) x").fetchone()[0]
    assert "cuerpo del artículo" not in volcado


def test_same_content_is_reused_without_new_work_and_limit_is_ten_per_hour(pg, http):
    ana = usuario(pg, "ana")
    lectura = enlaces.leer_enlace(http, "https://diario.co/nota", resolver)
    primero, _ = registrar(pg, ana, lectura)
    otra_vez, reutilizado = registrar(pg, usuario(pg, "beto"), lectura)
    assert (otra_vez, reutilizado) == (primero, True)
    assert pg.execute("SELECT count(*) FROM verificacion.evento_salida").fetchone()[0] == 1
    for i in range(9):
        registrar(pg, ana, enlaces.leer_texto(f"Texto número {i}: el desempleo fue 9,{i} % en agosto de 2026."))
    with pytest.raises(psycopg.errors.RaiseException, match="limite_enlaces"):
        registrar(pg, ana, enlaces.leer_texto("Otro texto: la inflación fue 6,1 % en agosto de 2026."))


def test_text_without_figures_is_registered_as_sin_cifras(pg):
    enlace, _ = registrar(pg, usuario(pg, "ana"), enlaces.leer_texto("Una opinión larga sobre el país, sin ningún número."))
    assert pg.execute("SELECT estado, url FROM verificacion.enlace WHERE id = %s", (enlace,)).fetchone() == ("sin_cifras", None)
    assert pg.execute("SELECT verificacion.estado_enlace(%s)", (enlace,)).fetchone()[0] == "sin_cifras"


def test_fragments_and_links_are_append_only(pg):
    enlace, _ = registrar(pg, usuario(pg, "ana"), enlaces.leer_texto("El desempleo fue 9,4 % en agosto de 2026, dice."))
    with pytest.raises(psycopg.errors.RaiseException):
        pg.execute("UPDATE verificacion.fragmento_enlace SET texto = 'El desempleo fue 1 %%' WHERE enlace_id = %s", (enlace,))
    with pytest.raises(psycopg.errors.RaiseException):
        pg.execute("DELETE FROM verificacion.enlace WHERE id = %s", (enlace,))


# --- API -------------------------------------------------------------------------------------------

def test_api_analyzes_a_link_and_explains_what_it_cannot_read(pg, http, test_db_url, monkeypatch):
    from servicios.verificacion import api
    monkeypatch.setenv("PG_URL_VERIFICACION", test_db_url)
    uid = usuario(pg, "ana")
    jti, vence = pg.execute("CALL social.iniciar_sesion(%s, 'pruebas', interval '1 hour', NULL, NULL)", (uid,)).fetchone()
    cabecera = {"Authorization": f"Bearer {emitir(str(jti), str(uid), vence)}"}
    api.app.dependency_overrides[api.cliente_http] = lambda: http
    api.app.dependency_overrides[api.resolver_dns] = lambda: resolver
    try:
        with TestClient(api.app) as cliente:
            assert cliente.post("/v1/enlaces", json={"url": "https://diario.co/nota"}).status_code == 401
            r = cliente.post("/v1/enlaces", json={"url": "https://diario.co/nota"}, headers=cabecera)
            assert r.status_code == 201 and not r.json()["reutilizado"]
            visto = cliente.get(f"/v1/enlaces/{r.json()['id']}").json()
            assert (visto["titulo"], visto["sitio"], visto["estado"]) == ("El desempleo en agosto", "Diario de Prueba", "pendiente")
            assert [f["estado"] for f in visto["fragmentos"]] == ["pendiente"]
            cerrada = cliente.post("/v1/enlaces", json={"url": "https://x.com/a/status/1"}, headers=cabecera)
            assert (cerrada.status_code, cerrada.json()["error"]["codigo"]) == (422, "red_cerrada")
            assert cliente.post("/v1/enlaces", json={}, headers=cabecera).status_code == 422
    finally:
        api.app.dependency_overrides.clear()


def test_a_fragment_with_only_a_year_is_not_worth_reading(pg):
    # Corrección 0026, vista en una nota real: "el salario mínimo para 2027" no tiene el valor de ningún indicador.
    enlace, _ = registrar(pg, usuario(pg, "ana"), enlaces.leer_texto(
        "Hay expectativa por el salario mínimo para 2027 en la mesa de concertación.\n\n"
        "El incremento salarial superior al 17% tuvo un efecto de 2% sobre la inflación."))
    assert [r[0] for r in pg.execute("SELECT texto FROM verificacion.fragmento_enlace WHERE enlace_id = %s", (enlace,))] == [
        "El incremento salarial superior al 17% tuvo un efecto de 2% sobre la inflación."]


def test_photo_captions_are_not_read():
    _, parrafos = enlaces.leer_html("<figure><img><figcaption>El salario mínimo de 2026 subió 23 %</figcaption></figure>"
                                    "<p>Texto de la nota.</p>")
    assert parrafos == ["Texto de la nota."]


def test_headlines_of_other_articles_are_not_read():
    # Visto con una nota real: "Capturaron a 10 presuntos integrantes…" era el título de otra noticia enlazada.
    _, parrafos = enlaces.leer_html('<p>El desempleo bajó a 8 % según la nota, dice el texto.</p>'
                                    '<li><a href="/otra">Capturaron a 10 presuntos integrantes por homicidios</a></li>'
                                    '<p>Más detalles en <a href="/x">este enlace</a> sobre la inflación de 5 %.</p>')
    assert parrafos == ["El desempleo bajó a 8 % según la nota, dice el texto.",
                        "Más detalles en este enlace sobre la inflación de 5 %."]
