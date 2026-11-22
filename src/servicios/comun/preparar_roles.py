"""Les pone a los roles de cada servicio su contraseña (desde el entorno) y les permite iniciar sesión.

    python -m servicios.comun.preparar_roles

Lo corre el contenedor de preparación, con el superusuario, después de las
migraciones. La migración 0007 crea los roles sin poder iniciar sesión: así ninguna
contraseña queda en git. Un rol sin contraseña en el entorno queda como estaba.
"""

from __future__ import annotations

import os
import sys

from psycopg import sql

from app.db import connect

ROLES = ("oficial", "social", "verificacion", "ia", "temas", "grafo")


def main() -> int:
    with connect() as conn:
        for rol in ROLES:
            clave = os.environ.get(f"PG_CLAVE_{rol.upper()}")
            if not clave:
                print(f"svc_{rol}: sin contraseña en el entorno, se deja como está")
                continue
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(f"svc_{rol}"), sql.Literal(clave)))
            print(f"svc_{rol}: listo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
