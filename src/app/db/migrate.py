"""Numbered SQL migrations (db/migrations/NNNN_name.sql), applied in order, each in its own transaction.

    uv run python -m app.db.migrate

A migration already applied must never change: its sha256 is recorded and
checked on every run.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import psycopg

from app.db import REPO_ROOT, connect

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigrationError(Exception):
    pass


def migrations(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    files = sorted(directory.glob("*.sql"))
    bad = [f.name for f in files if not _NAME.match(f.name)]
    if bad:
        raise MigrationError(f"migration files must be named NNNN_name.sql: {bad}")
    numbers = [int(_NAME.match(f.name).group(1)) for f in files]
    if numbers != list(range(1, len(files) + 1)):
        raise MigrationError(f"migrations must be numbered 0001, 0002, ... without gaps: {[f.name for f in files]}")
    return files


def pending(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Migrations not applied yet (all of them on an empty database)."""
    exists = conn.execute("SELECT to_regclass('schema_migrations') IS NOT NULL").fetchone()[0]
    applied = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")} if exists else set()
    return [p.name for p in migrations(directory) if p.name not in applied]


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; returns the names applied. Needs an autocommit connection."""
    if not conn.autocommit:
        raise MigrationError("migrate() needs an autocommit connection so each migration commits on its own")
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
    applied = dict(conn.execute("SELECT name, sha256 FROM schema_migrations").fetchall())
    done = []
    for path in migrations(directory):
        sql = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if path.name in applied:
            if applied[path.name] != digest:
                raise MigrationError(f"{path.name} changed after it was applied; write a new migration instead")
            continue
        with conn.transaction():
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (name, sha256) VALUES (%s, %s)", (path.name, digest))
        done.append(path.name)
    unknown = set(applied) - {p.name for p in migrations(directory)}
    if unknown:
        raise MigrationError(f"applied migrations missing from {directory}: {sorted(unknown)}")
    return done


def main() -> int:
    with connect() as conn:
        done = migrate(conn)
    print("applied: " + (", ".join(done) if done else "nothing (up to date)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
