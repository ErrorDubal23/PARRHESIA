"""Crea el .env a partir de .env.example con contraseñas al azar (para arrancar en un equipo nuevo).

    uv run python scripts/preparar_env.py

- Nunca sobrescribe un .env que ya existe.
- Llena con valores al azar solo los secretos locales vacíos (base, Neo4j, firma de sesiones, roles de cada
  servicio) y arma DATABASE_URL con esa contraseña. Las llaves de proveedores externos (IA, Unsplash, Socrata,
  Fact Check) quedan vacías: cada quien pone las suyas; sin ellas la app funciona, sin esas funciones.
- Nunca imprime un valor: solo los nombres de lo que llenó.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SECRETOS = ("POSTGRES_PASSWORD", "NEO4J_PASSWORD", "JWT_SECRETO", "PG_CLAVE_OFICIAL", "PG_CLAVE_SOCIAL",
            "PG_CLAVE_VERIFICACION", "PG_CLAVE_IA", "PG_CLAVE_TEMAS", "PG_CLAVE_GRAFO")


def main() -> int:
    destino, ejemplo = RAIZ / ".env", RAIZ / ".env.example"
    if destino.exists():
        print(".env ya existe: no se cambia nada.")
        return 0
    valores: dict[str, str] = {}
    lineas = []
    for linea in ejemplo.read_text(encoding="utf-8").splitlines():
        nombre, igual, valor = linea.partition("=")
        if igual and not linea.lstrip().startswith("#"):
            nombre = nombre.strip()
            if nombre in SECRETOS and not valor.strip():
                valor = secrets.token_hex(24)          # solo hexadecimal: no hay que escaparlo en una URL
            valores[nombre] = valor
            linea = f"{nombre}={valor}"
        lineas.append(linea)
    puerto = valores.get("POSTGRES_PORT") or "5433"
    lineas = [f"DATABASE_URL=postgresql://app:{valores['POSTGRES_PASSWORD']}@127.0.0.1:{puerto}/proyecto_social"
              if l.startswith("DATABASE_URL=") and not l.partition("=")[2] else l for l in lineas]
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    destino.chmod(0o600)
    print("Se creó .env con valores al azar para: " + ", ".join(n for n in SECRETOS) + ", DATABASE_URL.")
    print("Las llaves de proveedores externos quedan vacías (ver los comentarios en .env).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
