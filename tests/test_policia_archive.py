"""Policía archive: monthly download with hash comparison, manifest, and the homicide contrast end to end."""

from datetime import UTC, date, datetime

import httpx
import pytest

from app.catalog import KnownVersionDifference
from app.connectors.base import ShapeError
from app.connectors.policia_archive import PoliciaArchive, SourcesConfig, load_sources_config
from app.evidence import EvidenceManifest, page_links
from app.domain import ContrastLevel, ContrastStatus, Flag, ObservationStatus, Period
from app.pipeline import ingest
from app.storage.observations import InMemoryObservationStore
from tests import policia_files as files
from tests.test_socrata import FakeDatosGov, _connector, csv_body, metadata, row

PAGE = "https://www.policia.gov.co/estadistica-delictiva"
OCT_25 = datetime(2026, 10, 25, 12, tzinfo=UTC)

CONFIG = SourcesConfig.model_validate(
    {
        "code": "test",
        "channel": "policia_siedco",
        "page": PAGE,
        "legacy_page": "https://www.policia.gov.co/estadistica-delictiva-old",
        "sources": [
            {"name": "ultimo", "kind": "cuadros_ultimo_mes", "level": "monthly", "link_text": "Cuadro de salida delictivo ultimo mes"},
            {"name": "anual", "kind": "cuadros_anual", "level": "annual", "years": [2024],
             "link_text_prefix": "Cuadro de salida delictivo mes a mes anualizado"},
            {"name": "registro_2024", "kind": "registro", "level": "monthly", "years": [2024],
             "link_text": "Información de delitos a nivel de registro año 2024"},
            {"name": "legacy_2015", "kind": "legacy", "level": "monthly", "years": [2015],
             "url": "https://www.policia.gov.co/sites/default/files/delitos-impacto/Homicidio%20Intencional%202015.xlsx"},
        ],
    }
)

PAGE_HTML = """
<a href="/sites/default/files/CUADROS_DE_SALIDA_DELICTIVO_ULTIMO_MES_2.xlsx" target="_blank">Cuadro de salida delictivo ultimo mes</a>
<a href="/sites/default/files/C.S_DELICTIVO_MENSUAL_ANUAL_2020_2026.zip">Cuadro de salida delictivo mes a mes anualizado 2020 - 2026</a>
<a href="/sites/default/files/REGISTRO_2024_3.xlsx"><span>Información de delitos a nivel de registro año 2024</span></a>
"""


class FakePolicia:
    def __init__(self) -> None:
        months_2026 = [100] * 9
        self.files = {
            "/sites/default/files/CUADROS_DE_SALIDA_DELICTIVO_ULTIMO_MES_2.xlsx": files.ultimo_mes(months_2026),
            "/sites/default/files/C.S_DELICTIVO_MENSUAL_ANUAL_2020_2026.zip": files.anual({2024: 1200, 2026: 900}, 2026),
            "/sites/default/files/REGISTRO_2024_3.xlsx": files.registro(2024, {m: 100 for m in range(1, 13)}),
            "/sites/default/files/delitos-impacto/Homicidio%20Intencional%202015.xlsx": files.legacy(
                2015, {m: 100 for m in range(1, 13)}
            ),
        }
        self.requests: list[str] = []
        self.page_html = PAGE_HTML

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        self.requests.append(path)
        if path == "/estadistica-delictiva":
            return httpx.Response(200, text=self.page_html)
        return httpx.Response(200, content=self.files[path])


@pytest.fixture
def policia():
    return FakePolicia()


@pytest.fixture
def archive(policia, raw_store, tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(policia.handler))
    return PoliciaArchive(CONFIG, raw_store, EvidenceManifest(tmp_path / "evidence" / "test.jsonl"), client)


def test_real_sources_config_loads():
    config = load_sources_config("homicides_intentional_policia")
    names = {s.name for s in config.sources}
    assert {"policia_cuadros_ultimo_mes", "policia_cuadros_anual", "policia_registro_2024", "policia_legacy_2010"} <= names


def test_page_links_by_text():
    links = page_links(PAGE_HTML, PAGE)
    assert links["Información de delitos a nivel de registro año 2024"] == (
        "https://www.policia.gov.co/sites/default/files/REGISTRO_2024_3.xlsx"
    )


def test_duplicate_link_text_stops():
    with pytest.raises(ShapeError):
        page_links(PAGE_HTML + PAGE_HTML, PAGE)


# Monthly refresh with hash comparison


def test_refresh_archives_every_file_with_hash(archive, raw_store):
    records = archive.refresh(OCT_25)
    assert [r.source for r in records] == ["ultimo", "anual", "registro_2024", "legacy_2015"]
    assert all(r.changed for r in records)
    for r in records:
        assert len(raw_store.load(r.location)) == r.size


def test_refresh_downloads_once_a_month(archive, policia):
    archive.refresh(OCT_25)
    policia.requests.clear()
    assert archive.refresh(datetime(2026, 10, 31, tzinfo=UTC)) == []
    assert policia.requests == []

    november = archive.refresh(datetime(2026, 11, 2, tzinfo=UTC))
    assert len(november) == 4
    assert not any(r.changed for r in november)  # same content, same hash


def test_changed_file_is_marked_changed(archive, policia):
    archive.refresh(OCT_25)
    path = "/sites/default/files/CUADROS_DE_SALIDA_DELICTIVO_ULTIMO_MES_2.xlsx"
    policia.files[path] = files.ultimo_mes([100] * 10, published="20 noviembre del 2026")
    records = {r.source: r for r in archive.refresh(datetime(2026, 11, 21, tzinfo=UTC))}
    assert records["ultimo"].changed and not records["registro_2024"].changed


