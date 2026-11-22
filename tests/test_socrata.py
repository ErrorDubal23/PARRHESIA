"""datos.gov.co connector on synthetic metadata and CSV with the real dataset layout."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.connectors.base import ShapeError
from app.connectors.socrata import SocrataConnector
from app.domain import Period
from app.health import socrata_freshness
from app.storage.observations import InMemoryObservationStore

COLUMNS = [
    ("fecha_hecho", "calendar_date", "FECHA HECHO"),
    ("cod_depto", "text", "COD_DEPTO"),
    ("departamento", "text", "DEPARTAMENTO"),
    ("cod_muni", "text", "COD_MUNI"),
    ("municipio", "text", "MUNICIPIO"),
    ("zona", "text", "ZONA"),
    ("sexo", "text", "SEXO"),
    ("arma_medio", "text", "ARMA MEDIO"),
    ("_modalidad_presunta", "text", " MODALIDAD PRESUNTA"),
    ("spoa_caracterizacion", "text", "SPOA_CARACTERIZACION"),
    ("cantidad", "number", "CANTIDAD"),
]
UPDATED = datetime(2026, 10, 21, 14, 30, 57, tzinfo=UTC)
HEADER = ",".join(name for _, _, name in COLUMNS)


def metadata(columns=COLUMNS, updated=UPDATED) -> bytes:
    return json.dumps(
        {
            "rowsUpdatedAt": int(updated.timestamp()),
            "columns": [{"fieldName": f, "dataTypeName": t, "name": n} for f, t, n in columns],
        }
    ).encode()


def row(day="30/09/2026", category="HOMICIDIO INTENCIONAL O CON DOLO", quantity="1") -> str:
    return f"{day},27,CHOCO,27006,ACANDI,RURAL,MASCULINO,ARMA DE FUEGO,SICARIATO,{category},{quantity}"


def csv_body(*rows: str, header: str = HEADER) -> bytes:
    return ("﻿" + "\n".join([header, *rows]) + "\n").encode()


class FakeDatosGov:
    def __init__(self, meta: bytes, rows: bytes) -> None:
        self.meta, self.rows, self.requests = meta, rows, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("rows.csv"):
            return httpx.Response(200, content=self.rows)
        return httpx.Response(200, content=self.meta)


def _connector(fake, token=""):
    return SocrataConnector(httpx.Client(transport=httpx.MockTransport(fake.handler)), token=token)


def _parse(ficha, meta, rows):
    fake = FakeDatosGov(meta, rows)
    connector = _connector(fake)
    f = ficha("homicides_intentional_national")
    return connector.parse(connector.fetch(f), f)


def test_aggregates_included_categories_by_month(ficha):
    parsed = _parse(
        ficha,
        metadata(),
        csv_body(
            row("30/09/2026", quantity="2"),
            row("01/09/2026", category="FEMINICIDIO"),
            row("31/08/2026", quantity="38"),
        ),
    )
    assert {v.period: v.value for v in parsed.values} == {Period(2026, 8): Decimal(38), Period(2026, 9): Decimal(3)}
    assert parsed.source_updated == UPDATED.isoformat()


def test_two_original_files_are_fetched(ficha):
    fake = FakeDatosGov(metadata(), csv_body(row()))
    raws = _connector(fake).fetch(ficha("homicides_intentional_national"))
    assert [r.name for r in raws] == ["metadata", "rows"]
    assert raws[1].url.endswith("/api/views/m8fd-ahd9/rows.csv?accessType=DOWNLOAD")


def test_token_is_sent_only_when_configured(ficha):
    fake = FakeDatosGov(metadata(), csv_body(row()))
    _connector(fake, token="abc").fetch(ficha("homicides_intentional_national"))
    assert all(r.headers["X-App-Token"] == "abc" for r in fake.requests)
    fake.requests.clear()
    _connector(fake, token="").fetch(ficha("homicides_intentional_national"))
    assert all("X-App-Token" not in r.headers for r in fake.requests)


@pytest.mark.parametrize(
    ("meta", "rows"),
    [
        pytest.param(metadata(COLUMNS[:-1]), csv_body(row()), id="column removed"),
        pytest.param(metadata([*COLUMNS[:-1], ("cantidad", "text", "CANTIDAD")]), csv_body(row()), id="type changed"),
        pytest.param(metadata(list(reversed(COLUMNS))), csv_body(row()), id="order changed"),
        pytest.param(metadata(), csv_body(row(), header=HEADER.replace("FECHA HECHO", "FECHA")), id="csv header"),
        pytest.param(metadata(), csv_body(row(category="HOMICIDIO CULPOSO")), id="new category"),
        pytest.param(metadata(), csv_body(row(quantity="0")), id="zero quantity"),
        pytest.param(metadata(), csv_body(row(quantity="1.5")), id="fractional quantity"),
        pytest.param(metadata(), csv_body(row(day="2026-09-30")), id="date format"),
        pytest.param(metadata(), csv_body(row() + ",extra"), id="extra field"),
        pytest.param(b"{}", csv_body(row()), id="metadata shape"),
    ],
)
def test_shape_changes_stop_the_download(ficha, meta, rows):
    with pytest.raises(ShapeError):
        _parse(ficha, meta, rows)


# Health: metadata only; full download when rowsUpdatedAt changes; alert after 45 days


def test_freshness_changed_when_nothing_stored(ficha):
    fake = FakeDatosGov(metadata(), b"never requested")
    result = socrata_freshness(ficha("homicides_intentional_national"), _connector(fake), InMemoryObservationStore(), UPDATED)
    assert result.changed and not result.stale
    assert [r.url.path for r in fake.requests] == ["/api/views/m8fd-ahd9.json"]  # no CSV download


@pytest.mark.parametrize(("days", "stale"), [(45, False), (46, True)])
def test_stale_alert_after_45_days(ficha, days, stale):
    fake = FakeDatosGov(metadata(), b"")
    now = UPDATED + timedelta(days=days, seconds=1)
    result = socrata_freshness(ficha("homicides_intentional_national"), _connector(fake), InMemoryObservationStore(), now)
    assert result.stale is stale
