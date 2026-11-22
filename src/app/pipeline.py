"""Ingestion: download -> archive originals -> filters 2 to 6 -> observations (quarantined or accepted)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.catalog import Ficha
from app.connectors.base import Connector
from app.domain import NON_BLOCKING_FLAGS, Download, Flag, Observation, ObservationStatus, ParsedValue, RawFileRef
from app.storage.observations import ObservationStore
from app.storage.raw import RawStore
from app.validation.changes import detect_changes
from app.validation.contrast import ContrastReport, flags_for, period_contrast
from app.validation.plausibility import check_plausibility
from app.validation.references import ReferenceCheck, ReferenceMismatch, check_references

ContrastRunner = Callable[[Sequence[ParsedValue]], ContrastReport]

# Raised once, when a value first arrives; kept on later runs while the value is
# unchanged, so a jump or a changed final value is never accepted without review.
REVIEW_FLAGS = frozenset({Flag.JUMP, Flag.HISTORY_CHANGED, Flag.PRODUCER_VALUE_USED})


class UnapprovedSeries(Exception):
    """Filter 1: a series is never connected without a valid approval."""


@dataclass(frozen=True)
class IngestResult:
    download: Download
    stored: list[Observation]  # new or changed values only (append-only store)
    unchanged: int
    references: list[ReferenceCheck]
    contrast: ContrastReport | None


def ingest(
    ficha: Ficha,
    connector: Connector,
    raw_store: RawStore,
    store: ObservationStore,
    *,
    contrast: ContrastRunner | None = None,
    allow_unapproved: bool = False,
    today: date | None = None,
) -> IngestResult:
    """Run one download of one series.

    Raises UnapprovedSeries (filter 1), ShapeError (filter 2) or
    ReferenceMismatch (filter 4); in those cases nothing is stored except the
    original files, which are always archived first as evidence.
    contrast: computes the filter 5 report from the parsed values. Without it,
    every value of a series that declares contrast sources stays PENDING.
    """
    if not ficha.is_approved and not allow_unapproved:
        raise UnapprovedSeries(f"{ficha.code}: {ficha.approval_problem}")
    if connector.channel != ficha.access_channel:
        raise ValueError(f"{ficha.code} uses {ficha.access_channel!r}, not {connector.channel!r}")
    today = today or datetime.now(UTC).date()

    raws = connector.fetch(ficha)
    refs = tuple(RawFileRef(r.name, r.url, r.sha256, raw_store.save(r)) for r in raws)
    parsed = connector.parse(raws, ficha)  # filter 2

    references = check_references(parsed.values, ficha)  # filter 4
    failures = [r for r in references if not r.passed]
    if failures:
        raise ReferenceMismatch(failures)

    previous = store.latest(ficha.code, include_quarantined=True)
    changes = detect_changes(parsed.values, previous, ficha, today)  # filter 6

    history = {key: obs.value for key, obs in previous.items()}
    history.update({(v.period, v.territory): v.value for v in parsed.values})
    plausibility = check_plausibility(  # filter 3
        parsed.values,
        ficha,
        new_indices=[] if not previous else changes.new + changes.changed,
        history=history,
    )
    report = contrast(parsed.values) if contrast and ficha.contrast_with else None  # filter 5

    download = Download(
        id=str(uuid.uuid4()),
        series_code=ficha.code,
        channel=connector.channel,
        downloaded_at=min(r.downloaded_at for r in raws),
        raw_files=refs,
        source_updated=parsed.source_updated,
    )
    stored = []
    unchanged = 0
    for i, value in enumerate(parsed.values):
        key = (value.period, value.territory)
        contrast_state = period_contrast(ficha, report, key)
        flags = plausibility[i] | changes.flags.get(i, set()) | flags_for(contrast_state)
        before = previous.get(key)
        if before is not None and before.value == value.value:
            flags |= before.flags & REVIEW_FLAGS
        observation = Observation(
            id=str(uuid.uuid4()),
            series_code=ficha.code,
            download_id=download.id,
            period=value.period,
            territory=value.territory,
            value=value.value,
            status=ObservationStatus.QUARANTINED if flags - NON_BLOCKING_FLAGS else ObservationStatus.ACCEPTED,
            contrast=contrast_state.status,
            contrast_level=contrast_state.level,
            flags=frozenset(flags),
            contrast_checks=contrast_state.checks,
        )
        # Same value and same validation state: nothing new to store.
        if key in previous and _same_state(previous[key], observation):
            unchanged += 1
            continue
        stored.append(observation)
    store.add(download, stored)
    return IngestResult(download, stored, unchanged, references, report)


def _same_state(old: Observation, new: Observation) -> bool:
    return (old.value, old.status, old.contrast, old.contrast_level, old.flags) == (
        new.value,
        new.status,
        new.contrast,
        new.contrast_level,
        new.flags,
    )
