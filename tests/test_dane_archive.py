"""DANE archive (discovery, monthly re-check with If-Modified-Since), connector values and the filter 5 rules."""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from app import contrasts
from app.catalog import load_ficha_by_code
from app.connectors import dane
from app.connectors.dane_archive import DaneArchive, DaneConnector, DanePublications, load_dane_config, series_values
from app.domain import ContrastStatus, Flag, ObservationStatus, ParsedValue, Period
from app.evidence import EvidenceManifest
from app.pipeline import ingest
from app.storage.observations import InMemoryObservationStore
from tests import dane_files as files
from tests.conftest import approved, fixture_document, target_series

IPC_PAGE = "https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc"
OCT_26 = datetime(2026, 10, 26, 12, tzinfo=UTC)

BULLETINS = {
    "/files/operaciones/IPC/sep2026/bol-IPC-sep2026.pdf": files.BULLETIN_SEP_2026,
    "/files/operaciones/IPC/ago2026/bol-IPC-ago2026.pdf": files.FIXTURES / "bol-IPC-ago2026.pdf",
    "/files/operaciones/IPC/ago2024/bol-IPC-ago2024.pdf": files.BULLETIN_AUG_2024,
    "/files/operaciones/IPC/ene2024/bol-IPC-ene2024.pdf": files.BULLETIN_JAN_2024,
}
OLD_BULLETIN = "/files/investigaciones/boletines/ipc/bol_ipc_dic22.pdf"  # before 2023: not downloaded


def _geih_values():
    """GEIH values equal to the SUAMECA fixture (2 decimals), so the contrast passes."""
    series = target_series(fixture_document(500021), 15312)
    out = {}
    for t, v in series["data"]:
        d = datetime.fromtimestamp(t / 1000 - 5 * 3600, UTC)
        out[(d.year, d.month)] = str(v)
    return out


class FakeDane:
    def __init__(self, geih: bytes) -> None:
        self.files = {"/files/operaciones/IPC/sep2026/anex-IPC-Variacion-sep2026.xls": files.VARIATIONS_SEP_2026.read_bytes()}
        self.files.update({path: p.read_bytes() for path, p in BULLETINS.items()})
        self.files["/files/operaciones/GEIH/anex-GEIH-ago2026.xlsx"] = geih
        self.last_modified = "Wed, 07 Oct 2026 23:03:45 GMT"
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("indice-de-precios-al-consumidor-ipc"):
            return httpx.Response(200, text='<a href="/files/operaciones/IPC/sep2026/anex-IPC-Variacion-sep2026.xls">Variaciones porcentuales - septiembre 2026</a>')
        if path.endswith("empleo-y-desempleo"):
            return httpx.Response(200, text=(
                '<a href="/files/operaciones/GEIH/anex-GEIH-ago2026.xlsx">Descargar</a>'
                '<a href="/files/operaciones/GEIH/anex-GEIH-Desestacionalizado-ago2026.xlsx">Descargar</a>'
            ))
        if path.endswith("ipc-historico"):
            links = [f'<a href="{p}">Boletín técnico</a>' for p in [*BULLETINS, OLD_BULLETIN]]
            return httpx.Response(200, text="".join(links))
        if request.headers.get("If-Modified-Since") == self.last_modified:
            return httpx.Response(304)
        return httpx.Response(200, content=self.files[path], headers={"Last-Modified": self.last_modified})


@pytest.fixture
def fake_dane():
    return FakeDane(files.geih_annex(_geih_values()))


@pytest.fixture
def archive(fake_dane, raw_store, tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(fake_dane.handler))
    return DaneArchive(load_dane_config(), raw_store, EvidenceManifest(tmp_path / "dane.jsonl"), client)


@pytest.fixture
def connector(archive):
    archive.refresh(OCT_26)
    return DaneConnector(archive)


# Archive


def test_targets_find_files_by_link_text_and_pattern(archive):
    keys = dict(archive.targets())
    assert keys["dane_ipc_variations_annex"].endswith("anex-IPC-Variacion-sep2026.xls")
    assert keys["dane_geih_annex"].endswith("anex-GEIH-ago2026.xlsx")  # not the seasonally adjusted one
    bulletins = sorted(k for k in keys if k.startswith("dane_ipc_bulletin/"))
    assert len(bulletins) == 4 and not any("dic22" in k for k in bulletins)


