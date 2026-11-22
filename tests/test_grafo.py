"""Servicio de grafo: outbox → Neo4j, las cuatro consultas y la reconstrucción.

Usan la base temporal de PostgreSQL de las pruebas y un Neo4j SOLO PARA PRUEBAS
(puerto 7688, perfil "pruebas" del docker-compose), que se vacía en cada prueba.
Nunca tocan el Neo4j de desarrollo. Se saltan si el de pruebas no está encendido:
    docker compose --profile pruebas up -d neo4j-pruebas
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

HASH = "$2b$12$abcdefghijklmnopqrstuuJ1kq0V1pMqQ5rJ8y0bQ0n4R0YbSx5W."


URL_PRUEBAS = "bolt://127.0.0.1:7688"


@pytest.fixture(scope="module")
def neo4j():
    import os
    os.environ["NEO4J_URL"] = os.environ.get("NEO4J_URL_PRUEBAS", URL_PRUEBAS)  # nunca el de desarrollo
    try:
        from servicios.grafo.neo4j_cliente import conectar_neo4j, crear_restricciones
        driver = conectar_neo4j()
    except Exception:
        pytest.skip("El Neo4j de pruebas no está encendido (docker compose --profile pruebas up -d neo4j-pruebas)")
    crear_restricciones(driver)
    yield driver
    driver.close()


@pytest.fixture
def pg(test_db_url, neo4j):
    from servicios.grafo.neo4j_cliente import vaciar
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.evento_salida, verificacion.evento_salida, social.usuario, social.publicacion,"
                  " social.etiqueta, social.figura_publica CASCADE")
        vaciar(neo4j)
        yield c


@pytest.fixture
def sinc(pg, neo4j):
    from servicios.grafo.sincronizador import Sincronizador
    return Sincronizador(pg, neo4j, lote=3)  # lotes pequeños: también se prueba el recorrido por lotes


def usuario(pg, nombre):
    return str(pg.execute("CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
                          (nombre, nombre.title(), f"{nombre}@correo.co", HASH)).fetchone()[0])


def publicar(pg, autor, texto, responde_a=None, comparte=None):
    return str(pg.execute("CALL social.publicar(%s, %s, %s, %s, NULL, NULL)",
                          (autor, texto, responde_a, comparte)).fetchone()[0])


def seguir(pg, a, b):
    pg.execute("CALL social.seguir(%s, %s)", (a, b))


def contar(neo4j, patron):
    registros, _, _ = neo4j.execute_query(f"MATCH {patron} RETURN count(*) AS n")
    return registros[0]["n"]


def huella_del_grafo(neo4j):
    registros, _, _ = neo4j.execute_query(
        "MATCH (a)-[r]->(b) RETURN labels(a)[0] + ':' + coalesce(a.id, a.nombre, a.codigo) + '-' + type(r) + "
        "coalesce(r.tipo, r.conclusion, '') + '->' + labels(b)[0] + ':' + coalesce(b.id, b.nombre, b.codigo) AS arista "
        "ORDER BY arista")
    return [r["arista"] for r in registros]


def test_outbox_events_become_the_graph(pg, neo4j, sinc):
    ana, beto = usuario(pg, "ana"), usuario(pg, "beto")
    seguir(pg, ana, beto)
    p = publicar(pg, beto, "Hablemos del #desempleo con @ana")
    pg.execute("CALL social.reaccionar(%s, %s, 'util')", (p, ana))
    resultado = sinc.procesar_pendientes()
    assert resultado.aplicados == 7  # 2 usuarios, seguir, publicar, etiqueta, mención, reacción
    assert contar(neo4j, "(:Usuario {nombre_usuario: 'ana'})-[:SIGUE]->(:Usuario {nombre_usuario: 'beto'})") == 1
    assert contar(neo4j, "(:Usuario)-[:PUBLICO]->(:Publicacion)-[:ETIQUETADA_CON]->(:Etiqueta {nombre: 'desempleo'})") == 1
    assert contar(neo4j, "(:Publicacion)-[:MENCIONA]->(:Usuario {nombre_usuario: 'ana'})") == 1
    assert contar(neo4j, "(:Usuario)-[:REACCIONO {tipo: 'util'}]->(:Publicacion)") == 1
    assert sinc.procesar_pendientes().aplicados == 0  # nada pendiente: no se repite


def test_deletions_and_removals_reach_the_graph(pg, neo4j, sinc):
    ana, beto = usuario(pg, "ana"), usuario(pg, "beto")
    seguir(pg, ana, beto)
    p = publicar(pg, beto, "hola")
    pg.execute("CALL social.reaccionar(%s, %s, 'me_gusta')", (p, ana))
    sinc.procesar_pendientes()
    pg.execute("CALL social.dejar_de_seguir(%s, %s)", (ana, beto))
    pg.execute("CALL social.quitar_reaccion(%s, %s)", (p, ana))
    pg.execute("CALL social.retirar_publicacion(%s, %s)", (p, beto))
    sinc.procesar_pendientes()
    assert contar(neo4j, "()-[:SIGUE]->()") == 0
    assert contar(neo4j, "()-[:REACCIONO]->()") == 0
    assert contar(neo4j, "(:Publicacion {estado: 'retirada_por_autor'})") == 1  # no se borra: se conserva la difusión


def test_rebuilding_from_postgres_gives_the_same_graph(pg, neo4j, sinc):
    ana, beto, caro = usuario(pg, "ana"), usuario(pg, "beto"), usuario(pg, "caro")
    seguir(pg, ana, beto)
    seguir(pg, beto, caro)
    p = publicar(pg, caro, "#reforma")
    publicar(pg, beto, None, comparte=p)
    seguir(pg, ana, caro)
    pg.execute("CALL social.dejar_de_seguir(%s, %s)", (ana, caro))
    sinc.procesar_pendientes()
    antes = huella_del_grafo(neo4j)
    assert sinc.reconstruir() == len(pg.execute("SELECT id FROM social.evento_salida").fetchall())
    assert huella_del_grafo(neo4j) == antes
    sinc.procesar_pendientes()  # aplicar dos veces lo mismo tampoco cambia nada (MERGE)
    assert huella_del_grafo(neo4j) == antes


def test_feed_has_my_follows_and_their_follows(pg, neo4j, sinc):
    ana, beto, caro, dani = (usuario(pg, n) for n in ("ana", "beto", "caro", "dani"))
    seguir(pg, ana, beto)
    seguir(pg, beto, caro)
    de_beto, de_caro, de_dani = publicar(pg, beto, "uno"), publicar(pg, caro, "dos"), publicar(pg, dani, "tres")
    sinc.procesar_pendientes()
    from servicios.grafo import consultas
    feed = {f["publicacion_id"]: f["distancia"] for f in consultas.feed(neo4j, ana)}
    assert feed == {de_beto: 1, de_caro: 2}  # dani no está en mi red
    seguir(pg, ana, caro)
    respuesta = publicar(pg, beto, "gracias", responde_a=de_caro)
    compartida = publicar(pg, beto, None, comparte=de_caro)
    sinc.procesar_pendientes()
    feed = {f["publicacion_id"]: f["distancia"] for f in consultas.feed(neo4j, ana)}
    assert feed[de_caro] == 1 and de_dani not in feed
    assert respuesta not in feed and compartida in feed   # las respuestas se leen en su hilo
    propia = publicar(pg, ana, "lo mío")                  # lo propio también está en mi inicio (auditoría FN-03)
    sinc.procesar_pendientes()
    assert {f["publicacion_id"]: f["distancia"] for f in consultas.feed(neo4j, ana)}[propia] == 1


def test_suggestions_are_friends_of_friends(pg, neo4j, sinc):
    ana, beto, caro, dani, eva = (usuario(pg, n) for n in ("ana", "beto", "caro", "dani", "eva"))
    for a, b in ((ana, beto), (ana, eva), (beto, caro), (beto, dani), (eva, caro)):
        seguir(pg, a, b)
    sinc.procesar_pendientes()
    from servicios.grafo import consultas
    assert [(s["nombre_usuario"], s["en_comun"]) for s in consultas.sugerencias(neo4j, ana)] == [("caro", 2), ("dani", 1)]


def test_diffusion_tree_of_reposts(pg, neo4j, sinc):
    ana, beto, caro = usuario(pg, "ana"), usuario(pg, "beto"), usuario(pg, "caro")
    original = publicar(pg, ana, "dato")
    primera = publicar(pg, beto, None, comparte=original)
    publicar(pg, caro, "lo comparto también", comparte=primera)
    sinc.procesar_pendientes()
    from servicios.grafo import consultas
    difusion = consultas.difusion(neo4j, original)
    assert difusion["alcance"] == 2 and difusion["profundidad_maxima"] == 2
    assert [(c["compartida_por"], c["profundidad"]) for c in difusion["compartidas"]] == [("beto", 1), ("caro", 2)]


def test_diverse_authors_weigh_more_in_trends(pg, neo4j, sinc):
    from servicios.grafo import consultas
    autores = [usuario(pg, f"autor{i}") for i in range(6)]
    # Grupo cerrado: los tres se siguen entre todos. Grupo diverso: nadie se sigue.
    for a in autores[:3]:
        for b in autores[:3]:
            if a != b:
                seguir(pg, a, b)
    for a in autores[:3]:
        publicar(pg, a, "#cerrado #cerrado")
        publicar(pg, a, "otra vez #cerrado")
    for a in autores[3:]:
        publicar(pg, a, "#diverso")
    sinc.procesar_pendientes()
    neo4j.execute_query("MATCH (u:Usuario) SET u.creado_en = datetime() - duration('P30D')")  # cuentas antiguas
    hasta = datetime.now(timezone.utc) + timedelta(minutes=5)
    filas = consultas.calcular_tendencias(neo4j, hasta - timedelta(hours=24), hasta)
    por_etiqueta = {f["etiqueta"]: f for f in filas}
    assert por_etiqueta["cerrado"]["diversidad"] == "0.0"  # 6 publicaciones, pero de un grupo cerrado
    assert por_etiqueta["diverso"]["diversidad"] == "1.0"
    assert filas[0]["etiqueta"] == "diverso"  # 3 publicaciones diversas pesan más que 6 de un grupo cerrado
    assert consultas.registrar_tendencias(pg, hasta - timedelta(hours=24), hasta, filas)
    assert pg.execute("SELECT count(*) FROM social.tendencia").fetchone()[0] == 2
    # La misma ventana otra vez (el trabajador se reinició en la misma hora): queda el primer cálculo, sin fallar.
    assert not consultas.registrar_tendencias(pg, hasta - timedelta(hours=24), hasta, filas)
    assert pg.execute("SELECT count(*) FROM social.tendencia").fetchone()[0] == 2


def test_new_accounts_do_not_count_for_trends(pg, neo4j, sinc):
    from servicios.grafo import consultas
    for i in range(4):
        publicar(pg, usuario(pg, f"nueva{i}"), "#campana")
    sinc.procesar_pendientes()
    hasta = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert consultas.calcular_tendencias(neo4j, hasta - timedelta(hours=24), hasta) == []


def test_verification_reaches_the_graph_and_old_versions_do_not_overwrite(pg, neo4j, sinc):
    ana = usuario(pg, "ana")
    p = publicar(pg, ana, "El desempleo es 8 %")
    for version, conclusion in ((2, "se_invierte"), (1, "se_debilita")):  # la versión 1 llega tarde
        pg.execute(
            "INSERT INTO verificacion.evento_salida (tipo_entidad, entidad_id, tipo_evento, datos) VALUES"
            " ('verificacion', 'v', 'verificacion_publicada', %s)",
            (psycopg.types.json.Jsonb({"publicacion": p, "serie": "unemployment_rate_national",
                                        "indicador": "unemployment", "conclusion": conclusion, "version": version}),))
    sinc.procesar_pendientes()
    registros, _, _ = neo4j.execute_query(
        "MATCH (:Publicacion {id: $p})-[v:VERIFICADA_CON]->(s:Serie) RETURN v.conclusion AS c, s.indicador AS i", p=p)
    assert [(r["c"], r["i"]) for r in registros] == [("se_invierte", "unemployment")]


def test_api_health_and_feed(pg, neo4j, sinc, monkeypatch, test_db_url):
    from fastapi.testclient import TestClient
    from servicios.grafo.api import app
    monkeypatch.setenv("PG_URL_GRAFO", test_db_url)
    ana, beto = usuario(pg, "ana"), usuario(pg, "beto")
    seguir(pg, ana, beto)
    p = publicar(pg, beto, "hola")
    sinc.procesar_pendientes()
    with TestClient(app) as cliente:
        assert cliente.get("/salud").json() == {"estado": "ok", "base": "ok", "neo4j": "ok"}
        respuesta = cliente.get(f"/v1/feed/{ana}").json()
        assert [f["publicacion_id"] for f in respuesta["publicaciones"]] == [p]
        assert cliente.post("/v1/reconstruir").json()["eventos_aplicados"] == 4


# --- Comunidades y descubrimiento (T11) ------------------------------------------------------

def comunidad(pg, creador, nombre, privacidad="publica"):
    return str(pg.execute("CALL social.crear_comunidad(%s, %s, 'Debate con cifras y fuentes', NULL, %s, NULL)",
                          (creador, nombre, privacidad)).fetchone()[0])


def entrar(pg, usuario_id, comunidad_id):
    pg.execute("CALL social.entrar_a_comunidad(%s, %s, NULL, NULL)", (usuario_id, comunidad_id))


def publicar_en(pg, autor, comunidad_id, texto):
    return str(pg.execute("CALL social.publicar_en_comunidad(%s, %s, %s, '{}', NULL)", (autor, comunidad_id, texto)).fetchone()[0])


def test_communities_reach_the_graph_and_rebuild_the_same(pg, neo4j, sinc):
    ana, beto = usuario(pg, "ana"), usuario(pg, "beto")
    c = comunidad(pg, ana, "Economía")
    entrar(pg, beto, c)
    p = publicar_en(pg, beto, c, "El #empleo en la región")
    sinc.procesar_pendientes()
    assert contar(neo4j, "(:Usuario)-[:INTEGRA]->(:Comunidad {privacidad: 'publica'})") == 2
    assert contar(neo4j, f"(:Publicacion {{id: '{p}'}})-[:EN]->(:Comunidad {{id: '{c}'}})") == 1
    pg.execute("CALL social.configurar_comunidad(%s, %s, NULL, NULL, NULL, 'privada')", (ana, c))
    pg.execute("CALL social.salir_de_comunidad(%s, %s)", (beto, c))
    sinc.procesar_pendientes()
    assert contar(neo4j, "(:Comunidad {privacidad: 'privada'})") == 1
    assert contar(neo4j, "(:Usuario)-[:INTEGRA]->(:Comunidad)") == 1   # la salida borró la relación
    antes = huella_del_grafo(neo4j)
    sinc.reconstruir()
    assert huella_del_grafo(neo4j) == antes                         # reconstruir desde PostgreSQL da lo mismo


def test_private_community_posts_do_not_reach_trends_or_feeds(pg, neo4j, sinc):
    from servicios.grafo import consultas
    autores = [usuario(pg, f"autor{i}") for i in range(3)]
    privada = comunidad(pg, autores[0], "Cerrada", "privada")
    for a in autores[1:]:
        pg.execute("INSERT INTO social.integrante (comunidad_id, usuario_id) VALUES (%s, %s)", (privada, a))
    for a in autores:
        publicar_en(pg, a, privada, "Solo aquí hablamos de #secreto")
    lector = usuario(pg, "lector")
    seguir(pg, lector, autores[0])
    sinc.procesar_pendientes()
    neo4j.execute_query("MATCH (u:Usuario) SET u.creado_en = datetime() - duration('P30D')")
    hasta = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert consultas.calcular_tendencias(neo4j, hasta - timedelta(hours=24), hasta) == []
    assert consultas.feed(neo4j, lector) == []                      # sigue al autor, pero no es integrante
    assert pg.execute("SELECT count(*) FROM social.tendencias_basicas(now() - interval '1 day', now() + interval '1 hour')").fetchone()[0] == 0


def test_suggestions_prefer_communities_outside_my_network(pg, neo4j, sinc):
    from servicios.grafo import consultas
    yo, amiga, lejana1, lejana2 = (usuario(pg, n) for n in ("quien_busca", "amiga", "lejana1", "lejana2"))
    seguir(pg, yo, amiga)
    publicar(pg, yo, "Me preocupa el #desempleo y la #inflacion")
    cercana = comunidad(pg, amiga, "Mi círculo")
    publicar_en(pg, amiga, cercana, "Hablemos de #desempleo")
    otra = comunidad(pg, lejana1, "Otro círculo")
    entrar(pg, lejana2, otra)
    publicar_en(pg, lejana1, otra, "Datos de #desempleo")
    secreta = comunidad(pg, lejana2, "Secreta", "privada")
    publicar_en(pg, lejana2, secreta, "Aquí también #desempleo e #inflacion")
    sinc.procesar_pendientes()
    sugeridas = consultas.comunidades_recomendadas(neo4j, yo)
    assert [s["comunidad_id"] for s in sugeridas] == [otra, cercana]   # misma afinidad: gana la de fuera de mi red
    assert sugeridas[0]["fuera_de_mi_red"] == 1.0 and sugeridas[1]["fuera_de_mi_red"] == 0.0
    assert secreta not in [s["comunidad_id"] for s in sugeridas]       # las privadas no se sugieren por su contenido
    entrar(pg, yo, otra)
    sinc.procesar_pendientes()
    assert otra not in [s["comunidad_id"] for s in consultas.comunidades_recomendadas(neo4j, yo)]
    # Relacionadas: mismo tema, y primero la que comparte menos integrantes.
    relacionadas = consultas.comunidades_relacionadas(neo4j, cercana)
    assert [r["comunidad_id"] for r in relacionadas] == [otra] and relacionadas[0]["temas"] == ["desempleo"]
    assert consultas.comunidades_relacionadas(neo4j, secreta) == []    # de una privada no se revelan temas


def test_other_voices_are_outside_my_close_network(pg, neo4j, sinc):
    from servicios.grafo import consultas
    yo, amiga, amiga_de_amiga, lejana = (usuario(pg, n) for n in ("quien_busca", "amiga", "amiga_de_amiga", "lejana"))
    seguir(pg, yo, amiga)
    seguir(pg, amiga, amiga_de_amiga)
    publicar(pg, yo, "Opino sobre el #salario")
    for u in (amiga, amiga_de_amiga, lejana):
        publicar(pg, u, "Mi opinión sobre el #salario")
    sinc.procesar_pendientes()
    assert [p["nombre_usuario"] for p in consultas.otras_voces(neo4j, yo)] == ["lejana"]
