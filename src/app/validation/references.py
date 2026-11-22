"""Filter 4: compare against officially published reference values."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.catalog import Ficha, ReferenceValue
from app.domain import ParsedValue


@dataclass(frozen=True)
class ReferenceCheck:
    reference: ReferenceValue
    actual: tuple[Decimal | None, ...]  # every value the download has for that period
    passed: bool

    def describe(self) -> str:
        ref = self.reference
        return f"{ref.period}: expected {ref.value} ±{ref.tolerance} ({ref.document.strip()}), got {list(self.actual)}"


class ReferenceMismatch(Exception):
    """The connector fails: a reference value does not match."""

    def __init__(self, failures: Sequence[ReferenceCheck]) -> None:
        self.failures = list(failures)
        super().__init__("; ".join(f.describe() for f in self.failures))


def check_references(values: Sequence[ParsedValue], ficha: Ficha) -> list[ReferenceCheck]:
    """A value passes if |value - reference| <= 0.5 x 10^(-precision). No rounding rule is applied."""
    checks = []
    for ref in ficha.reference_values:
        actual = tuple(v.value for v in values if v.period == ref.period and v.territory == ficha.geography)
        passed = bool(actual) and all(a is not None and abs(a - ref.value) <= ref.tolerance for a in actual)
        checks.append(ReferenceCheck(reference=ref, actual=actual, passed=passed))
    return checks
