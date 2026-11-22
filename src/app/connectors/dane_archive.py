"""Archive of DANE publications and the connector that builds the DANE series from them.

The archive downloads the IPC variations annex, the GEIH annex and the IPC
bulletins (catalog/sources/dane_publications.yaml), keeps the originals in the
raw store and records each download in the evidence manifest. The connector
reads the latest archived version of each file; it never downloads by itself,
so every value can be traced to a manifest line.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict

from app.catalog import Ficha
from app.connectors import dane
from app.connectors.base import Parsed, ShapeError
from app.domain import ParsedValue, Period, RawDownload
from app.evidence import EvidenceManifest, EvidenceRecord, file_links, same_month, url_suffix
from app.storage.raw import RawStore

SOURCES_DIR = Path(__file__).resolve().parents[3] / "catalog" / "sources"

VARIATIONS = "dane_ipc_variations_annex"
GEIH = "dane_geih_annex"
BULLETIN = "dane_ipc_bulletin"


class DaneSourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    page: str
    link_text_prefix: str | None = None
    href_pattern: str | None = None
    many: bool = False
    from_year: int | None = None


class DaneSourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    channel: str
    sources: list[DaneSourceSpec]


def load_dane_config(code: str = "dane_publications", directory: Path = SOURCES_DIR) -> DaneSourcesConfig:
    config = DaneSourcesConfig.model_validate(yaml.safe_load((directory / f"{code}.yaml").read_text(encoding="utf-8")))
    if config.code != code:
        raise ValueError(f"{code}.yaml declares code {config.code!r}")
    return config


class DaneArchive:
    def __init__(
        self,
        config: DaneSourcesConfig,
        raw_store: RawStore,
        manifest: EvidenceManifest,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.raw_store = raw_store
        self.manifest = manifest
        self._client = client or httpx.Client(timeout=300.0, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"})
        self._pages: dict[str, list[tuple[str, str]]] = {}

    def refresh(self, now: datetime | None = None, *, force: bool = False) -> list[EvidenceRecord]:
        """Download what is new; a known file is re-checked at most once a month (If-Modified-Since)."""
        now = now or datetime.now(UTC)
        self._pages = {}  # pages are read fresh on every refresh; the cache only spans one refresh
        records = []
        for key, url in self.targets():
            previous = self.manifest.latest(key)
            headers = {}
            if previous and previous.url == url and not force:
                if same_month(datetime.fromisoformat(previous.downloaded_at), now):
                    continue
                if previous.last_modified:
                    headers["If-Modified-Since"] = previous.last_modified
            response = self._client.get(url, headers=headers)
            if response.status_code == 304:
                continue
            response.raise_for_status()
            raw = RawDownload(self.config.channel, key, url, response.content, now, url_suffix(url))
            record = EvidenceRecord(
                source=key,
                url=url,
                downloaded_at=now.isoformat(),
                sha256=raw.sha256,
                size=len(raw.content),
                location=self.raw_store.save(raw),
                changed=previous is None or previous.sha256 != raw.sha256,
                last_modified=response.headers.get("Last-Modified"),
            )
            self.manifest.append(record)
            records.append(record)
        return records

    def targets(self) -> list[tuple[str, str]]:
        """(source key, URL) of every file to keep. Bulletins get one key per file."""
        targets = []
        for spec in self.config.sources:
            links = self._links(spec.page)
            if spec.link_text_prefix:
                urls = sorted({url for text, url in links if text.startswith(spec.link_text_prefix)})
            else:
                urls = sorted({url for _, url in links if re.search(spec.href_pattern, url)})
            if spec.many:
                for url in urls:
                    match = re.search(spec.href_pattern, url)
                    year = int(match["year4"]) if match["year4"] else 2000 + int(match["year2"])
                    if spec.from_year is None or year >= spec.from_year:
                        targets.append((f"{spec.name}/{url.rsplit('/', 1)[-1]}", url))
            elif len(urls) == 1:
                targets.append((spec.name, urls[0]))
            else:
                raise ShapeError(f"{spec.name}: expected one link on {spec.page}, found {len(urls)}")
        return targets

    def archived(self, prefixes: Sequence[str]) -> list[RawDownload]:
        """The latest archived version of every file whose key starts with one of the prefixes."""
        raws = []
        for key, record in sorted(self.manifest.latest_by_source().items()):
            if not any(key == p or key.startswith(f"{p}/") for p in prefixes):
                continue
            raws.append(
                RawDownload(
                    channel=self.config.channel,
                    name=key,
                    url=record.url,
                    content=self.raw_store.load(record.location),
                    downloaded_at=datetime.fromisoformat(record.downloaded_at),
                    suffix=url_suffix(record.url),
                )
            )
        return raws

    def _links(self, page: str) -> list[tuple[str, str]]:
        if page not in self._pages:
            response = self._client.get(page)
            response.raise_for_status()
            self._pages[page] = file_links(response.text, page)
        return self._pages[page]


@dataclass
class DanePublications:
    variations: dane.VariationsAnnex | None = None
    geih: dane.GeihAnnex | None = None
    bulletins: dict[Period, dane.Bulletin] = field(default_factory=dict)


def read_publications(raws: Sequence[RawDownload], bulletin_cache: dict[str, dane.Bulletin] | None = None) -> DanePublications:
    """Read every archived file (filter 2 on each); two bulletins for one month stop the read.

    bulletin_cache: bulletins already read, by sha256 (reading a PDF takes about a second).
    """
    bulletin_cache = {} if bulletin_cache is None else bulletin_cache
    publications = DanePublications()
    for raw in raws:
        if raw.name == VARIATIONS:
            publications.variations = dane.read_variations(raw.content)
        elif raw.name == GEIH:
            publications.geih = dane.read_geih(raw.content)
        elif raw.name.startswith(f"{BULLETIN}/"):
            if raw.sha256 not in bulletin_cache:
                bulletin_cache[raw.sha256] = dane.read_bulletin(raw.content)
            bulletin = bulletin_cache[raw.sha256]
            if bulletin.period in publications.bulletins:
                raise ShapeError(f"two bulletins for {bulletin.period}")
            publications.bulletins[bulletin.period] = bulletin
        else:
            raise ShapeError(f"unexpected archived file {raw.name}")
    return publications


# Which archived files each series needs.
FILES_BY_SERIES = {
    "inflation_monthly_national": (VARIATIONS,),
    "inflation_ytd_national": (VARIATIONS, BULLETIN),
    "dane_ipc_annual_national": (VARIATIONS, BULLETIN),
    "dane_geih_unemployment_rate_national": (GEIH,),
}
# Before 2023 the DANE annual series has only Decembers, from the annex (dane_ipc_annual_national ficha).
BULLETINS_FROM = Period(2023, 1)


class DaneConnector:
    channel = "dane_web"

    def __init__(self, archive: DaneArchive) -> None:
        self.archive = archive
        self.last: DanePublications | None = None
        self._bulletins: dict[str, dane.Bulletin] = {}

    def fetch(self, ficha: Ficha) -> list[RawDownload]:
        if ficha.code not in FILES_BY_SERIES:
            raise ValueError(f"no DANE files configured for {ficha.code}")
        if ficha.code == "dane_geih_unemployment_rate_national":
            _check_geih_ficha(ficha)
        raws = self.archive.archived(FILES_BY_SERIES[ficha.code])
        if not raws:
            raise ShapeError(f"{ficha.code}: nothing archived yet; run the DANE archive refresh first")
        return raws

    def publications(self) -> DanePublications:
        """Every archived DANE file, read once (used to build the contrasts)."""
        return read_publications(self.archive.archived((VARIATIONS, GEIH, BULLETIN)), self._bulletins)

    def parse(self, raws: Sequence[RawDownload], ficha: Ficha) -> Parsed:
        pubs = read_publications(raws, self._bulletins)
        self.last = pubs
        values = series_values(ficha.code, pubs)
        updated = pubs.geih.updated_on if ficha.code == "dane_geih_unemployment_rate_national" else _need(pubs.variations).updated_on
        return Parsed(
            values=[ParsedValue(p, ficha.geography, v) for p, v in sorted(values.items())],
            source_updated=updated.isoformat(),
        )


def series_values(code: str, pubs: DanePublications) -> dict[Period, Decimal]:
    """The values of each DANE series, taken as published (never computed)."""
    if code == "inflation_monthly_national":
        return dict(_need(pubs.variations).monthly)
    if code == "dane_geih_unemployment_rate_national":
        return dict(_need(pubs.geih).unemployment)
    if code == "inflation_ytd_national":
        values = {p: b.ytd for p, b in pubs.bulletins.items() if b.ytd is not None}
        values.update(_need(pubs.variations).ytd)  # the annex wins where both publish; the contrast compares them
        return values
    if code == "dane_ipc_annual_national":
        # December "año corrido" equals the 12-month variation of December (ficha);
        # used only before the bulletins start.
        values = {p: v for p, v in _need(pubs.variations).ytd.items() if p.month == 12 and p < BULLETINS_FROM}
        values.update({p: b.annual for p, b in pubs.bulletins.items()})
        return values
    raise ValueError(f"unknown DANE series {code}")


def _check_geih_ficha(ficha: Ficha) -> None:
    """The approved ficha and the reader must name the same sheet, section and row."""
    expected = {
        "sheet": dane.GEIH_SHEET,
        "section": dane.GEIH_SECTION,
        "section_position": dane.GEIH_SECTION_POSITION,
        "row_label": dane.GEIH_ROW,
    }
    actual = {key: ficha.external.get(key) for key in expected}
    if actual != expected:
        raise ValueError(f"{ficha.code}: ficha says {actual}, the GEIH reader reads {expected}")


def _need(value):
    if value is None:
        raise ShapeError("a required DANE file is not archived")
    return value