def test_page_is_read_again_on_each_refresh(archive, policia):
    archive.refresh(OCT_25)
    renamed = "/sites/default/files/CUADROS_DE_SALIDA_DELICTIVO_ULTIMO_MES_3.xlsx"
    policia.files[renamed] = files.ultimo_mes([100] * 10, published="20 noviembre del 2026")
    policia.page_html = PAGE_HTML.replace("ULTIMO_MES_2", "ULTIMO_MES_3")
    records = {r.source: r for r in archive.refresh(datetime(2026, 11, 21, tzinfo=UTC))}
    assert records["ultimo"].url.endswith("ULTIMO_MES_3.xlsx")


def test_manifest_keeps_every_version(archive):
    archive.refresh(OCT_25)
    archive.refresh(datetime(2026, 11, 2, tzinfo=UTC))
    assert len(archive.manifest.records()) == 8


# Loading contrast sources


def test_load_reads_sources_and_resolves_current_year(archive):
    archive.refresh(OCT_25)
    expected, loaded, pending = archive.load(date(2026, 10, 25))
    assert pending == {}
    assert loaded["ultimo"].values[Period(2026, 9)] == 100
    assert Period(2026) not in loaded["anual"].values  # provisional year is not used
    assert loaded["anual"].values[Period(2024)] == 1200
    years = {e.name: e.years for e in expected}
    assert years["ultimo"] == {2026}


def test_never_downloaded_source_is_pending(archive):
    _, loaded, pending = archive.load(date(2026, 10, 25))
    assert loaded == {} and set(pending) == {"ultimo", "anual", "registro_2024", "legacy_2015"}


def test_changed_layout_makes_the_source_pending(archive, policia):
    policia.files["/sites/default/files/REGISTRO_2024_3.xlsx"] = files.legacy(2024, {1: 1})
    archive.refresh(OCT_25)
    _, loaded, pending = archive.load(date(2026, 10, 25))
    assert "registro_2024" not in loaded
    assert pending["registro_2024"].startswith("layout changed")


# End to end: datos.gov.co + Policía contrast


def _socrata_rows(overrides=None):
    overrides = overrides or {}
    rows = []
    for year, months in ((2012, 12), (2015, 12), (2024, 12), (2026, 9)):
        for m in range(1, months + 1):
            quantity = overrides.get((year, m), 100)
            rows.append(row(f"01/{m:02d}/{year}", quantity=str(quantity)))
    return csv_body(*rows)


def _ingest(ficha_obj, archive, rows):
    connector = _connector(FakeDatosGov(metadata(), rows))
    return ingest(
        ficha_obj, connector, archive.raw_store, InMemoryObservationStore(),
        contrast=archive.contrast_runner(ficha_obj, OCT_25.date()), allow_unapproved=True, today=OCT_25.date(),
    )


def _homicides(ficha, differences=()):
    f = ficha("homicides_intentional_national")
    # The test series has gaps between years and no 2026-08 reference value.
    rules = f.plausibility.model_copy(update={"no_gaps": False, "min": None})
    return f.model_copy(
        update={"plausibility": rules, "reference_values": [], "known_version_differences": list(differences)}
    )


def test_contrast_states_by_year(ficha, archive):
    archive.refresh(OCT_25)
    result = _ingest(_homicides(ficha), archive, _socrata_rows())
    by_period = {o.period: o for o in result.stored}

    assert by_period[Period(2012, 5)].contrast is ContrastStatus.UNAVAILABLE
    assert by_period[Period(2012, 5)].status is ObservationStatus.ACCEPTED
    assert Flag.CONTRAST_UNAVAILABLE in by_period[Period(2012, 5)].flags

    for period in (Period(2015, 5), Period(2024, 5), Period(2026, 9)):
        assert by_period[period].contrast is ContrastStatus.PASSED
        assert by_period[period].contrast_level is ContrastLevel.MONTHLY
        assert by_period[period].status is ObservationStatus.ACCEPTED


def test_unregistered_difference_is_listed_and_quarantined(ficha, archive):
    archive.refresh(OCT_25)
    result = _ingest(_homicides(ficha), archive, _socrata_rows({(2024, 10): 101}))
    october = next(o for o in result.stored if o.period == Period(2024, 10))
    assert october.contrast is ContrastStatus.FAILED and october.status is ObservationStatus.QUARANTINED
    # Month and annual checks both see it; the annual mismatch also fails the rest of 2024.
    listed = {(str(d.period), d.source, int(d.source_value), int(d.series_value)) for d in archive.last_differences}
    assert listed == {("2024-10", "registro_2024", 100, 101), ("2024", "anual", 1200, 1201)}


def test_registered_differences_pass(ficha, archive):
    archive.refresh(OCT_25)
    registered = [
        KnownVersionDifference(period="2024-10", level="monthly", source="registro_2024", source_value=100, series_value=101),
        KnownVersionDifference(period="2024", level="annual", source="anual", source_value=1200, series_value=1201),
    ]
    result = _ingest(_homicides(ficha, registered), archive, _socrata_rows({(2024, 10): 101}))
    october = next(o for o in result.stored if o.period == Period(2024, 10))
    assert october.contrast is ContrastStatus.PASSED and Flag.KNOWN_VERSION_DIFFERENCE in october.flags
    assert all(d.registered for d in archive.last_differences)
