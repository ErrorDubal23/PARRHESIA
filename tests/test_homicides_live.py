"""Daily health check for the homicide sources (live). Run with: uv run pytest -m live

Only metadata and page links are checked here; full downloads happen in
`python -m app.runs homicides` when rowsUpdatedAt changes (and once a month for
the Policía files).
"""

import httpx
import pytest

from app.connectors.policia_archive import load_sources_config, page_links
from app.connectors.socrata import SocrataConnector, check_columns, read_metadata
from app.health import STALE_AFTER_DAYS, socrata_freshness
from app.storage.observations import InMemoryObservationStore

pytestmark = pytest.mark.live


def test_datos_gov_metadata_matches_ficha_and_is_fresh(ficha):
    f = ficha("homicides_intentional_national")
    connector = SocrataConnector()
    check_columns(read_metadata(connector.fetch_metadata(f).content), f)  # filter 2 on the metadata
    freshness = socrata_freshness(f, connector, InMemoryObservationStore())
    assert not freshness.stale, f"no update in {freshness.days_since_update} days (alert after {STALE_AFTER_DAYS})"


def test_policia_page_still_links_every_configured_file():
    config = load_sources_config("homicides_intentional_policia")
    client = httpx.Client(timeout=60.0, headers={"User-Agent": "Mozilla/5.0"})
    links = page_links(client.get(config.page).text, config.page)
    for spec in config.sources:
        if spec.link_text:
            assert spec.link_text in links, spec.name
        elif spec.link_text_prefix:
            assert sum(text.startswith(spec.link_text_prefix) for text in links) == 1, spec.name
        else:
            assert client.head(spec.url).status_code == 200, spec.name
