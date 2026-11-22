"""Caídas en plena demo (plan de pruebas MS-11, MS-12, MS-14, MS-15). DETIENE CONTENEDORES: hacer un respaldo antes.

    uv run python scripts/auditoria/caidas.py [--solo grafo,neo4j,ia,social,db,reinicio,reconstruir]

Para cada caída: detiene el contenedor, comprueba lo que ve la persona (por el gateway, como la página), lo
vuelve a encender y comprueba que se recupere solo, sin reiniciar nada más y sin perder datos. Nunca usa
"down -v". Imprime OK o FALLA por paso y sale con 1 si algo falla.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8080/api"
FALLOS = 0
CORREO, CLAVE = "laura_castano@demo.parrhesia.local", "iAvYzWWLoEeemD-a"


def caso(codigo, descripcion, ok, detalle=""):
    global FALLOS
    FALLOS += not ok
    print(f"{'OK   ' if ok else 'FALLA'} {codigo} {descripcion}{'' if ok else ' → ' + str(detalle)[:220]}", flush=True)


def compose(*args, timeout=180):
    return subprocess.run(["docker", "compose", *args], cwd=RAIZ, capture_output=True, text=True, timeout=timeout)


def sql(consulta):
    r = compose("exec", "-T", "db", "sh", "-c", f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "{consulta}"')
    return r.stdout.strip()


def esperar(condicion, segundos=90, cada=2):
    fin = time.time() + segundos
    while time.time() < fin:
        try:
            if condicion():
                return True
        except Exception:
            pass
        time.sleep(cada)
    return False


def sesion():
    h = httpx.Client(timeout=15, headers={"X-Parrhesia": "1"})
    h.post(f"{API}/social/v1/sesiones", json={"correo": CORREO, "clave": CLAVE})
    return h


def publicar(h, texto):
    r = h.post(f"{API}/social/v1/publicaciones", json={"texto": texto})
    return r.json()["id"] if r.status_code == 201 else None


def conteos_neo4j():
    r = compose("exec", "-T", "neo4j", "sh", "-c",
                'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" --format plain '
                '"MATCH (n) WITH count(n) AS nodos MATCH ()-[r]->() RETURN nodos, count(r) AS relaciones"')
    filas = [l for l in r.stdout.splitlines() if l and l[0].isdigit()]
    return filas[0] if filas else f"error: {r.stderr.strip()[:120]}"


def caida_grafo():
    compose("stop", "grafo")
    h = sesion()
    caso("MS-11", "sin grafo: el feed sigue (respaldo de PostgreSQL)", h.get(f"{API}/social/v1/feed").status_code == 200)
    s = h.get(f"{API}/social/v1/sugerencias")
    caso("MS-11", "sin grafo: 'A quién seguir' avisa en vez de fallar", s.status_code == 200 and "aviso" in s.json(), s.text)
    pid = publicar(h, "Prueba de caída: publico con el grafo apagado.")
    caso("MS-11", "sin grafo: se puede publicar", pid is not None)
    compose("start", "grafo")
    caso("MS-11", "grafo de vuelta y saludable", esperar(lambda: "healthy" in compose("ps", "grafo", "--format", "{{.Status}}").stdout, 120))
    pendientes = lambda: sql("SELECT count(*) FROM social.evento_salida e WHERE NOT EXISTS (SELECT 1 FROM social.entrega_evento d "
                             "WHERE d.evento_id = e.id AND d.consumidor = 'grafo') AND e.tipo_evento <> 'declaracion_creada'") == "0"
    caso("MS-11", "el grafo se pone al día con lo publicado mientras estuvo apagado (outbox)", esperar(pendientes, 120))


def caida_neo4j():
    compose("stop", "neo4j")
    h = sesion()
    caso("MS-11", "sin Neo4j: el feed sigue", h.get(f"{API}/social/v1/feed").status_code == 200)
    pid = publicar(h, "Prueba de caída: publico con Neo4j apagado.")
    caso("MS-11", "sin Neo4j: se puede publicar", pid is not None)
    compose("start", "neo4j")
    caso("MS-11", "Neo4j de vuelta y saludable", esperar(lambda: "healthy" in compose("ps", "neo4j", "--format", "{{.Status}}").stdout, 180))
    entregado = lambda: sql(f"SELECT count(*) FROM social.entrega_evento d JOIN social.evento_salida e ON e.id = d.evento_id "
                            f"WHERE d.consumidor = 'grafo' AND e.entidad_id = '{pid}'") != "0"
    caso("MS-11", "lo publicado sin Neo4j llega al grafo cuando vuelve (sin reiniciar el trabajador)", esperar(entregado, 180), pid)


def caida_ia():
    compose("stop", "ia-trabajador")
    h = sesion()
    pid = publicar(h, "Prueba de caída: la inflación anual de septiembre de 2026 fue de 6,29 %.")
    time.sleep(8)
    estado = h.get(f"{API}/verificacion/v1/textos/publicacion/{pid}").json().get("estado")
    caso("MS-14", "sin IA: la publicación sale y su verificación queda pendiente (nunca inventa)", estado == "pendiente", estado)
    compose("start", "ia-trabajador")
    listo = lambda: h.get(f"{API}/verificacion/v1/textos/publicacion/{pid}").json().get("estado") != "pendiente"
    caso("MS-14", "al volver la IA, la verificación se completa sola", esperar(listo, 240, 5),
         h.get(f"{API}/verificacion/v1/textos/publicacion/{pid}").json().get("estado"))


def caida_social():
    compose("stop", "social")
    r = httpx.get(f"{API}/social/v1/feed", timeout=15)
    caso("MS-11", "sin el servicio social: la API responde 503 con mensaje claro", r.status_code == 503 and "servicio_no_disponible" in r.text, f"{r.status_code} {r.text}")
    caso("MS-11", "sin el servicio social: los temas del día siguen", httpx.get(f"{API}/temas/v1/temas", timeout=15).status_code == 200)
    caso("MS-11", "sin el servicio social: la página carga", httpx.get("http://127.0.0.1:8080/", timeout=15).status_code == 200)
    compose("start", "social")
    caso("MS-11", "servicio social de vuelta sin reiniciar el gateway",
         esperar(lambda: httpx.get(f"{API}/social/v1/tendencias", timeout=5).status_code == 200, 90))


def caida_db():
    compose("stop", "db")
    r = httpx.get(f"{API}/social/v1/tendencias", timeout=20)
    caso("MS-11", "sin base: la API responde con error controlado (no se queda colgada)", r.status_code in (500, 503) and r.elapsed.total_seconds() < 15,
         f"{r.status_code} {r.elapsed.total_seconds():.1f}s {r.text[:120]}")
    caso("MS-11", "sin base: el error no muestra detalles internos", "Traceback" not in r.text and "psycopg" not in r.text, r.text[:200])
    compose("start", "db")
    esperar(lambda: "healthy" in compose("ps", "db", "--format", "{{.Status}}").stdout, 120)
    for servicio, ruta in (("social", "/social/v1/tendencias"), ("temas", "/temas/v1/temas"), ("oficial", "/oficial/v1/series"),
                           ("verificacion", "/verificacion/v1/consejos/general/leer_tema")):
        caso("MS-11", f"base de vuelta: {servicio} se recupera solo (sin reiniciarlo)",
             esperar(lambda: httpx.get(API + ruta, timeout=5).status_code == 200, 90))
    h = sesion()
    caso("MS-11", "base de vuelta: se puede publicar", publicar(h, "Prueba de caída: publico después de que volvió la base.") is not None)


def reinicio():
    antes = sql("SELECT (SELECT count(*) FROM social.publicacion)||'/'||(SELECT count(*) FROM social.usuario)||'/'||(SELECT count(*) FROM verificacion.verificacion)")
    compose("down", timeout=300)                 # sin -v: los volúmenes (datos) se conservan
    compose("up", "-d", timeout=600)
    caso("MS-12", "todo vuelve a estar saludable tras down/up",
         esperar(lambda: httpx.get(f"{API}/social/v1/tendencias", timeout=5).status_code == 200, 240, 5))
    despues = sql("SELECT (SELECT count(*) FROM social.publicacion)||'/'||(SELECT count(*) FROM social.usuario)||'/'||(SELECT count(*) FROM verificacion.verificacion)")
    caso("MS-12", f"mismos datos antes y después (publicaciones/cuentas/verificaciones {antes})", antes == despues, despues)


def reconstruir():
    antes = conteos_neo4j()
    r = compose("exec", "-T", "grafo", "python", "-c",
                "import urllib.request as u; print(u.urlopen(u.Request('http://localhost:8000/v1/reconstruir', method='POST'), timeout=600).read().decode()[:200])",
                timeout=660)
    caso("MS-15", "reconstrucción del grafo desde PostgreSQL", r.returncode == 0, r.stderr[-200:])
    despues = conteos_neo4j()
    caso("MS-15", f"el grafo reconstruido es igual (nodos y relaciones: {antes})", antes == despues, despues)


PASOS = {"grafo": caida_grafo, "neo4j": caida_neo4j, "ia": caida_ia, "social": caida_social, "db": caida_db,
         "reconstruir": reconstruir, "reinicio": reinicio}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo", default=",".join(PASOS))
    args = parser.parse_args()
    for nombre in args.solo.split(","):
        print(f"\n== {nombre}", flush=True)
        PASOS[nombre]()
    print(f"\nPasos fallidos: {FALLOS}")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
