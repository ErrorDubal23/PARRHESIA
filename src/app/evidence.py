"""Evidence of archived source files: manifest (hashes and metadata, kept in git) and page-link discovery.

Original files go to the raw store (data/, not in git); the manifest records
every download with its URL, date, sha256, size and HTTP Last-Modified.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from app.connectors.base import ShapeError

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence"

_FILE_LINK = re.compile(r'<a\b[^>]*href="([^"]+\.(?:xlsx?|zip|pdf))"[^>]*>(.*?)</a>', re.I | re.S)


@dataclass(frozen=True)
class EvidenceRecord:
    source: str
    url: str
    downloaded_at: str  # ISO 8601, UTC
    sha256: str
    size: int
    location: str  # in the raw store
    changed: bool  # sha256 differs from the previous version (or first version)
    last_modified: str | None = None  # HTTP Last-Modified, when the server sends it


class EvidenceManifest:
    """Append-only JSON Lines file: one line per download of a source file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def records(self) -> list[EvidenceRecord]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [EvidenceRecord(**json.loads(line)) for line in lines if line.strip()]

    def latest(self, source: str) -> EvidenceRecord | None:
        matches = [r for r in self.records() if r.source == source]
        return matches[-1] if matches else None

    def latest_by_source(self) -> dict[str, EvidenceRecord]:
        latest: dict[str, EvidenceRecord] = {}
        for record in self.records():
            latest[record.source] = record
        return latest

    def append(self, record: EvidenceRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")


def file_links(page_html: str, base_url: str) -> list[tuple[str, str]]:
    """(link text, absolute URL) for every file link (.xlsx, .xls, .zip, .pdf) on a page, in page order."""
    links = []
    for match in _FILE_LINK.finditer(page_html):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(match.group(2)))).strip()
        links.append((text, urljoin(base_url, html.unescape(match.group(1)))))
    return links


def page_links(page_html: str, base_url: str) -> dict[str, str]:
    """Map link text -> absolute URL; two file links with the same text stop the read."""
    links: dict[str, str] = {}
    for text, url in file_links(page_html, base_url):
        if text in links:
            raise ShapeError(f"two file links with the same text {text!r}")
        links[text] = url
    return links


def same_month(a: datetime, b: datetime) -> bool:
    return (a.year, a.month) == (b.year, b.month)


def url_suffix(url: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", url.split("?")[0])
    return match.group(1).lower() if match else ".bin"
