"""Archive of Policía publications used as homicide contrast, and the filter 5 runner built on it.

Original files go to the raw store (data/raw/, not in git). The manifest with
hashes and metadata (evidence/*.jsonl) is kept in the repository. The Policía
servers send no ETag or Last-Modified, so each file is downloaded at most once a
calendar month and its sha256 is compared with the previous version.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict

from app.catalog import Ficha
from app.connectors import policia
from app.connectors.base import ShapeError
from app.domain import ContrastLevel, ParsedValue, Period, RawDownload
from app.evidence import EvidenceManifest, EvidenceRecord, page_links, same_month, url_suffix
from app.storage.raw import RawStore
from app.validation.contrast import (
    ContrastReport,
    ContrastSource,
    Difference,
    ExpectedSource,
    compare_with_sources,
)

SOURCES_DIR = Path(__file__).resolve().parents[3] / "catalog" / "sources"

Kind = Literal["cuadros_ultimo_mes", "cuadros_anual", "registro", "legacy"]


class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Kind
    level: ContrastLevel
    years: list[int] = []
    link_text: str | None = None
    link_text_prefix: str | None = None
    url: str | None = None


class SourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    channel: str
    page: str
    legacy_page: str
    sources: list[SourceSpec]


def load_sources_config(code: str, directory: Path = SOURCES_DIR) -> SourcesConfig:
    config = SourcesConfig.model_validate(yaml.safe_load((directory / f"{code}.yaml").read_text(encoding="utf-8")))
    if config.code != code:
        raise ValueError(f"{code}.yaml declares code {config.code!r}")
    return config


class PoliciaArchive:
    def __init__(
        self,
        config: SourcesConfig,
        raw_store: RawStore,
        manifest: EvidenceManifest,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.raw_store = raw_store
        self.manifest = manifest
        self._client = client or httpx.Client(timeout=600.0, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"})
        self._page_links: dict[str, str] | None = None
        self.last_differences: list[Difference] = []
        self.last_pending: dict[str, str] = {}

    def refresh(self, now: datetime | None = None, *, force: bool = False) -> list[EvidenceRecord]:
        """Download every source not yet downloaded this calendar month (or all, if forced)."""
        now = now or datetime.now(UTC)
        self._page_links = None  # the page is read fresh on every refresh
        records = []
        for spec in self.config.sources:
            previous = self.manifest.latest(spec.name)
            if previous and not force and same_month(datetime.fromisoformat(previous.downloaded_at), now):
                continue
            url = self._url_for(spec)
            response = self._client.get(url)
            response.raise_for_status()
            raw = RawDownload(self.config.channel, spec.name, url, response.content, now, url_suffix(url))
            record = EvidenceRecord(
                source=spec.name,
                url=url,
                downloaded_at=now.isoformat(),
                sha256=raw.sha256,
                size=len(raw.content),
                location=self.raw_store.save(raw),
                changed=previous is None or previous.sha256 != raw.sha256,
            )
            self.manifest.append(record)
            records.append(record)
        return records

    def load(self, today: date) -> tuple[list[ExpectedSource], dict[str, ContrastSource], dict[str, str]]:
        """Read the latest archived version of every source.

        Returns the expected sources (with the years each should cover), the
        sources that could be read, and why the others could not.
        """
        loaded: dict[str, ContrastSource] = {}
        pending: dict[str, str] = {}
        contents: dict[str, tuple[bytes, str]] = {}
        for spec in self.config.sources:
            record = self.manifest.latest(spec.name)
            if record is None:
                pending[spec.name] = "never downloaded"
                continue
            try:
                contents[spec.name] = (self.raw_store.load(record.location), record.sha256)
            except FileNotFoundError:
                pending[spec.name] = f"archived file {record.location} is not available in this raw store"

        anual = None
        for spec in self.config.sources:
            if spec.name not in contents:
                continue
            content, sha = contents[spec.name]
            try:
                if spec.kind == "cuadros_anual":
                    anual = policia.read_cuadros_anual(content)
                    values = {
                        Period(y): Decimal(t)
                        for y, t in anual.totals.items()
                        if y in spec.years and y not in anual.provisional_years
                    }
                elif spec.kind == "registro":
                    [year] = spec.years
                    values = _decimal(policia.read_registro(content, year).values)
                elif spec.kind == "legacy":
                    [year] = spec.years
                    values = _decimal(policia.read_legacy(content, year).values)
                else:
                    continue  # último mes needs the annual file; resolved below
            except ShapeError as exc:
                pending[spec.name] = f"layout changed: {exc}"
                continue
            loaded[spec.name] = ContrastSource(spec.name, spec.level, values, sha)

        expected = []
        for spec in self.config.sources:
            years = spec.years
            if spec.kind == "cuadros_ultimo_mes":
                years = sorted(anual.provisional_years) if anual else [today.year]
                if spec.name in contents and spec.name not in pending:
                    self._load_ultimo_mes(spec, contents[spec.name], anual, loaded, pending)
            expected.append(ExpectedSource(spec.name, spec.level, frozenset(years)))
        return expected, loaded, pending

    def contrast_runner(self, ficha: Ficha, today: date):
        """A filter 5 runner for the pipeline; keeps the last differences found."""
        expected, loaded, pending = self.load(today)
        self.last_differences = []
        self.last_pending = pending

        def run(values: Sequence[ParsedValue]) -> ContrastReport:
            report, differences = compare_with_sources(values, ficha, expected, loaded, pending)
            self.last_differences = differences
            return report

        return run

    def _load_ultimo_mes(self, spec, content_sha, anual, loaded, pending) -> None:
        content, sha = content_sha
        if anual is None:
            pending[spec.name] = "annual file not available to confirm the year"
            return
        try:
            resolved = policia.resolve_ultimo_mes(policia.read_cuadros_ultimo_mes(content), anual)
        except ShapeError as exc:
            pending[spec.name] = f"layout changed: {exc}"
            return
        if resolved.pending_reason:
            pending[spec.name] = resolved.pending_reason
            return
        loaded[spec.name] = ContrastSource(spec.name, spec.level, _decimal(resolved.values), sha)

    def _url_for(self, spec: SourceSpec) -> str:
        if spec.url:
            return spec.url
        links = self._links()
        if spec.link_text:
            matches = [href for text, href in links.items() if text == spec.link_text]
        else:
            matches = [href for text, href in links.items() if text.startswith(spec.link_text_prefix or "")]
        if len(matches) != 1:
            raise ShapeError(f"{spec.name}: expected one link on {self.config.page}, found {len(matches)}")
        return matches[0]

    def _links(self) -> dict[str, str]:
        if self._page_links is None:
            response = self._client.get(self.config.page)
            response.raise_for_status()
            self._page_links = page_links(response.text, self.config.page)
        return self._page_links


def _decimal(values: dict[Period, int]) -> dict[Period, Decimal]:
    return {k: Decimal(v) for k, v in values.items()}
