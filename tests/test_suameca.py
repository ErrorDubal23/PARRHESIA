"""SUAMECA connector against saved responses: reference values (filter 4) and shape (filter 2)."""

import hashlib
import ssl
from decimal import Decimal

import httpx
import pytest

from app.connectors.base import ShapeError
from app.connectors.suameca import (
    INTERMEDIATE_CERT,
    INTERMEDIATE_CERT_SHA256,
    SUAMECA_HOST,
    SuamecaConnector,
    default_client,
)
from app.domain import Period
from tests.conftest import SUAMECA_CODES, fixture_document, target_series


def test_bundled_intermediate_is_the_verified_one():
    der = ssl.PEM_cert_to_DER_cert(INTERMEDIATE_CERT.read_text())
    assert hashlib.sha256(der).hexdigest() == INTERMEDIATE_CERT_SHA256


def test_intermediate_is_used_for_the_suameca_host_only():
    client = default_client()
    # httpx's own routing: which transport would serve each URL.
    suameca = client._transport_for_url(httpx.URL(f"https://{SUAMECA_HOST}/x"))
    other = client._transport_for_url(httpx.URL("https://www.datos.gov.co/x"))
    lookalike = client._transport_for_url(httpx.URL(f"https://{SUAMECA_HOST}.example.com/x"))
    assert suameca is not client._transport
    assert other is client._transport
    assert lookalike is client._transport


def test_redirects_are_not_followed(ficha):
    def redirect(request):
        return httpx.Response(302, headers={"Location": "https://example.com/"})

    connector = SuamecaConnector(httpx.Client(transport=httpx.MockTransport(redirect)))
    with pytest.raises(httpx.HTTPStatusError):
        connector.fetch(ficha("inflation_annual_national"))


@pytest.mark.parametrize("code", SUAMECA_CODES)
def test_reference_values_match(connector, ficha, code):
    f = ficha(code)
    parsed = connector.parse(connector.fetch(f), f)
    values = {v.period: v.value for v in parsed.values}
    for ref in f.reference_values:
        assert abs(values[ref.period] - ref.value) <= ref.tolerance


def test_values_keep_the_source_digits(connector, ficha):
    f = ficha("unemployment_rate_national")
    values = {v.period: v.value for v in connector.parse(connector.fetch(f), f).values}
    assert values[Period(2026, 8)] == Decimal("9.36")  # not rounded to the DANE's 9.4
    assert str(values[Period(2026, 8)]) == "9.36"


def test_monthly_and_annual_periods(connector, ficha):
    inflation = ficha("inflation_annual_national")
    periods = [v.period for v in connector.parse(connector.fetch(inflation), inflation).values]
    assert periods[0] == Period(1955, 7) and periods[-1] == Period(2026, 9)

    wage = ficha("minimum_wage_monthly")
    values = {v.period: v.value for v in connector.parse(connector.fetch(wage), wage).values}
    assert values[Period(2026)] == Decimal("1750905")


def test_daylight_saving_1992_timestamps_are_accepted(connector, ficha):
    # Colombia used UTC-4 in 1992-1993; SUAMECA stamps those months at 23:00 UTC-5.
    f = ficha("inflation_annual_national")
    periods = {v.period for v in connector.parse(connector.fetch(f), f).values}
    assert {Period(1992, 6), Period(1993, 2), Period(1993, 3)} <= periods


def test_ignored_series_is_not_read(connector, ficha):
    f = ficha("inflation_annual_national")  # menu also returns 853, the inflation target
    parsed = connector.parse(connector.fetch(f), f)
    assert len(parsed.values) == len(target_series(fixture_document(100001), 15270)["data"])


def test_source_update_date_is_kept(connector, ficha):
    f = ficha("inflation_annual_national")
    assert connector.parse(connector.fetch(f), f).source_updated == "08 de octubre de 2026"


def _break(fake_suameca, menu_id, series_id, mutate):
    doc = fixture_document(menu_id)
    mutate(doc, target_series(doc, series_id))
    fake_suameca.set(menu_id, doc)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda doc, s: s.pop("unidad"), id="missing field"),
        pytest.param(lambda doc, s: s.update(unidad="Variación porcentual mensual"), id="unit changed"),
        pytest.param(lambda doc, s: s.update(nombre="Inflación total mensual"), id="series renamed"),
        pytest.param(lambda doc, s: s.update(descripcionPeriodicidad="Trimestral"), id="frequency changed"),
        pytest.param(lambda doc, s: doc["SERIES"].append({**s, "id": 99999}), id="unexpected series"),
        pytest.param(lambda doc, s: doc["SERIES"].remove(s), id="series missing"),
        pytest.param(lambda doc, s: s["data"].append([s["data"][-1][0] + 86_400_000, 1.0]), id="not month end"),
        pytest.param(lambda doc, s: s["data"].append([s["data"][-1][0] + 3_600_000, 1.0]), id="not midnight"),
        pytest.param(lambda doc, s: s["data"].append(["2026-10-31", 1.0]), id="timestamp not int"),
        pytest.param(lambda doc, s: s["data"].append([s["data"][-1][0], "6,3"]), id="value not number"),
        pytest.param(lambda doc, s: doc.pop("SERIES"), id="no SERIES"),
    ],
)
def test_shape_changes_stop_the_download(connector, fake_suameca, ficha, mutate):
    _break(fake_suameca, 100001, 15270, mutate)
    f = ficha("inflation_annual_national")
    with pytest.raises(ShapeError):
        connector.parse(connector.fetch(f), f)


@pytest.mark.parametrize("body", [b"", b"   ", b"<html>error</html>"])
def test_empty_or_non_json_body_stops(connector, fake_suameca, ficha, body):
    fake_suameca.set(100001, body)
    f = ficha("inflation_annual_national")
    with pytest.raises(ShapeError):
        connector.parse(connector.fetch(f), f)
