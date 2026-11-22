from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import uuid

import httpx
import psycopg
import pytest
from psycopg import sql

from app.catalog import Approval, Ficha, load_ficha_by_code
from app.db import database_url
from app.db.migrate import migrate
from app.connectors.suameca import SuamecaConnector
from app.storage.observations import InMemoryObservationStore
from app.storage.raw import FilesystemRawStore

FIXTURES = Path(__file__).parent / "fixtures" / "suameca"
SUAMECA_CODES = ("inflation_annual_national", "unemployment_rate_national", "minimum_wage_monthly")


def fixture_document(menu_id: int) -> dict:
    """A saved SUAMECA response (downloaded 25 Oct 2026), decoded for editing in tests."""
    return json.loads((FIXTURES / f"menu_{menu_id}.json").read_bytes(), parse_float=Decimal)


def encode(document: dict) -> bytes:
    return json.dumps(document, default=lambda d: float(d) if isinstance(d, Decimal) else d).encode()


class FakeSuameca:
    """Serves saved responses by menu id; tests can replace the body of a menu."""

    def __init__(self) -> None:
        self.bodies: dict[str, bytes] = {}

    def set(self, menu_id: int, body: bytes | dict) -> None:
        self.bodies[str(menu_id)] = body if isinstance(body, bytes) else encode(body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        menu_id = request.url.params["idMenu"]
        body = self.bodies.get(menu_id)
        if body is None:
            body = (FIXTURES / f"menu_{menu_id}.json").read_bytes()
        return httpx.Response(200, content=body)


@pytest.fixture
def fake_suameca() -> FakeSuameca:
    return FakeSuameca()


@pytest.fixture
def connector(fake_suameca: FakeSuameca) -> SuamecaConnector:
    return SuamecaConnector(httpx.Client(transport=httpx.MockTransport(fake_suameca.handler)))


@pytest.fixture
def raw_store(tmp_path: Path) -> FilesystemRawStore:
    return FilesystemRawStore(tmp_path / "raw")


@pytest.fixture
def store() -> InMemoryObservationStore:
    return InMemoryObservationStore()


@pytest.fixture
def ficha() -> Callable[[str], Ficha]:
    return load_ficha_by_code


def approved(ficha: Ficha, content_sha256: str | None = None) -> Ficha:
    """A copy approved for its current content (or for the given hash)."""
    approval = Approval(status="approved", approved_by="test", content_sha256=content_sha256 or ficha.content_sha256)
    return ficha.model_copy(update={"approval": approval})


def target_series(document: dict, series_id: int) -> dict:
    return next(s for s in document["SERIES"] if s["id"] == series_id)


# PostgreSQL: one temporary database per test session (never the development one),
# with every migration applied. Skipped when DATABASE_URL is not set or the server is down.


def _server_url():
    url = database_url()
    if not url:
        pytest.skip("DATABASE_URL is not set")
    try:
        with psycopg.connect(url, connect_timeout=3):
            pass
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL is not reachable at DATABASE_URL")
    return url


@pytest.fixture(scope="session")
def test_db_url():
    url = _server_url()
    name = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    test_url = psycopg.conninfo.make_conninfo(url, dbname=name)
    try:
        with psycopg.connect(test_url, autocommit=True) as conn:
            migrate(conn)
        yield test_url
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
