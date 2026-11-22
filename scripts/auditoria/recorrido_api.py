"""Recorrido por la API de todos los servicios con una cuenta desechable (plan de pruebas, bloques 2 y 4).

    uv run python scripts/auditoria/recorrido_api.py [--base http://127.0.0.1:8080]

Crea la cuenta "auditoria_<hora>", hace las acciones principales por el gateway (igual que la página) y al final
desactiva la cuenta. Sirve para comprobar, con los roles reales de cada servicio, que nada responde 500 ni
"permission denied". Imprime una línea por paso y sale con 1 si algún paso falla.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

ENCABEZADOS = {"X-Parrhesia": "1"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    api = f"{args.base}/api"
    nombre = f"auditoria_{time.strftime('%H%M%S')}"
    clave = "Clave-de-auditoria-2026"
    fallos = 0
    http = httpx.Client(timeout=30, headers=ENCABEZADOS)

    def paso(descripcion: str, metodo: str, ruta: str, esperado: tuple[int, ...] = (200, 201), **kw):
        nonlocal fallos
        r = http.request(metodo, f"{api}{ruta}", **kw)
        ok = r.status_code in esperado
        fallos += not ok
        detalle = "" if ok else f" → {r.text[:200]}"
        print(f"{'OK ' if ok else 'FALLA'} {r.status_code} {descripcion}{detalle}")
        return r

    paso("crear cuenta", "POST", "/social/v1/cuentas",
         json={"nombre_usuario": nombre, "nombre_visible": "Auditoría", "correo": f"{nombre}@auditoria.local", "clave": clave})
    paso("iniciar sesión", "POST", "/social/v1/sesiones", json={"correo": f"{nombre}@auditoria.local", "clave": clave})
    paso("yo", "GET", "/social/v1/yo")
    paso("feed", "GET", "/social/v1/feed")
    op = paso("publicar opinión", "POST", "/social/v1/publicaciones", json={"texto": "Prueba de auditoría: una opinión sin cifras."}).json()
    cifra = paso("publicar cifra", "POST", "/social/v1/publicaciones",
                 json={"texto": "Prueba de auditoría: la inflación anual de octubre de 2026 fue de 6,30 %."}).json()
    paso("reaccionar", "PUT", f"/social/v1/publicaciones/{op['id']}/reacciones/yo", json={"tipo": "util"})
    paso("quitar reacción", "DELETE", f"/social/v1/publicaciones/{op['id']}/reacciones/yo", esperado=(200, 204))
    paso("responder", "POST", "/social/v1/publicaciones", json={"texto": "Respuesta de auditoría.", "responde_a_id": op["id"]})
    paso("hilo", "GET", f"/social/v1/publicaciones/{op['id']}/hilo")
    paso("tendencias", "GET", "/social/v1/tendencias")
    paso("comunidades", "GET", "/social/v1/comunidades")
    paso("figuras", "GET", "/social/v1/figuras")
    figuras = http.get(f"{api}/social/v1/figuras").json()["figuras"]
    if figuras:
        paso("ficha de figura", "GET", f"/social/v1/figuras/{figuras[0]['id']}")
    paso("equipo", "GET", "/social/v1/equipo")
    paso("buscar personas", "GET", "/social/v1/usuarios", params={"q": "laura"})
    paso("perfil propio", "GET", f"/social/v1/usuarios/{nombre}")
    paso("seguir a laura_castano", "PUT", "/social/v1/usuarios/laura_castano/seguidores/yo", esperado=(204,))
    paso("dejar de seguir", "DELETE", "/social/v1/usuarios/laura_castano/seguidores/yo", esperado=(204,))
    paso("asignar rol sin ser admin (debe negar)", "POST", "/social/v1/equipo/roles",
         json={"nombre_usuario": nombre, "rol": "admin", "motivo": "Intento de auditoría sin permiso."}, esperado=(403,))
    paso("temas del día", "GET", "/temas/v1/temas")
    temas = http.get(f"{api}/temas/v1/temas").json()["temas"]
    if temas:
        paso("página de un tema", "GET", f"/temas/v1/temas/{temas[0]['id']}")
    paso("series oficiales", "GET", "/oficial/v1/series")
    paso("estado de verificación de la cifra", "GET", f"/verificacion/v1/textos/publicacion/{cifra['id']}")
    paso("revisiones pendientes sin ser verificador (debe negar)", "GET", "/verificacion/v1/revisiones/pendientes", esperado=(403,))
    paso("consejo general", "GET", "/verificacion/v1/consejos/general/leer_tema")
    an = paso("analizar texto", "POST", "/verificacion/v1/enlaces",
              json={"texto": "Circula en redes que el desempleo de septiembre de 2026 fue de 8 % en Colombia."}, esperado=(201,))
    if an.status_code == 201:
        paso("ver análisis", "GET", f"/verificacion/v1/enlaces/{an.json()['id']}")
    paso("desactivar cuenta de auditoría", "POST", "/social/v1/yo/desactivacion", json={"clave_actual": clave}, esperado=(204,))
    paso("la sesión ya no vale tras desactivar", "GET", "/social/v1/yo", esperado=(401, 403))
    print(f"\nPasos fallidos: {fallos}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
