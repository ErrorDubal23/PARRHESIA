"""Operational runs.

    uv run python -m app.runs homicides [--allow-unapproved] [--force-refresh]
    uv run python -m app.runs dane [--force-refresh]

homicides: archives the Policía contrast files (once a month), downloads
datos.gov.co, runs filters 1 to 6 and prints every contrast difference in the
shape of known_version_differences entries, for a person to review and register.

dane: archives the DANE publications, downloads SUAMECA, and ingests the four
DANE series and the two SUAMECA series they contrast with (both directions).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app import contrasts
from app.catalog import load_ficha_by_code
from app.connectors.base import Parsed
from app.connectors.dane_archive import DaneArchive, DaneConnector, load_dane_config, series_values
from app.connectors.policia_archive import PoliciaArchive, load_sources_config
from app.connectors.socrata import SocrataConnector
from app.db import connect
from app.db.migrate import pending as pending_migrations
from app.db.store import PostgresObservationStore
from app.db.sync import sync_all
from app.connectors.suameca import SuamecaConnector
from app.domain import RawDownload
from app.evidence import EVIDENCE_DIR, EvidenceManifest
from app.health import Freshness, socrata_freshness
from app.pipeline import REVIEW_FLAGS, IngestResult, ingest
from app.storage.observations import InMemoryObservationStore, ObservationStore
from app.storage.raw import FilesystemRawStore
from app.validation.contrast import Difference

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
HOMICIDES = "homicides_intentional_national"


@dataclass(frozen=True)
class HomicidesRun:
    freshness: Freshness
    result: IngestResult | None  # None when rowsUpdatedAt did not change
    differences: list[Difference]
    pending_sources: dict[str, str]


def run_homicides(
    store: ObservationStore,
    *,
    raw_root: Path = DATA_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    allow_unapproved: bool = False,
    force_refresh: bool = False,
    now: datetime | None = None,
) -> HomicidesRun:
    now = now or datetime.now(UTC)
    ficha = load_ficha_by_code(HOMICIDES)
    raw_store = FilesystemRawStore(raw_root)
    connector = SocrataConnector()

    freshness = socrata_freshness(ficha, connector, store, now)
    archive = PoliciaArchive(
        load_sources_config(ficha.contrast_with[0]),
        raw_store,
        EvidenceManifest(evidence_dir / f"{ficha.contrast_with[0]}.jsonl"),
    )
    archive.refresh(now, force=force_refresh)
    if not freshness.changed:
        return HomicidesRun(freshness, None, [], archive.last_pending)

    result = ingest(
        ficha,
        connector,
        raw_store,
        store,
        contrast=archive.contrast_runner(ficha, now.date()),
        allow_unapproved=allow_unapproved,
        today=now.date(),
    )
    return HomicidesRun(freshness, result, archive.last_differences, archive.last_pending)


class PrefetchedConnector:
    """Serves files already downloaded in this run, so a source is fetched once."""

    def __init__(self, connector, raws: list[RawDownload]) -> None:
        self.channel = connector.channel
        self._connector, self._raws = connector, raws

    def fetch(self, ficha) -> list[RawDownload]:
        return self._raws

    def parse(self, raws, ficha) -> Parsed:
        return self._connector.parse(raws, ficha)


DANE_SERIES = (
    "dane_ipc_annual_national",
    "dane_geih_unemployment_rate_national",
    "inflation_monthly_national",
    "inflation_ytd_national",
)
SUAMECA_CONTRASTED = ("inflation_annual_national", "unemployment_rate_national")


@dataclass(frozen=True)
class DaneRun:
    results: dict[str, IngestResult]
    differences: dict[str, list[Difference]]


def run_dane(
    store: ObservationStore,
    *,
    raw_root: Path = DATA_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    force_refresh: bool = False,
    now: datetime | None = None,
    suameca: SuamecaConnector | None = None,
    archive: DaneArchive | None = None,
) -> DaneRun:
    now = now or datetime.now(UTC)
    raw_store = FilesystemRawStore(raw_root)
    archive = archive or DaneArchive(
        load_dane_config(), raw_store, EvidenceManifest(evidence_dir / "dane_publications.jsonl")
    )
    archive.refresh(now, force=force_refresh)
    dane_connector = DaneConnector(archive)
    pubs = dane_connector.publications()
    dane_values = {code: series_values(code, pubs) for code in DANE_SERIES}

    suameca = suameca or SuamecaConnector()
    fichas = {code: load_ficha_by_code(code) for code in DANE_SERIES + SUAMECA_CONTRASTED}
    prefetched, suameca_values = {}, {}
    for code in SUAMECA_CONTRASTED:
        raws = suameca.fetch(fichas[code])
        prefetched[code] = PrefetchedConnector(suameca, raws)
        suameca_values[code] = {v.period: v.value for v in suameca.parse(raws, fichas[code]).values}

    runners = {
        "dane_ipc_annual_national": contrasts.dane_annual(
            fichas["dane_ipc_annual_national"], pubs, suameca_values["inflation_annual_national"]
        ),
        "dane_geih_unemployment_rate_national": contrasts.dane_geih(
            fichas["dane_geih_unemployment_rate_national"], suameca_values["unemployment_rate_national"]
        ),
        "inflation_monthly_national": contrasts.inflation_monthly(fichas["inflation_monthly_national"], pubs),
        "inflation_ytd_national": contrasts.inflation_ytd(fichas["inflation_ytd_national"], pubs),
        "inflation_annual_national": contrasts.suameca_inflation(
            fichas["inflation_annual_national"], dane_values["dane_ipc_annual_national"]
        ),
        "unemployment_rate_national": contrasts.suameca_unemployment(
            fichas["unemployment_rate_national"], dane_values["dane_geih_unemployment_rate_national"]
        ),
    }
    results = {}
    for code, runner in runners.items():
        connector = dane_connector if code in DANE_SERIES else prefetched[code]
        results[code] = ingest(fichas[code], connector, raw_store, store, contrast=runner, today=now.date())
    return DaneRun(results, {code: runner.differences for code, runner in runners.items()})


def differences_yaml(differences: list[Difference]) -> str:
    entries = [
        {
            "period": str(d.period),
            "level": d.level.value,
            "source": d.source,
            "source_value": int(d.source_value) if d.source_value == int(d.source_value) else str(d.source_value),
            "series_value": int(d.series_value) if d.series_value == int(d.series_value) else str(d.series_value),
        }
        for d in differences
    ]
    return yaml.safe_dump({"known_version_differences": entries}, allow_unicode=True, sort_keys=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.runs")
    parser.add_argument("series", choices=["homicides", "dane"])
    parser.add_argument("--allow-unapproved", action="store_true", help="development only; nothing is persisted")
    parser.add_argument("--force-refresh", action="store_true", help="download contrast files even if done this month")
    parser.add_argument("--db", action="store_true", help="persist in PostgreSQL (DATABASE_URL); default: in memory")
    args = parser.parse_args(argv)
    if args.db and args.allow_unapproved:
        parser.error("--allow-unapproved is for development only and cannot be combined with --db")
    store = _store(args.db)
    if args.series == "dane":
        return _print_dane(run_dane(store, force_refresh=args.force_refresh))

    run = run_homicides(store, allow_unapproved=args.allow_unapproved, force_refresh=args.force_refresh)
    f = run.freshness
    print(f"datos.gov.co rowsUpdatedAt: {f.rows_updated_at.isoformat()} ({f.days_since_update} days ago)")
    if f.stale:
        print(f"ALERT: more than 45 days without an update ({f.days_since_update} days)")
    for name, reason in sorted(run.pending_sources.items()):
        print(f"contrast source pending: {name}: {reason}")
    if run.result is None:
        print("rowsUpdatedAt unchanged: full download skipped")
        return 0
    stored = run.result.stored
    by_contrast: dict[str, int] = {}
    for obs in stored:
        key = f"{obs.contrast.value}/{obs.contrast_level.value if obs.contrast_level else '-'}"
        by_contrast[key] = by_contrast.get(key, 0) + 1
    print(f"observations: {len(stored)}; by contrast: {dict(sorted(by_contrast.items()))}")
    unregistered = [d for d in run.differences if not d.registered]
    print(f"differences: {len(run.differences)} ({len(unregistered)} not registered)")
    print(differences_yaml(run.differences))
    return 0


def _store(use_db: bool) -> ObservationStore:
    """In memory, or PostgreSQL after checking migrations and syncing the copy of git."""
    if not use_db:
        return InMemoryObservationStore()
    conn = connect()
    missing = pending_migrations(conn)
    if missing:
        raise SystemExit(f"pending migrations {missing}: run `uv run python -m app.db.migrate` first")
    report = sync_all(conn)
    print(f"synced from git: {len(report.series)} series, {report.evidence_lines} new evidence lines"
          + (f"; drafts not synced: {', '.join(report.skipped_drafts)}" if report.skipped_drafts else ""))
    return PostgresObservationStore(conn)


def _print_dane(run: DaneRun) -> int:
    for code, result in run.results.items():
        summary: dict[str, int] = {}
        for obs in result.stored:
            key = f"{obs.status.value}/{obs.contrast.value}/{obs.contrast_level.value if obs.contrast_level else '-'}"
            summary[key] = summary.get(key, 0) + 1
        review = sum(1 for o in result.stored if o.flags & REVIEW_FLAGS)
        print(f"{code}: {len(result.stored)} observations {dict(sorted(summary.items()))}; needing review: {review}")
        differences = run.differences[code]
        if differences:
            print(differences_yaml(differences))
    return 0


if __name__ == "__main__":
    sys.exit(main())
