"""Banco de la República SUAMECA connector (undocumented JSON API behind the SUAMECA site).

The official SDMX service does not carry these indicators (see docs/PROYECTO.md).
Because this API is undocumented, parse() checks every field it relies on and
raises ShapeError on any change instead of guessing.
"""

from __future__ import annotations

import calendar
import json
import ssl
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import certifi
import httpx

from app.catalog import Ficha
from app.connectors.base import Parsed, ShapeError
from app.domain import ParsedValue, Period, RawDownload

SUAMECA_HOST = "suameca.banrep.gov.co"
BASE_URL = (
    f"https://{SUAMECA_HOST}/estadisticas-economicas-back/rest/"
    "estadisticaEconomicaRestService/consultaMenuXId"
)
REFERER = "https://suameca.banrep.gov.co/estadisticas-economicas/"

# SUAMECA stamps each observation at midnight Bogotá time. Colombia uses UTC-5,
# except for the 1992-1993 daylight saving period (UTC-4). The server's end date
# for that period differs from tzdata, so both offsets are accepted for those
# two years instead of relying on a timezone database.
BOGOTA = timezone(timedelta(hours=-5))
BOGOTA_DST = timezone(timedelta(hours=-4))
DST_YEARS = (1992, 1993)

# The server does not send the intermediate certificate that links its leaf to
# DigiCert Global Root G2. We add that intermediate (downloaded from
# cacerts.digicert.com and verified against the root on 25 Oct 2026) to the
# trust store of requests to SUAMECA_HOST only. Verification stays fully on; it
# only gets the missing link. The live health check warns 90 days before expiry.
INTERMEDIATE_CERT = Path(__file__).parent / "certs" / "geotrust_ev_rsa_ca_g2.pem"
INTERMEDIATE_CERT_SHA256 = "2d140f20b8a96e2b4d2f1cc5aca5e5a1e7dc56a7491e510906960f38d2d21aef"

FREQUENCY_LABELS = {"monthly": "Mensual", "annual": "Anual"}
REQUIRED_SERIES_FIELDS = ("id", "nombre", "unidad", "descripcionPeriodicidad", "fuente", "fechaUltimoCargue", "data")


class SuamecaConnector:
    channel = "banrep_suameca"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or default_client()

    def fetch(self, ficha: Ficha) -> list[RawDownload]:
        response = self._client.get(
            BASE_URL,
            params={"idMenu": ficha.external["menu_id"]},
            headers={"Referer": REFERER},
        )
        response.raise_for_status()
        return [
            RawDownload(
                channel=self.channel,
                name="menu",
                url=str(response.url),
                content=response.content,
                downloaded_at=datetime.now(UTC),
                suffix=".json",
            )
        ]

    def parse(self, raws: Sequence[RawDownload], ficha: Ficha) -> Parsed:
        [raw] = raws
        if not raw.content.strip():
            # The server's proxy answers some rejected requests with 200 and an empty body.
            raise ShapeError("empty response")
        try:
            document = json.loads(raw.content, parse_float=Decimal)
        except ValueError as exc:
            raise ShapeError(f"response is not JSON: {exc}") from exc

        series_list = document.get("SERIES") if isinstance(document, dict) else None
        if not isinstance(series_list, list) or not all(isinstance(s, dict) for s in series_list):
            raise ShapeError("missing or malformed SERIES list")

        series_id = ficha.external["series_id"]
        allowed = {series_id, *ficha.external.get("ignore_series_ids", [])}
        unexpected = {s.get("id") for s in series_list} - allowed
        if unexpected:
            raise ShapeError(f"menu returned unexpected series {sorted(map(str, unexpected))}")

        matches = [s for s in series_list if s.get("id") == series_id]
        if len(matches) != 1:
            raise ShapeError(f"expected exactly one series {series_id}, found {len(matches)}")
        series = matches[0]

        missing = [f for f in REQUIRED_SERIES_FIELDS if f not in series]
        if missing:
            raise ShapeError(f"series {series_id} is missing fields {missing}")
        _expect(series, "nombre", ficha.external["series_name"])
        _expect(series, "unidad", ficha.unit_label)
        _expect(series, "descripcionPeriodicidad", FREQUENCY_LABELS[ficha.frequency])

        to_period = _period_rule(ficha.history.period_from_timestamp)
        data = series["data"]
        if not isinstance(data, list):
            raise ShapeError("data is not a list")
        values = [
            ParsedValue(period=to_period(_timestamp(point)), territory=ficha.geography, value=_value(point))
            for point in data
        ]
        return Parsed(values=values, source_updated=series["fechaUltimoCargue"])


def default_client() -> httpx.Client:
    """The bundled intermediate is mounted for SUAMECA_HOST only; any other host uses
    the standard trust store. Redirects are not followed (a redirect fails the fetch)."""
    return httpx.Client(
        timeout=60.0,
        follow_redirects=False,
        mounts={f"https://{SUAMECA_HOST}": httpx.HTTPTransport(verify=_suameca_ssl_context())},
    )


def _suameca_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=INTERMEDIATE_CERT)
    return context


def _expect(series: dict, field: str, expected: object) -> None:
    if series[field] != expected:
        raise ShapeError(f"{field} is {series[field]!r}, ficha expects {expected!r}")


def _timestamp(point: object) -> datetime:
    if not isinstance(point, list) or len(point) != 2:
        raise ShapeError(f"data point is not [timestamp, value]: {point!r}")
    ms = point[0]
    if not isinstance(ms, int) or isinstance(ms, bool):
        raise ShapeError(f"timestamp is not an integer: {ms!r}")
    stamp = datetime.fromtimestamp(ms / 1000, tz=BOGOTA)
    if _is_midnight(stamp):
        return stamp
    dst_stamp = datetime.fromtimestamp(ms / 1000, tz=BOGOTA_DST)
    if _is_midnight(dst_stamp) and dst_stamp.year in DST_YEARS:
        return dst_stamp
    raise ShapeError(f"timestamp is not midnight in Bogotá: {stamp.isoformat()}")


def _is_midnight(stamp: datetime) -> bool:
    return (stamp.hour, stamp.minute, stamp.second, stamp.microsecond) == (0, 0, 0, 0)


def _value(point: list) -> Decimal | None:
    value = point[1]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ShapeError(f"value is not a number: {value!r}")
    return Decimal(value)


def _period_rule(rule: str | None):
    if rule == "last_day_of_month_bogota":
        return _month_from_last_day
    if rule == "year_of_timestamp":
        return _year_from_december_31
    raise ValueError(f"ficha has no supported history.period_from_timestamp: {rule!r}")


def _month_from_last_day(stamp: datetime) -> Period:
    if stamp.day != calendar.monthrange(stamp.year, stamp.month)[1]:
        raise ShapeError(f"monthly timestamp is not the last day of the month: {stamp.date()}")
    return Period(stamp.year, stamp.month)


def _year_from_december_31(stamp: datetime) -> Period:
    if (stamp.month, stamp.day) != (12, 31):
        raise ShapeError(f"annual timestamp is not 31 December: {stamp.date()}")
    return Period(stamp.year)
