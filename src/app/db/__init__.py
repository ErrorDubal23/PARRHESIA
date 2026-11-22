"""PostgreSQL: connection settings, migrations, catalog sync and the observation store."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


def database_url(env_file: Path = ENV_FILE) -> str | None:
    """DATABASE_URL from the environment, or from .env (never logged or printed)."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip() or None
    return None


def connect(url: str | None = None, *, autocommit: bool = True) -> psycopg.Connection:
    """Autocommit by default: every unit of work opens its own `conn.transaction()`."""
    url = url or database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return psycopg.connect(url, autocommit=autocommit)
