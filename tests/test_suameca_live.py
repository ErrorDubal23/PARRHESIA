"""Live SUAMECA checks against the real API. Also the daily connector health check.

Run with: uv run pytest -m live
"""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509

from app.connectors.suameca import INTERMEDIATE_CERT, SuamecaConnector
from app.pipeline import ingest
from app.storage.observations import InMemoryObservationStore
from app.storage.raw import FilesystemRawStore
from tests.conftest import SUAMECA_CODES

pytestmark = pytest.mark.live

CERT_WARNING_DAYS = 90


@pytest.mark.parametrize("code", SUAMECA_CODES)
def test_live_download_passes_filters_2_and_4(ficha, tmp_path, code):
    # Nothing is persisted (temporary directory and in-memory store), so this
    # health check may run before the fichas are approved.
    result = ingest(
        ficha(code),
        SuamecaConnector(),
        FilesystemRawStore(tmp_path),
        InMemoryObservationStore(),
        allow_unapproved=True,
    )
    assert result.stored
    assert all(check.passed for check in result.references)


def test_bundled_intermediate_is_not_about_to_expire():
    cert = x509.load_pem_x509_certificate(INTERMEDIATE_CERT.read_bytes())
    remaining = cert.not_valid_after_utc - datetime.now(UTC)
    assert remaining > timedelta(days=CERT_WARNING_DAYS), (
        f"{INTERMEDIATE_CERT.name} expires on {cert.not_valid_after_utc:%Y-%m-%d} "
        f"({remaining.days} days left): download the new intermediate from "
        "cacerts.digicert.com, verify it against DigiCert Global Root G2 and update "
        "INTERMEDIATE_CERT_SHA256"
    )
