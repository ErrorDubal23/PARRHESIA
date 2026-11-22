"""Core data types shared by catalog, connectors, validation and storage."""

from __future__ import annotations

import calendar
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from functools import total_ordering

_PERIOD_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


@total_ordering
@dataclass(frozen=True)
class Period:
    """A year (2026), a month (2026-08) or a day (2026-02-12)."""

    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if self.day is not None and self.month is None:
            raise ValueError("a day period needs a month")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError(f"invalid month: {self.month}")
        if self.day is not None:
            date(self.year, self.month, self.day)  # raises on an invalid day

    @classmethod
    def parse(cls, value: object) -> Period:
        """Accept a Period, a date, an int year or a 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' string."""
        if isinstance(value, Period):
            return value
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return cls(value.year, value.month, value.day)
        if isinstance(value, int) and not isinstance(value, bool):
            return cls(value)
        if isinstance(value, str):
            match = _PERIOD_RE.match(value.strip())
            if match:
                year, month, day = match.groups()
                return cls(int(year), int(month) if month else None, int(day) if day else None)
        raise ValueError(f"not a period: {value!r}")

    @property
    def granularity(self) -> str:
        if self.day is not None:
            return "day"
        return "month" if self.month is not None else "year"

    def previous(self) -> Period:
        """The period right before this one, at the same granularity."""
        if self.day is not None:
            d = date.fromordinal(date(self.year, self.month, self.day).toordinal() - 1)
            return Period(d.year, d.month, d.day)
        if self.month is not None:
            return Period(self.year - 1, 12) if self.month == 1 else Period(self.year, self.month - 1)
        return Period(self.year - 1)

    def next(self) -> Period:
        """The period right after this one, at the same granularity."""
        if self.day is not None:
            d = date.fromordinal(date(self.year, self.month, self.day).toordinal() + 1)
            return Period(d.year, d.month, d.day)
        if self.month is not None:
            return Period(self.year + 1, 1) if self.month == 12 else Period(self.year, self.month + 1)
        return Period(self.year + 1)

    def year_ago(self) -> Period:
        """The same period one year earlier (29 Feb maps to 28 Feb)."""
        if self.day is not None:
            last_day = calendar.monthrange(self.year - 1, self.month)[1]
            return Period(self.year - 1, self.month, min(self.day, last_day))
        return Period(self.year - 1, self.month)

    def _key(self) -> tuple[int, int, int]:
        return (self.year, self.month or 0, self.day or 0)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self._key() < other._key()

    def __str__(self) -> str:
        if self.day is not None:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.month is not None:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"


class Flag(StrEnum):
    """Why an observation is (or is not) held in quarantine."""

    MISSING_VALUE = "missing_value"  # filter 3
    OUT_OF_RANGE = "out_of_range"  # filter 3
    GAP_BEFORE = "gap_before"  # filter 3: the period before this one is missing
    DUPLICATE = "duplicate"  # filter 3
    JUMP = "jump"  # filter 3
    NOT_INCREASING = "not_increasing"  # filter 3
    CONTRAST_PENDING = "contrast_pending"  # filter 5: contrast source not connected yet
    CONTRAST_MISMATCH = "contrast_mismatch"  # filter 5
    NO_SECOND_SOURCE = "no_second_source"  # filter 5 does not apply; informative only
    CONTRAST_UNAVAILABLE = "contrast_unavailable"  # filter 5: no published source for the period; shown to users
    KNOWN_VERSION_DIFFERENCE = "known_version_difference"  # filter 5: registered difference; informative
    # filter 5: the producer's value differs from the channel's and is used anyway;
    # mandatory human review (it does not block, but it is never dropped silently)
    PRODUCER_VALUE_USED = "producer_value_used"
    HISTORY_CHANGED = "history_changed"  # filter 6: a final value changed


NON_BLOCKING_FLAGS = frozenset(
    {Flag.NO_SECOND_SOURCE, Flag.CONTRAST_UNAVAILABLE, Flag.KNOWN_VERSION_DIFFERENCE, Flag.PRODUCER_VALUE_USED}
)

# Flags that open an alert for human review. CONTRAST_PENDING does not: it clears
# by itself when the contrast runs. Informative flags (no second source,
# unavailable, registered difference) do not either.
ALERT_FLAGS = frozenset(
    {
        Flag.MISSING_VALUE,
        Flag.OUT_OF_RANGE,
        Flag.GAP_BEFORE,
        Flag.DUPLICATE,
        Flag.JUMP,
        Flag.NOT_INCREASING,
        Flag.CONTRAST_MISMATCH,
        Flag.HISTORY_CHANGED,
        Flag.PRODUCER_VALUE_USED,  # does not block, but is never dropped silently
    }
)


class ObservationStatus(StrEnum):
    QUARANTINED = "quarantined"
    ACCEPTED = "accepted"


class ContrastStatus(StrEnum):
    """Filter 5 outcome, stored explicitly on every observation."""

    PASSED = "passed"  # every expected contrast was run and matched (or differs as registered)
    PENDING = "pending"  # a contrast source exists but has not been run
    NOT_APPLICABLE = "not_applicable"  # single official source (e.g. the minimum wage decree)
    UNAVAILABLE = "unavailable"  # no published contrast source for this period
    FAILED = "failed"  # a contrast was run and did not match


class ContrastLevel(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"  # does not validate the monthly distribution


@dataclass(frozen=True)
class RawDownload:
    """One original file a connector received, before any parsing."""

    channel: str
    name: str  # role of the file in the download, e.g. "menu", "metadata", "rows"
    url: str
    content: bytes
    downloaded_at: datetime
    suffix: str = ".bin"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class RawFileRef:
    name: str
    url: str
    sha256: str
    location: str


@dataclass(frozen=True)
class ParsedValue:
    period: Period
    territory: str
    value: Decimal | None


@dataclass(frozen=True)
class Download:
    id: str
    series_code: str
    channel: str
    downloaded_at: datetime
    raw_files: tuple[RawFileRef, ...]
    source_updated: str | None  # as the source states it, e.g. "08 de octubre de 2026"


@dataclass(frozen=True)
class ContrastCheck:
    """One comparison behind an observation's contrast status (stored in contrast_check)."""

    source: str
    level: ContrastLevel
    compared_period: Period  # the month, or the year for annual checks
    source_value: Decimal | None  # None when the check could not run
    series_value: Decimal | None
    tolerance: Decimal
    outcome: str  # passed, pending or failed
    known_difference: bool = False


@dataclass(frozen=True)
class Observation:
    id: str
    series_code: str
    download_id: str
    period: Period
    territory: str
    value: Decimal | None
    status: ObservationStatus
    contrast: ContrastStatus
    contrast_level: ContrastLevel | None = None
    flags: frozenset[Flag] = field(default_factory=frozenset)
    contrast_checks: tuple[ContrastCheck, ...] = ()