def test_refresh_records_last_modified_and_rechecks_monthly(archive, fake_dane):
    first = archive.refresh(OCT_26)
    assert len(first) == 6 and all(r.last_modified == fake_dane.last_modified for r in first)

    fake_dane.requests.clear()
    assert archive.refresh(datetime(2026, 10, 30, tzinfo=UTC)) == []  # same month: not even asked
    assert not any(r.url.path.endswith((".xls", ".xlsx", ".pdf")) for r in fake_dane.requests)

    assert archive.refresh(datetime(2026, 11, 2, tzinfo=UTC)) == []  # next month: 304 Not Modified
    assert all(r.headers["If-Modified-Since"] == fake_dane.last_modified
               for r in fake_dane.requests if r.url.path.endswith((".xls", ".xlsx", ".pdf")))


def test_new_month_file_url_is_downloaded(archive, fake_dane):
    archive.refresh(OCT_26)
    old = "/files/operaciones/IPC/sep2026/anex-IPC-Variacion-sep2026.xls"
    new = "/files/operaciones/IPC/oct2026/anex-IPC-Variacion-oct2026.xls"
    fake_dane.files[new] = fake_dane.files[old]
    original = fake_dane.handler

    def handler(request):
        if request.url.path.endswith("indice-de-precios-al-consumidor-ipc"):
            return httpx.Response(200, text=f'<a href="{new}">Variaciones porcentuales - octubre 2026</a>')
        return original(request)

    archive._client = httpx.Client(transport=httpx.MockTransport(handler))
    records = archive.refresh(datetime(2026, 10, 31, tzinfo=UTC))  # same month, but a new URL
    assert [r.url for r in records] == [f"https://www.dane.gov.co{new}"]


# Connector values (as published, never computed)


def test_series_values(connector):
    pubs = connector.publications()
    monthly = series_values("inflation_monthly_national", pubs)
    ytd = series_values("inflation_ytd_national", pubs)
    annual = series_values("dane_ipc_annual_national", pubs)
    geih = series_values("dane_geih_unemployment_rate_national", pubs)

    assert monthly[Period(2026, 8)] == Decimal("0.39") and len(monthly) == 285
    assert ytd[Period(2026, 9)] == Decimal("5.74") and ytd[Period(2026, 8)] == Decimal("5.35")
    assert Period(2024, 1) not in ytd and Period(2024, 8) not in ytd  # bulletins without a published total
    assert annual[Period(2026, 9)] == Decimal("6.29") and annual[Period(2022, 12)] == Decimal("13.12")
    assert Period(2022, 11) not in annual  # before 2023, Decembers only
    assert geih[Period(2026, 8)] == Decimal("9.36")


@pytest.mark.parametrize(
    ("key", "value"),
    [("section", "Total Cabeceras"), ("section_position", 2), ("sheet", "Total 13 ciudades A.M."), ("row_label", "TD")],
)
def test_ficha_and_reader_must_agree_on_where_the_value_is(connector, key, value):
    ficha = load_ficha_by_code("dane_geih_unemployment_rate_national")
    changed = ficha.model_copy(update={"external": {**ficha.external, key: value}})
    with pytest.raises(ValueError, match="the GEIH reader reads"):
        connector.fetch(changed)


def test_approved_ficha_location_matches_the_reader(connector):
    assert connector.fetch(load_ficha_by_code("dane_geih_unemployment_rate_national"))


# Filter 5


def _relaxed(code):
    """The fixtures cover only some bulletins: drop the gap check for these tests."""
    f = load_ficha_by_code(code)
    return f.model_copy(update={"plausibility": f.plausibility.model_copy(update={"no_gaps": False, "expected_gaps": []})})


def _by_period(result):
    return {o.period: o for o in result.stored}


