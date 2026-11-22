"""Asignar un rol desde la consola del dueño de la base (migración 0035).

    uv run python db/consola/asignar_rol.py --usuario dubal_aguilar --rol admin --motivo "Primer administrador del proyecto."

Sirve para el primer administrador (cuando todavía no hay nadie que pueda asignarlo desde la app) y para
recuperar el acceso si hiciera falta. Usa social.asignar_rol_consola, que ningún servicio puede ejecutar: solo
quien tiene la conexión del dueño de la base. El cambio queda en la bitácora pública sin actor ("desde la
consola"). Desde la app, un administrador usa la página Equipo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.db import connect  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usuario", required=True, help="nombre de usuario, sin @")
    parser.add_argument("--rol", required=True, choices=["usuario", "verificador", "admin"])
    parser.add_argument("--motivo", required=True, help="queda en la bitácora pública (al menos 10 caracteres)")
    args = parser.parse_args()
    conn = connect(autocommit=True)
    fila = conn.execute("SELECT id, rol FROM social.usuario WHERE nombre_usuario = %s AND estado = 'activo'",
                        (args.usuario.lstrip("@"),)).fetchone()
    if fila is None:
        raise SystemExit(f"No hay una cuenta activa @{args.usuario.lstrip('@')}")
    conn.execute("CALL social.asignar_rol_consola(%s, %s, %s)", (fila[0], args.rol, args.motivo))
    print(f"@{args.usuario.lstrip('@')}: {fila[1]} → {args.rol} (queda en la bitácora)")


if __name__ == "__main__":
    main()
