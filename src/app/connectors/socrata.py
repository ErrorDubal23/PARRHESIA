"""datos.gov.co (Socrata) connector for SIEDCO datasets published by MinDefensa.

A download is two original files: the dataset metadata (columns, types,
rowsUpdatedAt) and the full CSV export. Values are aggregated locally with the
ficha's rule, so the archived CSV is the evidence for every total.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.catalog import Ficha
from app.connectors.base import Parsed, ShapeError
from app.domain import ParsedValue, Period, RawDownload

TOKEN_ENV = "SOCRATA_APP_TOKEN"
_MONTH_GROUP = re.compile(r"^month\((\w+)\)$")


@dataclass(frozen=True)
class Column:
    field: str
    type: str
    name: str  # display name, used as the CSV header


@dataclass(frozen=True)
class DatasetMetadata:
    rows_updated_at: datetime
    columns: tuple[Column, ...]


class SocrataConnector:
    channel = "mindefensa_datos_gov_co"

    def __init__(self, client: httpx.Client | None = None, token: str | None = None) -> None:
        self._client = client or httpx.Client(timeout=300.0, follow_redirects=False)
        self._token = token if token is not None else os.environ.get(TOKEN_ENV) or None

    def fetch_metadata(self, ficha: Ficha) -> RawDownload:
        ext = ficha.external
        return self._get(f"https://{ext['domain']}/api/views/{ext['dataset_id']}.json", "metadata", ".json")

    def fetch(self, ficha: Ficha) -> list[RawDownload]:
        ext = ficha.external
        rows_url = f"https://{ext['domain']}/api/views/{ext['dataset_id']}/rows.csv?accessType=DOWNLOAD"
        return [self.fetch_metadata(ficha), self._get(rows_url, "rows", ".csv")]

    def parse(self, raws: Sequence[RawDownload], ficha: Ficha) -> Parsed:
        by_name = {r.name: r for r in raws}
        if set(by_name) != {"metadata", "rows"}:
            raise ShapeError(f"expected metadata and rows files, got {sorted(by_name)}")
        metadata = read_metadata(by_name["metadata"].content)
        check_columns(metadata, ficha)
        values = aggregate(by_name["rows"].content, metadata, ficha)
        return Parsed(values=values, source_updated=metadata.rows_updated_at.isoformat())

    def _get(self, url: str, name: str, suffix: str) -> RawDownload:
        headers = {"X-App-Token": self._token} if self._token else {}
        response = self._client.get(url, headers=headers)
        response.raise_for_status()
        return RawDownload(
            channel=self.channel,
            name=name,
            url=url,
            content=response.content,
            downloaded_at=datetime.now(UTC),
            suffix=suffix,
        )


def read_metadata(content: bytes) -> DatasetMetadata:
    try:
        doc = json.loads(content)
        updated = doc["rowsUpdatedAt"]
        columns = tuple(Column(c["fieldName"], c["dataTypeName"], c["name"]) for c in doc["columns"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ShapeError(f"unexpected dataset metadata: {exc!r}") from exc
    if not isinstance(updated, int) or isinstance(updated, bool):
        raise ShapeError(f"rowsUpdatedAt is not a timestamp: {updated!r}")
    return DatasetMetadata(rows_updated_at=datetime.fromtimestamp(updated, UTC), columns=columns)


def check_columns(metadata: DatasetMetadata, ficha: Ficha) -> None:
    """Filter 2: same fields, same types, same order as the ficha."""
    expected = list(ficha.external["expected_fields"].items())
    actual = [(c.field, c.type) for c in metadata.columns]
    if actual != expected:
        raise ShapeError(f"dataset columns changed: expected {expected}, got {actual}")


def aggregate(content: bytes, metadata: DatasetMetadata, ficha: Ficha) -> list[ParsedValue]:
    """Sum the count field of the included rows, by month of the date field."""
    rule = ficha.external["aggregation"]
    match = _MONTH_GROUP.match(rule["group_by"])
    if not match:
        raise ValueError(f"unsupported group_by {rule['group_by']!r}")
    date_field, sum_field = match.group(1), rule["sum_field"]
    include = {field: set(allowed) for field, allowed in rule["include_only"].items()}
    expected_categories = {field: set(v) for field, v in ficha.external.get("expected_categories", {}).items()}

    reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    header = next(reader, None)
    names = [c.name for c in metadata.columns]
    if header != names:
        raise ShapeError(f"CSV header {header} does not match the metadata column names {names}")
    index = {c.field: i for i, c in enumerate(metadata.columns)}

    totals: Counter[Period] = Counter()
    for line_number, row in enumerate(reader, start=2):
        if len(row) != len(names):
            raise ShapeError(f"line {line_number}: {len(row)} fields, expected {len(names)}")
        for field, allowed in expected_categories.items():
            if row[index[field]] not in allowed:
                raise ShapeError(f"line {line_number}: new {field} value {row[index[field]]!r}")
        if not all(row[index[field]] in allowed for field, allowed in include.items()):
            continue
        day = _csv_date(row[index[date_field]], line_number)
        quantity = row[index[sum_field]]
        if not quantity.isdigit() or int(quantity) <= 0:
            raise ShapeError(f"line {line_number}: invalid {sum_field} {quantity!r}")
        totals[Period(day.year, day.month)] += int(quantity)

    return [ParsedValue(period, ficha.geography, Decimal(total)) for period, total in sorted(totals.items())]


def _csv_date(text: str, line_number: int) -> datetime:
    try:
        return datetime.strptime(text, "%d/%m/%Y")
    except ValueError as exc:
        raise ShapeError(f"line {line_number}: unreadable date {text!r}") from exc