def test_monthly_contrast_with_bulletins_from_2023(connector, raw_store):
    ficha = _relaxed("inflation_monthly_national")
    runner = contrasts.inflation_monthly(ficha, connector.publications())
    obs = _by_period(ingest(ficha, connector, raw_store, InMemoryObservationStore(), contrast=runner))
    assert obs[Period(2026, 8)].contrast is ContrastStatus.PASSED
    assert obs[Period(2015, 5)].contrast is ContrastStatus.UNAVAILABLE  # before 2023
    assert obs[Period(2025, 5)].contrast is ContrastStatus.PENDING  # 2023+ but no bulletin archived


def test_ytd_single_publication_is_unavailable(connector, raw_store):
    ficha = _relaxed("inflation_ytd_national")
    runner = contrasts.inflation_ytd(ficha, connector.publications())
    obs = _by_period(ingest(ficha, connector, raw_store, InMemoryObservationStore(), contrast=runner))
    assert obs[Period(2026, 9)].contrast is ContrastStatus.PASSED  # annex and bulletin
    assert obs[Period(2026, 8)].contrast is ContrastStatus.UNAVAILABLE  # bulletin only
    assert obs[Period(2015, 12)].contrast is ContrastStatus.UNAVAILABLE  # annex only


def _suameca(values: dict[Period, str]) -> dict[Period, Decimal]:
    return {p: Decimal(v) for p, v in values.items()}


def test_mismatch_quarantines_suameca_and_uses_dane_with_mandatory_alert(connector, raw_store):
    pubs = connector.publications()
    geih = series_values("dane_geih_unemployment_rate_national", pubs)
    suameca = dict(geih)
    suameca[Period(2026, 6)] = geih[Period(2026, 6)] + Decimal("0.01")  # beyond ±0.005

    dane_ficha = approved(load_ficha_by_code("dane_geih_unemployment_rate_national"))
    dane_obs = _by_period(ingest(
        dane_ficha, connector, raw_store, InMemoryObservationStore(), contrast=contrasts.dane_geih(dane_ficha, suameca)
    ))
    june = dane_obs[Period(2026, 6)]
    assert june.contrast is ContrastStatus.FAILED
    assert june.status is ObservationStatus.ACCEPTED  # the producer's value is used...
    assert Flag.PRODUCER_VALUE_USED in june.flags  # ...with a mandatory review alert
    assert dane_obs[Period(2026, 5)].contrast is ContrastStatus.PASSED

    suameca_ficha = load_ficha_by_code("unemployment_rate_national")
    runner = contrasts.suameca_unemployment(suameca_ficha, geih)
    report = runner([ParsedValue(p, "national", v) for p, v in suameca.items()])
    assert report[(Period(2026, 6), "national")].status is ContrastStatus.FAILED
    assert not report[(Period(2026, 6), "national")].producer_prevails  # SUAMECA goes to quarantine


@pytest.mark.parametrize(("suameca", "status"), [("9.36", ContrastStatus.PASSED), ("9.37", ContrastStatus.FAILED)])
def test_tolerance_uses_the_lower_precision(suameca, status):
    ficha = load_ficha_by_code("unemployment_rate_national")
    dane_full = {Period(2026, 8): Decimal("9.3636797215898682")}
    report = contrasts.suameca_unemployment(ficha, dane_full)([ParsedValue(Period(2026, 8), "national", Decimal(suameca))])
    assert report[(Period(2026, 8), "national")].status is status  # ±0.005: 9.36 passes, 9.37 does not


def test_two_dane_publications_must_agree_without_the_producer_rule():
    # A December published by both the bulletin (annual) and the annex (year to date).
    december = Period(2025, 12)
    annex = dane.VariationsAnnex(date(2026, 10, 7), Period(2026, 9), {}, {december: Decimal("5.10")})
    pubs = DanePublications(annex, None, {december: dane.Bulletin(december, Decimal("5.11"), Decimal("0.27"), None)})
    ficha = load_ficha_by_code("dane_ipc_annual_national")
    runner = contrasts.dane_annual(ficha, pubs, suameca={december: Decimal("5.11")})
    state = runner([ParsedValue(december, "national", Decimal("5.11"))])[(december, "national")]
    assert state.status is ContrastStatus.FAILED
    assert not state.producer_prevails  # a disagreement inside the DANE goes to quarantine
