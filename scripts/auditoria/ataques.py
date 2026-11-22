"""Ataques desde fuera contra la pila en Docker (plan de pruebas, bloque 3). No detiene contenedores.

    uv run python scripts/auditoria/ataques.py [--base http://127.0.0.1:8080]

Cada caso imprime OK o FALLA con lo que respondió. Usa una cuenta desechable "ataque_<hora>" que desactiva al
final. Lo que publica para las pruebas de XSS queda con esa cuenta desactivada.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import socket
import sys
import time

import httpx

FALLOS = 0


def caso(codigo: str, descripcion: str, ok: bool, detalle: str = "") -> None:
    global FALLOS
    FALLOS += not ok
    print(f"{'OK   ' if ok else 'FALLA'} {codigo} {descripcion}{'' if ok else ' → ' + detalle[:220]}")


def puerto_abierto(puerto: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    base, api = args.base, f"{args.base}/api"
    h = httpx.Client(timeout=30, headers={"X-Parrhesia": "1"})
    anon = httpx.Client(timeout=30)

    # MS-01 · Servicios por fuera del gateway --------------------------------------------------------------
    for puerto in (8000, 8001, 8002, 8003, 8004, 8005, 8006):
        caso("MS-01", f"puerto {puerto} del equipo cerrado (servicios solo en la red interna)", not puerto_abierto(puerto))
    for puerto, que in ((5433, "PostgreSQL"), (7474, "Neo4j"), (8080, "app")):
        caso("MS-01", f"{que} solo en 127.0.0.1:{puerto} (informativo: publicado a propósito)", puerto_abierto(puerto))

    # MS-02 · Rutas internas y documentación -------------------------------------------------------------------
    for ruta in ("/api/grafo/v1/tendencias/calcular", "/api/grafo/salud", "/api/ia/v1/trabajos", "/api/../etc/passwd",
                 "/api/social/../../etc/passwd", "/api/social/%2e%2e/%2e%2e/etc/passwd"):
        r = anon.get(base + ruta)
        # Una ruta desconocida fuera de /api devuelve la página de la app (así funciona el enrutado del navegador);
        # lo que importa es que nunca salga un archivo del sistema ni algo de un servicio interno.
        caso("MS-02", f"ruta interna {ruta} no alcanzable", "root:" not in r.text and (r.status_code in (400, 404) or "<!doctype html>" in r.text.lower()),
             f"{r.status_code} {r.text}")
    for servicio in ("social", "verificacion", "temas", "oficial"):
        for doc in ("docs", "openapi.json", "redoc"):
            r = anon.get(f"{api}/{servicio}/{doc}")
            caso("MS-02", f"documentación automática /{servicio}/{doc} cerrada", r.status_code == 404, f"{r.status_code}")

    # Cuenta desechable para lo que exige sesión.
    nombre, clave = f"ataque_{time.strftime('%H%M%S')}", "Clave-de-ataque-2026"
    h.post(f"{api}/social/v1/cuentas", json={"nombre_usuario": nombre, "nombre_visible": "Ataque",
                                              "correo": f"{nombre}@auditoria.local", "clave": clave})
    r = h.post(f"{api}/social/v1/sesiones", json={"correo": f"{nombre}@auditoria.local", "clave": clave})
    token = r.cookies.get("parrhesia_sesion")
    caso("MS-04", "sesión de la cuenta de ataque", bool(token), r.text)

    # MS-03 · CSRF: escrituras sin el encabezado de la app o desde otro origen ---------------------------------
    sin_enc = httpx.post(f"{api}/social/v1/publicaciones", json={"texto": "csrf"}, cookies={"parrhesia_sesion": token})
    caso("MS-03", "escritura con la cookie pero sin X-Parrhesia, rechazada", sin_enc.status_code in (401, 403), f"{sin_enc.status_code} {sin_enc.text}")
    otro = httpx.post(f"{api}/social/v1/publicaciones", json={"texto": "csrf"}, cookies={"parrhesia_sesion": token},
                      headers={"X-Parrhesia": "1", "Origin": "https://atacante.example"})
    caso("MS-03", "escritura desde otro origen, rechazada", otro.status_code in (401, 403), f"{otro.status_code} {otro.text}")
    form = httpx.post(f"{api}/social/v1/publicaciones", data={"texto": "csrf"}, cookies={"parrhesia_sesion": token})
    caso("MS-03", "formulario HTML simple (sin JSON ni encabezado), rechazado", form.status_code in (401, 403, 415, 422), f"{form.status_code}")

    # MS-04 · Tokens falsificados ------------------------------------------------------------------------------
    cabecera, carga, firma = token.split(".")
    datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    falsos = {
        "firma alterada": f"{cabecera}.{carga}.{firma[::-1]}",
        "alg none": base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode() + "." + carga + ".",
        "otro usuario en la carga": cabecera + "." + base64.urlsafe_b64encode(json.dumps({**datos, "sub": "00000000-0000-0000-0000-000000000000"}).encode()).rstrip(b"=").decode() + "." + firma,
        "basura": "abc.def.ghi",
    }
    for que, t in falsos.items():
        r = httpx.get(f"{api}/social/v1/yo", headers={"Authorization": f"Bearer {t}"})
        caso("MS-04", f"token con {que}, rechazado", r.status_code == 401, f"{r.status_code} {r.text}")

    # MS-06 · Inyección SQL ------------------------------------------------------------------------------------
    cargas = ["' OR '1'='1", "'; DROP TABLE social.usuario; --", "\\'; SELECT pg_sleep(5); --", "1 UNION SELECT clave_hash FROM social.usuario",
              "%' AND 1=1 --", "laura'--"]
    for c in cargas:
        inicio = time.perf_counter()
        r1 = h.get(f"{api}/social/v1/usuarios", params={"q": c})
        r2 = h.get(f"{api}/social/v1/tendencias/{c}")
        r3 = h.get(f"{api}/social/v1/usuarios/{c}")
        lento = time.perf_counter() - inicio > 4
        fuga = any("argon2" in r.text or "$2b$" in r.text for r in (r1, r2, r3))
        caido = any(r.status_code >= 500 for r in (r1, r2, r3))
        caso("MS-06", f"inyección {c!r} sin efecto", not (lento or fuga or caido), f"{r1.status_code}/{r2.status_code}/{r3.status_code}")
    caso("MS-06", "la tabla de cuentas sigue ahí", h.get(f"{api}/social/v1/usuarios/laura_castano").status_code == 200)
    r = h.get(f"{api}/social/v1/publicaciones/no-es-un-uuid")
    caso("MS-06", "id que no es uuid: error de validación, no del servidor", r.status_code in (404, 422), f"{r.status_code}")

    # MS-08 · SSRF con Analizar enlace -------------------------------------------------------------------------
    internos = ["http://db:5432/", "http://grafo:8000/v1/difusion/x", "http://social:8000/v1/yo", "http://localhost:8080/",
                "http://127.0.0.1:5433/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://0.0.0.0:8000/",
                "file:///etc/passwd", "gopher://db:5432/", "http://2130706433/", "http://0x7f.0.0.1/", "http://neo4j:7474/"]
    for url in internos:
        r = h.post(f"{api}/verificacion/v1/enlaces", json={"url": url})
        caso("MS-08", f"SSRF {url} rechazado", r.status_code in (400, 422, 429), f"{r.status_code} {r.text}")

    # MS-09 · Archivos -----------------------------------------------------------------------------------------
    def subir(nombre_archivo, contenido, tipo):
        return h.put(f"{api}/social/v1/yo/foto", files={"foto": (nombre_archivo, contenido, tipo)})
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for que, (n, c, t) in {"texto disfrazado de imagen": ("foto.png", b"esto no es una imagen", "image/png"),
                           "SVG con script": ("foto.svg", svg, "image/svg+xml"),
                           "ejecutable": ("foto.jpg", b"MZ\x90\x00" + b"\x00" * 200, "image/jpeg"),
                           "imagen de 4 MB": ("grande.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (4 * 1024 * 1024), "image/png")}.items():
        r = subir(n, c, t)
        caso("MS-09", f"foto: {que}, rechazada", r.status_code in (400, 413, 415, 422), f"{r.status_code} {r.text[:120]}")
    try:
        from PIL import Image
        buf = io.BytesIO()
        img = Image.new("RGB", (40, 40), (120, 90, 60))
        exif = Image.Exif()
        exif[0x010F] = "FabricanteSecreto"                    # Make
        exif[0x010E] = "Casa de Ana, calle 10"                 # ImageDescription (dato personal)
        img.save(buf, "JPEG", exif=exif)
        r = subir("con_gps.jpg", buf.getvalue(), "image/jpeg")
        ok = r.status_code in (200, 201, 204)
        foto = h.get(f"{api}/social/v1/yo").json().get("foto") if ok else None
        limpia = False
        if foto:
            contenido = httpx.get(foto if foto.startswith("http") else base + foto).content
            limpia = b"FabricanteSecreto" not in contenido and b"Casa de Ana" not in contenido
        caso("MS-09", "foto con metadatos personales: se acepta y se guarda sin ellos", ok and limpia, f"{r.status_code} foto={foto}")
    except ImportError:
        caso("MS-09", "foto con metadatos (Pillow no disponible para la prueba)", True)

    # MS-10 · Cargas extremas ----------------------------------------------------------------------------------
    for que, cuerpo in {"10 000 caracteres": {"texto": "a" * 10000}, "501 caracteres": {"texto": "b" * 501},
                        "JSON con campos de más": {"texto": "hola", "autor_id": "00000000-0000-0000-0000-000000000000", "rol": "admin"},
                        "texto vacío": {"texto": "   "}, "tipo equivocado": {"texto": 12345}}.items():
        r = h.post(f"{api}/social/v1/publicaciones", json=cuerpo)
        if que == "JSON con campos de más":
            autor = r.json().get("autor", {}).get("nombre_usuario") if r.status_code == 201 else nombre
            caso("MS-10", "campos de más ignorados (no cambian autor ni rol)", autor == nombre, f"{r.status_code} {r.text[:120]}")
        else:
            caso("MS-10", f"publicación con {que}, rechazada con mensaje", r.status_code == 422 and "error" in r.json(), f"{r.status_code} {r.text[:120]}")
    r = h.post(f"{api}/social/v1/publicaciones", content=b"{esto no es json", headers={"Content-Type": "application/json"})
    caso("MS-10", "JSON malformado, 422", r.status_code == 422, f"{r.status_code}")
    r = h.post(f"{api}/social/v1/publicaciones", content=b"x" * (2 * 1024 * 1024), headers={"Content-Type": "application/json"})
    caso("MS-10", "cuerpo de 2 MB, cortado por el gateway", r.status_code == 413, f"{r.status_code}")
    rara = h.post(f"{api}/social/v1/publicaciones", json={"texto": "Prueba con emojis 🇨🇴🔥 y RTL مرحبا y nulos ​"})
    caso("MS-10", "emojis, texto de derecha a izquierda y caracteres invisibles", rara.status_code in (201, 422), f"{rara.status_code}")

    # MS-07 · XSS: se publica y se revisa cómo lo devuelve la API (el navegador se revisa aparte) ---------------
    xss = h.post(f"{api}/social/v1/publicaciones",
                 json={"texto": 'XSS <script>alert(1)</script> <img src=x onerror=alert(2)> [clic](javascript:alert(3))'})
    caso("MS-07", "publicación con HTML y enlace javascript: se guarda como texto", xss.status_code == 201, f"{xss.status_code}")
    print(f"   (id para revisar en el navegador: {xss.json().get('id') if xss.status_code == 201 else '-'})")

    # MS-16 · Encabezados y cookie -----------------------------------------------------------------------------
    r = anon.get(base + "/")
    for enc in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy"):
        caso("MS-16", f"encabezado {enc} en la app", enc in r.headers, "falta")
    r = anon.get(f"{api}/social/v1/tendencias")
    for enc in ("x-content-type-options",):
        caso("MS-16", f"encabezado {enc} en la API", enc in r.headers, "falta")
    caso("MS-16", "el servidor no dice su versión", "nginx/" not in r.headers.get("server", ""), r.headers.get("server", ""))
    galleta = h.post(f"{api}/social/v1/sesiones", json={"correo": f"{nombre}@auditoria.local", "clave": clave}).headers.get("set-cookie", "")
    caso("MS-16", "cookie de sesión HttpOnly y SameSite", "httponly" in galleta.lower() and "samesite" in galleta.lower(), galleta[:160])

    h.post(f"{api}/social/v1/yo/desactivacion", json={"clave_actual": clave})
    print(f"\nCasos fallidos: {FALLOS}")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
