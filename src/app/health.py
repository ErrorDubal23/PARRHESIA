"""Daily connector health checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.catalog import Ficha
from app.connectors.socrata import SocrataConnector, read_metadata
from app.storage.observations import ObservationStore

STALE_AFTER_DAYS = 45  # alert when more than 45 whole days have passed


@dataclass(frozen=True)
class Freshness:
    rows_updated_at: datetime
    changed: bool  # rowsUpdatedAt differs from the last stored download: run the full download
    stale: bool  # alert: more than 45 days without an update
    days_since_update: int


def socrata_freshness(
    ficha: Ficha, connector: SocrataConnector, store: ObservationStore, now: datetime | None = None
) -> Freshness:
    """Checks only the dataset metadata (a few KB); the 41 MB export is downloaded only if it changed."""
    now = now or datetime.now(UTC)
    metadata = read_metadata(connector.fetch_metadata(ficha).content)
    downloads = store.downloads(ficha.code)
    last = downloads[-1].source_updated if downloads else None
    age = now - metadata.rows_updated_at
    return Freshness(
        rows_updated_at=metadata.rows_updated_at,
        changed=last != metadata.rows_updated_at.isoformat(),
        stale=age.days > STALE_AFTER_DAYS,
        days_since_update=age.days,
    )
