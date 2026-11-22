"""Variables de configuración: primero del entorno (Docker), si no, del archivo .env.

Los valores nunca se imprimen ni se registran: pueden ser contraseñas.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parents[3]
ARCHIVO_ENV = RAIZ / ".env"


def variable(nombre: str, por_defecto: str | None = None) -> str | None:
    if os.environ.get(nombre):
        return os.environ[nombre]
    if ARCHIVO_ENV.exists():
        for linea in ARCHIVO_ENV.read_text(encoding="utf-8").splitlines():
            if linea.startswith(f"{nombre}="):
                return linea.split("=", 1)[1].strip() or por_defecto
    return por_defecto


def obligatoria(nombre: str) -> str:
    valor = variable(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable {nombre} (ver .env.example)")
    return valor


def conectar_postgres(variable_url: str = "DATABASE_URL") -> psycopg.Connection:
    """Conexión en autocommit: cada unidad de trabajo abre su propia transacción.

    Cada servicio usará su propio rol (decisión 13) con su variable, por ejemplo
    PG_URL_GRAFO; mientras no exista, se usa DATABASE_URL.
    """
    url = variable(variable_url) or obligatoria("DATABASE_URL")
    return psycopg.connect(url, autocommit=True)


def crear_pool(variable_url: str = "DATABASE_URL", minimo: int = 1, maximo: int = 10):
    """Pool de conexiones en autocommit: cada petición toma una y la devuelve al terminar.

    Cada petición es una sola llamada a un procedimiento (o una lectura), así que
    cada petición es una transacción: si el procedimiento falla, no queda nada.
    """
    from psycopg_pool import ConnectionPool

    url = variable(variable_url) or obligatoria("DATABASE_URL")
    return ConnectionPool(url, min_size=minimo, max_size=maximo, kwargs={"autocommit": True}, open=True)
