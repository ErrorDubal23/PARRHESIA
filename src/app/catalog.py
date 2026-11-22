"""Series fichas (filter 1): load and validate catalog/series/*.yaml.

Approval is tied to the ficha's content: approval.content_sha256 must equal the
SHA-256 of the file text without its top-level approval block (comments
included). Any later edit outside that block voids the approval until a person
approves again. Print the hash to approve with:

    uv run python -m app.catalog <code>
"""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PrivateAttr

from app.domain import ContrastLevel, Period

CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog" / "series"

# From a column-0 "approval:" line up to the next column-0 line or the end of the file.
_APPROVAL_BLOCK = re.compile(r"^approval:.*?(?=^\S|\Z)", re.MULTILINE | re.DOTALL)

PeriodField = Annotated[Period, BeforeValidator(Period.parse)]


class _Model(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")


class History(_Model):
    first_period: PeriodField
    decimals: int | None  # None: the source publishes full precision and it is kept as is
    period_from_timestamp: str | None = None


class ExpectedGap(_Model):
    """Periods the source does not publish. A missing period listed here never alerts."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    periods: list[PeriodField] = Field(default_factory=list)
    range: tuple[PeriodField, PeriodField] | None = None  # inclusive
    except_months: list[int] = Field(default_factory=list)  # months inside the range that are published
    reason: str

    def covers(self, period: Period) -> bool:
        if period in self.periods:
            return True
        if self.range is None:
            return False
        start, end = self.range
        return start <= period <= end and period.month not in self.except_months


class Plausibility(_Model):
    # Strict: a misspelled rule must fail loudly instead of being ignored.
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    min: Decimal | None = None
    max: Decimal | None = None
    max_step: Decimal | None = None  # vs. the previous period
    max_step_yoy: Decimal | None = None  # vs. the same period one year earlier
    max_step_pct: Decimal | None = None  # relative change vs. the previous period, in %
    max_step_applies_to: Literal["new_observations"] = "new_observations"
    max_step_excluded_years: list[int] = Field(default_factory=list)
    must_increase: bool = False
    no_gaps: bool = True
    # With no_gaps false, listing the expected gaps still checks every other
    # missing period: anything not listed alerts.
    expected_gaps: list[ExpectedGap] = Field(default_factory=list)
    no_duplicates: bool = True

    def is_expected_gap(self, period: Period) -> bool:
        return any(gap.covers(period) for gap in self.expected_gaps)


class KnownException(_Model):
    periods: list[PeriodField]
    explanation: str


class ReferenceValue(_Model):
    period: PeriodField
    value: Decimal
    precision: int = Field(ge=0)
    published_by: str
    document: str

    @property
    def tolerance(self) -> Decimal:
        """Half a unit of the last published digit: no rounding rule is chosen."""
        return Decimal("0.5") * Decimal(10) ** -self.precision


class KnownVersionDifference(_Model):
    """A registered difference with a contrast source, with each side's exact value."""

    period: PeriodField
    level: ContrastLevel
    source: str
    source_value: Decimal
    series_value: Decimal


class Approval(_Model):
    status: Literal["pending", "approved", "rejected"]
    approved_by: str | None = None
    approved_on: Any = None
    content_sha256: str | None = None


class Ficha(_Model):
    code: str
    indicator: str
    variant: str
    name: str
    unit_label: str
    frequency: Literal["monthly", "annual"]
    geography: str
    producer: str
    access_channel: str
    external: dict[str, Any]
    history: History
    plausibility: Plausibility
    known_exceptions: list[KnownException] = Field(default_factory=list)
    reference_values: list[ReferenceValue] = Field(default_factory=list)
    contrast_with: list[str]  # required: an empty list means "no second source"
    known_version_differences: list[KnownVersionDifference] = Field(default_factory=list)
    status: str | None = None
    approval: Approval

    _content_sha256: str | None = PrivateAttr(default=None)

    @property
    def content_sha256(self) -> str | None:
        """Hash of the file this ficha was loaded from, without the approval block."""
        return self._content_sha256

    @property
    def approval_problem(self) -> str | None:
        """Why the ficha may not be connected, or None if its approval is valid."""
        if self.approval.status != "approved":
            return f"approval status is {self.approval.status!r}"
        if not self.approval.content_sha256:
            return "approved without content_sha256"
        if self.approval.content_sha256 != self.content_sha256:
            return "ficha changed after approval (content_sha256 does not match); approve again"
        return None

    @property
    def is_approved(self) -> bool:
        return self.approval_problem is None

    def is_final(self, period: Period, today: date) -> bool:
        """Whether a stored value for this period is final, so that a change raises filter 6.

        provisional_until_march_next_year: SIEDCO data "solo hasta marzo del siguiente
        año pasarán a ser definitivos". Treating a period as final from 1 April of
        the following year is the project's interpretation, not an official Policía
        rule (see docs/PROYECTO.md). Series without a provisional status are final
        on release.
        """
        if self.status == "provisional_until_march_next_year":
            return today >= date(period.year + 1, 4, 1)
        if self.status and self.status.startswith("provisional"):
            raise ValueError(f"{self.code}: unknown provisional status {self.status!r}")
        return True

    @property
    def exception_periods(self) -> frozenset[Period]:
        return frozenset(p for exc in self.known_exceptions for p in exc.periods)


def content_sha256(text: str) -> str:
    """SHA-256 of a ficha's text without its top-level approval block."""
    normalized = text.replace("\r\n", "\n")
    blocks = _APPROVAL_BLOCK.findall(normalized)
    if len(blocks) != 1:
        raise ValueError(f"expected one top-level approval block, found {len(blocks)}")
    return hashlib.sha256(_APPROVAL_BLOCK.sub("", normalized).encode("utf-8")).hexdigest()


def load_ficha(path: Path) -> Ficha:
    text = path.read_text(encoding="utf-8")
    ficha = Ficha.model_validate(yaml.safe_load(text))
    ficha._content_sha256 = content_sha256(text)
    return ficha


def load_ficha_by_code(code: str, catalog_dir: Path = CATALOG_DIR) -> Ficha:
    ficha = load_ficha(catalog_dir / f"{code}.yaml")
    if ficha.code != code:
        raise ValueError(f"{code}.yaml declares code {ficha.code!r}")
    return ficha


if __name__ == "__main__":
    for code in sys.argv[1:] or sorted(p.stem for p in CATALOG_DIR.glob("*.yaml")):
        path = CATALOG_DIR / f"{code}.yaml"
        print(f"{code}: {content_sha256(path.read_text(encoding='utf-8'))}")
