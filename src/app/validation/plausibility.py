"""Filter 3: plausible values. Anything odd goes to quarantine; nothing is rejected."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from decimal import Decimal

from app.catalog import Ficha
from app.domain import Flag, ParsedValue, Period

Key = tuple[Period, str]


def check_plausibility(
    values: Sequence[ParsedValue],
    ficha: Ficha,
    *,
    new_indices: Collection[int],
    history: Mapping[Key, Decimal | None],
) -> list[set[Flag]]:
    """Return the flags for each value, in the same order.

    new_indices: values that are new or changed in this download. Only these go
    through the jump checks; the initial load of the history does not.
    history: the best known value for each key (stored values updated with this
    download), used as the comparison point for jumps.
    """
    rules = ficha.plausibility
    flags: list[set[Flag]] = [set() for _ in values]

    by_key: dict[Key, list[int]] = defaultdict(list)
    for i, v in enumerate(values):
        by_key[(v.period, v.territory)].append(i)

    for i, v in enumerate(values):
        if v.value is None:
            flags[i].add(Flag.MISSING_VALUE)
        elif (rules.min is not None and v.value < rules.min) or (rules.max is not None and v.value > rules.max):
            flags[i].add(Flag.OUT_OF_RANGE)

    if rules.no_duplicates:
        for indices in by_key.values():
            if len(indices) > 1:
                for i in indices:
                    flags[i].add(Flag.DUPLICATE)

    if rules.no_gaps or rules.expected_gaps:
        first_index = {key: indices[0] for key, indices in by_key.items()}
        periods_by_territory: dict[str, list[Period]] = defaultdict(list)
        for period, territory in by_key:
            periods_by_territory[territory].append(period)
        for territory, periods in periods_by_territory.items():
            periods.sort()
            for before, after in zip(periods, periods[1:]):
                missing = before.next()
                while missing != after:
                    if not rules.is_expected_gap(missing):
                        flags[first_index[(after, territory)]].add(Flag.GAP_BEFORE)
                        break
                    missing = missing.next()

    exceptions = ficha.exception_periods
    excluded_years = set(rules.max_step_excluded_years)
    for i in new_indices:
        v = values[i]
        if v.value is None or v.period in exceptions or v.period.year in excluded_years:
            continue
        if _jumps(v, rules, history):
            flags[i].add(Flag.JUMP)

    if rules.must_increase:
        for i, v in enumerate(values):
            before = history.get((v.period.previous(), v.territory))
            if v.value is not None and before is not None and v.value <= before:
                flags[i].add(Flag.NOT_INCREASING)

    return flags


def _jumps(v: ParsedValue, rules, history: Mapping[Key, Decimal | None]) -> bool:
    """Strictly greater than the threshold counts as a jump."""
    previous = history.get((v.period.previous(), v.territory))
    year_ago = history.get((v.period.year_ago(), v.territory))
    if rules.max_step is not None and previous is not None and abs(v.value - previous) > rules.max_step:
        return True
    if rules.max_step_yoy is not None and year_ago is not None and abs(v.value - year_ago) > rules.max_step_yoy:
        return True
    if rules.max_step_pct is not None and previous:
        if abs(v.value - previous) / abs(previous) * 100 > rules.max_step_pct:
            return True
    return False
