"""Esquema temas (migración 0005): la IA propone, la base decide y revisa las citas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
import pytest
from psycopg.types.json import Jsonb

INICIO = datetime(2026, 11, 21, 0, tzinfo=timezone.utc)
FIN = INICIO + timedelta(hours=24)


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c
        c.execute(
            "TRUNCATE temas.entrega_evento, temas.evento_salida, temas.declaracion_reportada, temas.tema_articulo,"
            " temas.tema, temas.articulo, temas.medio, social.evento_salida, social.figura_publica CASCADE"
        )


def medio(db, nombre):
    db.execute("CALL temas.configurar_medio(%s, %s, 'rss', %s, true)",
               (nombre, f"https://{nombre}.co", f"https://{nombre}.co/rss"))
    return db.execute("SELECT id FROM temas.medio WHERE nombre = %s", (nombre,)).fetchone()[0]


def articulos(db, medio_id, *items):
    datos = [{"url": f"https://{medio_id}.co/{i}", "titulo": titulo, "resumen": resumen, "texto": None,
              "publicado_en": (INICIO + timedelta(hours=1 + i)).isoformat()}
             for i, (titulo, resumen) in enumerate(items)]
    db.execute("CALL temas.registrar_articulos(%s, %s, NULL)", (medio_id, Jsonb(datos)))
    return [r[0] for r in db.execute(
        "SELECT id FROM temas.articulo WHERE medio_id = %s ORDER BY publicado_en", (medio_id,))]


def registrar_temas(db, grupos):
    return db.execute("CALL temas.registrar_temas(%s, %s, NULL, %s, NULL)", (INICIO, FIN, Jsonb(grupos))).fetchone()[0]


@pytest.fixture
def noticias(db):
    """Cuatro medios: tres hablan de la reforma, dos del desempleo."""
    a = articulos(db, medio(db, "medio_a"), ("La reforma avanza", "Debate en el Congreso"),
                  ("Desempleo en octubre", "El ministro dijo: \"el desempleo bajó al 8,2 %\""))
    b = articulos(db, medio(db, "medio_b"), ("Reforma tributaria", "Votación aplazada"),
                  ("Cifras de empleo", "Según el DANE la tasa fue 8,9 %"))
    c = articulos(db, medio(db, "medio_c"), ("Lo que trae la reforma", "Cambios al IVA"))
    d = articulos(db, medio(db, "medio_d"), ("Reforma: qué sigue", "Nuevo debate"))
    return {"reforma": [a[0], b[0], c[0], d[0]], "desempleo": [a[1], b[1]], "cita": a[1]}


def test_numbers_in_text_follow_colombian_format(db):
    cifras = db.execute("SELECT util.cifras_en_texto('Bajó de 1.234.567,5 a 9,28 % en 2026; otra vez 9,28')").fetchone()[0]
    assert cifras == [Decimal("1234567.5"), Decimal("9.28"), Decimal("2026")]
    assert db.execute("SELECT util.cifras_en_texto('sin números')").fetchone()[0] == []


def test_repeated_articles_are_ignored(db):
    m = medio(db, "medio_a")
    articulos(db, m, ("Uno", "uno"))
    assert db.execute(
        "CALL temas.registrar_articulos(%s, %s, NULL)",
        (m, Jsonb([{"url": f"https://{m}.co/0", "titulo": "Uno", "publicado_en": INICIO.isoformat()}]))
    ).fetchone()[0] == 0


def test_the_database_counts_outlets_and_drops_small_topics(db, noticias):
    guardados = registrar_temas(db, [
        {"titulo": "Desempleo", "etiqueta": "Desempleo", "articulos": [str(x) for x in noticias["desempleo"]]},
        {"titulo": "Reforma tributaria", "etiqueta": "reforma_tributaria", "articulos": [str(x) for x in noticias["reforma"]]},
    ])
    assert guardados == 1  # el desempleo solo tiene 2 medios
    assert db.execute("SELECT titulo, total_medios, total_articulos, posicion FROM temas.temas_actuales()").fetchall() == [
        ("Reforma tributaria", 4, 4, 1)]


def test_topic_groups_are_validated_all_or_nothing(db, noticias):
    reforma = [str(x) for x in noticias["reforma"]]
    with pytest.raises(psycopg.errors.RaiseException, match="articulo_repetido"):
        registrar_temas(db, [{"titulo": "Reforma", "etiqueta": "reforma", "articulos": reforma},
                             {"titulo": "Otra", "etiqueta": "otra", "articulos": reforma[:1]}])
    with pytest.raises(psycopg.errors.RaiseException, match="articulo_fuera_de_ventana"):
        registrar_temas(db, [{"titulo": "Reforma", "etiqueta": "reforma",
                              "articulos": reforma + ["00000000-0000-0000-0000-000000000000"]}])
    with pytest.raises(psycopg.errors.CheckViolation, match="tema_titulo_sin_cifras"):
        registrar_temas(db, [{"titulo": "Reforma del 19 %", "etiqueta": "reforma", "articulos": reforma}])
    assert db.execute("SELECT count(*) FROM temas.tema").fetchone()[0] == 0


def test_a_quote_must_be_verbatim_in_the_article(db, noticias):
    cita = noticias["cita"]
    with pytest.raises(psycopg.errors.RaiseException, match="cita_no_textual"):
        db.execute("CALL temas.registrar_declaraciones(%s, NULL, %s, NULL)", (cita, Jsonb([
            {"actor": "El ministro", "texto_citado": "el desempleo bajó al 8,2 %"},
            {"actor": "El ministro", "texto_citado": "el desempleo bajó al 7 %"},   # inventada
        ])))
    assert db.execute("SELECT count(*) FROM temas.declaracion_reportada").fetchone()[0] == 0  # ninguna del lote
    guardadas = db.execute("CALL temas.registrar_declaraciones(%s, NULL, %s, NULL)", (cita, Jsonb([
        {"actor": "El ministro", "texto_citado": "el desempleo bajó al 8,2 %"}]))).fetchone()[0]
    assert guardadas == 1
    [evento] = db.execute("SELECT tipo_evento FROM temas.eventos_pendientes('verificacion', ARRAY['declaracion_reportada_creada'])").fetchall()
    assert evento == ("declaracion_reportada_creada",)


def test_a_quote_without_numbers_is_not_stored(db, noticias):
    with pytest.raises(psycopg.errors.CheckViolation, match="declaracion_reportada_con_cifras"):
        db.execute("CALL temas.registrar_declaraciones(%s, NULL, %s, NULL)", (noticias["cita"], Jsonb([
            {"actor": "El ministro", "texto_citado": "el desempleo bajó"}])))


def test_actor_is_linked_only_to_an_exact_registered_figure(db, noticias):
    figura = db.execute(
        "INSERT INTO social.figura_publica (nombre_completo) VALUES ('Ministro de Trabajo') RETURNING id").fetchone()[0]
    assert db.execute("SELECT temas.buscar_figura('ministro de trabajo')").fetchone()[0] == figura
    assert db.execute("SELECT temas.buscar_figura('El ministro')").fetchone()[0] is None  # no adivina
    db.execute("CALL temas.registrar_declaraciones(%s, NULL, %s, NULL)", (noticias["cita"], Jsonb([
        {"actor": "Ministro de Trabajo", "texto_citado": "el desempleo bajó al 8,2 %"}])))
    assert db.execute("SELECT figura_id FROM temas.declaracion_reportada").fetchone()[0] == figura


def test_topic_page_lists_articles_and_reported_statements(db, noticias):
    registrar_temas(db, [{"titulo": "Mercado laboral", "etiqueta": "empleo",
                          "articulos": [str(x) for x in noticias["desempleo"] + noticias["reforma"][2:]]}])
    db.execute("CALL temas.registrar_declaraciones(%s, NULL, %s, NULL)", (noticias["cita"], Jsonb([
        {"actor": "El ministro", "texto_citado": "el desempleo bajó al 8,2 %"}])))
    tema = db.execute("SELECT tema_id FROM temas.temas_actuales()").fetchone()[0]
    filas = db.execute("SELECT tipo, medio, texto_citado FROM temas.pagina_tema(%s)", (tema,)).fetchall()
    assert sum(1 for f in filas if f[0] == "articulo") == 4
    assert [f for f in filas if f[0] == "declaracion"] == [("declaracion", "medio_a", "el desempleo bajó al 8,2 %")]
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        db.execute("UPDATE temas.tema SET total_medios = 10")


def test_coverage_and_activity_only_count_stored_articles(db, noticias):
    """Migración 0013: la huella de cobertura y la actividad salen de los artículos, sin estimar nada."""
    registrar_temas(db, [{"titulo": "Reforma tributaria", "etiqueta": "reforma_tributaria", "articulos": [str(x) for x in noticias["reforma"]]}])
    tema = db.execute("SELECT id, total_articulos FROM temas.tema").fetchone()
    cobertura = db.execute("SELECT medio, articulos FROM temas.cobertura_tema(%s)", (tema[0],)).fetchall()
    assert sorted(cobertura) == [("medio_a", 1), ("medio_b", 1), ("medio_c", 1), ("medio_d", 1)]
    actividad = db.execute("SELECT tramo, articulos FROM temas.actividad_tema(%s, 8)", (tema[0],)).fetchall()
    assert [t for t, _ in actividad] == list(range(1, 9))
    assert sum(n for _, n in actividad) == tema[1]  # cada artículo cae en un tramo, ninguno se pierde
    assert actividad[0][1] == 4  # todos se publicaron en la primera hora de la ventana
    assert db.execute("SELECT count(*) FROM temas.actividad_tema(%s, 0)", (tema[0],)).fetchone()[0] == 0


# --- Imagen de cada tema (migración 0028) ------------------------------------------------------------

FOTO = {"id": "abc123", "color": "#a08c70", "urls": {"regular": "https://images.unsplash.com/photo-1?w=1080"},
        "user": {"name": "Ana Fotógrafa", "links": {"html": "https://unsplash.com/@ana"}},
        "links": {"html": "https://unsplash.com/photos/abc123",
                  "download_location": "https://api.unsplash.com/photos/abc123/download"}}


def test_a_topic_image_is_searched_once_with_credit_and_reused_by_label(db, noticias, monkeypatch):
    import httpx
    from servicios.temas import imagenes
    llamadas = []

    def unsplash(peticion):
        llamadas.append((peticion.url.path, dict(peticion.url.params)))
        if peticion.url.path.endswith("/download"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"results": [FOTO]})

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "llave-de-prueba")
    registrar_temas(db, [{"titulo": "Reforma tributaria", "etiqueta": "reforma_tributaria",
                          "articulos": [str(x) for x in noticias["reforma"]]}])
    with httpx.Client(transport=httpx.MockTransport(unsplash)) as http:
        assert imagenes.completar(db, http) == 1
        assert imagenes.completar(db, http) == 0            # ya tiene: no se busca otra vez
    busqueda = llamadas[0][1]
    assert (busqueda["query"], busqueda["content_filter"]) == ("colombian pesos money", "high")   # nunca el título
    assert llamadas[1][0].endswith("/download")             # condición de Unsplash: avisar el uso
    assert db.execute("SELECT autor, url_autor FROM temas.imagen_tema").fetchone() == (
        "Ana Fotógrafa", "https://unsplash.com/@ana?utm_source=parrhesia&utm_medium=referral")
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("UPDATE temas.imagen_tema SET autor = 'otro'")


def test_without_a_key_nothing_is_searched_or_marked(db, noticias, monkeypatch):
    import httpx
    from servicios.temas import imagenes
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
    registrar_temas(db, [{"titulo": "Reforma tributaria", "etiqueta": "reforma_tributaria",
                          "articulos": [str(x) for x in noticias["reforma"]]}])
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        assert imagenes.completar(db, http) == 0
    assert db.execute("SELECT count(*) FROM temas.temas_sin_imagen('categoria-1')").fetchone()[0] == 1


def test_image_must_come_from_unsplash_with_its_credit(db, noticias):
    registrar_temas(db, [{"titulo": "Reforma tributaria", "etiqueta": "reforma_tributaria",
                          "articulos": [str(x) for x in noticias["reforma"]]}])
    tema = db.execute("SELECT tema_id FROM temas.temas_actuales()").fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("CALL temas.registrar_imagen_tema(%s, 'categoria-1', %s)",
                   (tema, Jsonb({"consulta": "x", "url": "https://otro.sitio/foto.jpg", "autor": "A",
                                 "url_autor": "https://unsplash.com/@a", "url_foto": "https://unsplash.com/photos/1"})))


def test_image_searches_never_use_names_from_the_title():
    # Migración 0030: con el título, "Escándalo Verónica Estrada" trajo una flor y el Clan del Golfo, unas cataratas.
    from servicios.temas.imagenes import consultas
    assert consultas("Escándalo Verónica Estrada") == ["Colombia landscape"]
    assert consultas("Denuncia por títulos falsos de congresista") == ["parliament building", "Colombia landscape"]
    assert consultas("Capturas del Clan del Golfo") == ["city street night", "Colombia landscape"]
    assert consultas("Tormentas eléctricas en Medellín") == [
        "Medellin storm clouds city", "storm clouds city", "Medellin Colombia", "Colombia landscape"]
