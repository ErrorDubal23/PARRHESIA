"""Observation store: append-only, one row per new or changed value per download."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain import Download, Observation, ObservationStatus, Period

Key = tuple[Period, str]  # (period, territory)


class ObservationStore(Protocol):
    def add(self, download: Download, observations: Sequence[Observation]) -> None: ...

    def downloads(self, series_code: str) -> list[Download]: ...

    def latest(self, series_code: str, *, include_quarantined: bool = False) -> dict[Key, Observation]:
        """Most recent version of each value.

        By default only accepted versions count, so a value whose newest version is
        in quarantine falls back to its last validated version. Quarantined data is
        returned only when asked for explicitly.
        """
        ...


class InMemoryObservationStore:
    """Development and test store; PostgreSQL will implement the same protocol."""

    def __init__(self) -> None:
        self._downloads: list[Download] = []
        self._observations: list[Observation] = []

    def add(self, download: Download, observations: Sequence[Observation]) -> None:
        if any(d.id == download.id for d in self._downloads):
            raise ValueError(f"download {download.id} already stored")
        if any(o.download_id != download.id for o in observations):
            raise ValueError("observations must belong to the download being added")
        self._downloads.append(download)
        self._observations.extend(observations)

    def downloads(self, series_code: str) -> list[Download]:
        return [d for d in self._downloads if d.series_code == series_code]

    def latest(self, series_code: str, *, include_quarantined: bool = False) -> dict[Key, Observation]:
        result: dict[Key, Observation] = {}
        for obs in self._observations:  # append order = download order
            if obs.series_code != series_code:
                continue
            if not include_quarantined and obs.status is not ObservationStatus.ACCEPTED:
                continue
            result[(obs.period, obs.territory)] = obs
        return result
