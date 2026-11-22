"""Daily health check for the DANE publications (live). Run with: uv run pytest -m live

Only the pages and HTTP headers are checked here; downloads happen in
`python -m app.runs dane` (new URL, or once a month with If-Modified-Since).
"""

import httpx
import pytest

from app.connectors.dane_archive import DaneArchive, load_dane_config
from app.evidence import EvidenceManifest
from app.storage.raw import FilesystemRawStore

pytestmark = pytest.mark.live


def test_every_dane_file_is_still_linked_and_sends_last_modified(tmp_path):
    archive = DaneArchive(load_dane_config(), FilesystemRawStore(tmp_path), EvidenceManifest(tmp_path / "m.jsonl"))
    targets = dict(archive.targets())
    assert "dane_ipc_variations_annex" in targets and "dane_geih_annex" in targets
    bulletins = [k for k in targets if k.startswith("dane_ipc_bulletin/")]
    assert len(bulletins) >= 45  # 2023-01 to 2026-09 at least
    client = httpx.Client(timeout=60.0, headers={"User-Agent": "Mozilla/5.0"})
    for key in ("dane_ipc_variations_annex", "dane_geih_annex"):
        response = client.head(targets[key])
        assert response.status_code == 200, key
        assert response.headers.get("Last-Modified"), key
