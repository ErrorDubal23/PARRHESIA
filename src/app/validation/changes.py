"""Filter 6: watch for changes to values already stored."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.catalog import Ficha
from app.domain import Flag, Observation, ParsedValue, Period

Key = tuple[Period, str]


@dataclass
class ChangeReport:
    new: list[int] = field(default_factory=list)  # not stored before
    changed: list[int] = field(default_factory=list)  # stored with a different value
    unchanged: list[int] = field(default_factory=list)
    flags: dict[int, set[Flag]] = field(default_factory=dict)


def detect_changes(
    values: Sequence[ParsedValue], previous: Mapping[Key, Observation], ficha: Ficha, today: date
) -> ChangeReport:
    """A provisional value keeps its new version silently; a change to a final value raises an alert."""
    report = ChangeReport()
    for i, v in enumerate(values):
        stored = previous.get((v.period, v.territory))
        if stored is None:
            report.new.append(i)
        elif stored.value == v.value:
            report.unchanged.append(i)
        else:
            report.changed.append(i)
            if ficha.is_final(v.period, today):
                report.flags[i] = {Flag.HISTORY_CHANGED}
    return report
