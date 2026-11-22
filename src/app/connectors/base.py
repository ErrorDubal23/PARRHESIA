"""Common connector interface. Each source implements fetch and parse; the pipeline does the rest."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.catalog import Ficha
from app.domain import ParsedValue, RawDownload


class ShapeError(Exception):
    """Filter 2: the source changed its format. The download stops."""


@dataclass(frozen=True)
class Parsed:
    values: list[ParsedValue]
    source_updated: str | None = None


class Connector(Protocol):
    channel: str  # matches Ficha.access_channel

    def fetch(self, ficha: Ficha) -> list[RawDownload]:
        """Download the original files (one or more). No parsing here."""
        ...

    def parse(self, raws: Sequence[RawDownload], ficha: Ficha) -> Parsed:
        """Read the values, checking the shape as it goes (filter 2). Raises ShapeError."""
        ...
