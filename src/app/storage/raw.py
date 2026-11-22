"""Archive of original downloads: every file as received, addressed by its hash."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.domain import RawDownload


class RawStore(Protocol):
    def save(self, raw: RawDownload) -> str:
        """Archive the bytes and return where they live."""
        ...

    def load(self, location: str) -> bytes: ...


class FilesystemRawStore:
    """Writes each download once under <root>/<channel>/; never overwrites."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, raw: RawDownload) -> str:
        directory = self.root / raw.channel
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{raw.downloaded_at:%Y%m%dT%H%M%SZ}_{raw.sha256[:16]}{raw.suffix}"
        path = directory / name
        if path.exists():
            if path.read_bytes() != raw.content:
                raise FileExistsError(f"{path} exists with different content")
        else:
            with path.open("xb") as fh:
                fh.write(raw.content)
        return str(path.relative_to(self.root))

    def load(self, location: str) -> bytes:
        return (self.root / location).read_bytes()
