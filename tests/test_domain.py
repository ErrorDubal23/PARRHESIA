from datetime import date

import pytest

from app.domain import Period


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026", Period(2026)),
        (2026, Period(2026)),
        ("2026-08", Period(2026, 8)),
        ("2026-02-12", Period(2026, 2, 12)),
        (date(2026, 2, 12), Period(2026, 2, 12)),
    ],
)
def test_parse_accepts_year_month_and_day(raw, expected):
    assert Period.parse(raw) == expected


@pytest.mark.parametrize("raw", ["2026-13", "2026-02-30", "26-08", "agosto 2026", True, None])
def test_parse_rejects_invalid(raw):
    with pytest.raises(ValueError):
        Period.parse(raw)


def test_str_round_trips():
    for text in ("2026", "2026-08", "2026-02-12"):
        assert str(Period.parse(text)) == text


def test_previous_next_and_year_ago():
    assert Period(2026, 1).previous() == Period(2025, 12)
    assert Period(2025, 12).next() == Period(2026, 1)
    assert Period(2026).previous() == Period(2025)
    assert Period(2026, 3, 1).previous() == Period(2026, 2, 28)
    assert Period(2026, 8).year_ago() == Period(2025, 8)
    assert Period(2024, 2, 29).year_ago() == Period(2023, 2, 28)


def test_ordering():
    assert sorted([Period(2026, 2), Period(2025, 12), Period(2026, 1)]) == [
        Period(2025, 12),
        Period(2026, 1),
        Period(2026, 2),
    ]
