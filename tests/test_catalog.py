from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.catalog import CATALOG_DIR, Ficha, ReferenceValue, content_sha256, load_ficha_by_code
from app.domain import Period

CONNECTABLE = (
    "inflation_annual_national",
    "unemployment_rate_national",
    "minimum_wage_monthly",
    "homicides_intentional_national",
)


@pytest.mark.parametrize("code", CONNECTABLE)
def test_fichas_load(code):
    ficha = load_ficha_by_code(code)
    assert ficha.code == code
    assert ficha.reference_values


def test_reference_values_keep_published_text_exactly():
    ficha = load_ficha_by_code("unemployment_rate_national")
    refs = {str(r.period): r for r in ficha.reference_values}
    assert refs["2026-08"].value == Decimal("9.4")
    assert refs["2026-08"].precision == 1


def test_unemployment_rules():
    rules = load_ficha_by_code("unemployment_rate_national").plausibility
    assert rules.max_step is None
    assert rules.max_step_yoy == Decimal("4.0")
    assert rules.max_step_excluded_years == [2021]


def test_known_exceptions_are_periods():
    ficha = load_ficha_by_code("unemployment_rate_national")
    assert Period(2020, 5) in ficha.exception_periods


def test_minimum_wage_has_no_second_source():
    assert load_ficha_by_code("minimum_wage_monthly").contrast_with == []


@pytest.mark.parametrize(("precision", "tolerance"), [(0, "0.5"), (1, "0.05"), (2, "0.005")])
def test_tolerance_is_half_the_last_published_digit(precision, tolerance):
    ref = ReferenceValue(period="2026", value="1", precision=precision, published_by="x", document="x")
    assert ref.tolerance == Decimal(tolerance)


# Filter 1: approval is tied to content_sha256 (file text without the approval block)

WAGE_TEXT = (CATALOG_DIR / "minimum_wage_monthly.yaml").read_text(encoding="utf-8")


def test_hash_ignores_the_approval_block():
    body = WAGE_TEXT[: WAGE_TEXT.index("\napproval:") + 1]
    pending = body + "approval:\n  status: pending\n  approved_by:\n  approved_on:\n"
    approved = body + "approval:\n  status: approved\n  approved_by: Alguien\n  content_sha256: abc\n"
    assert content_sha256(pending) == content_sha256(approved) == content_sha256(WAGE_TEXT)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("min: 0", "min: 1"),  # a rule
        ("# Ningún año de la serie", "# Ningun año de la serie"),  # comments count too
        ("1750905", "1750906"),  # a reference value
    ],
)
def test_hash_changes_with_any_other_edit(old, new):
    assert old in WAGE_TEXT
    assert content_sha256(WAGE_TEXT.replace(old, new, 1)) != content_sha256(WAGE_TEXT)


def test_hash_ignores_line_endings():
    assert content_sha256(WAGE_TEXT.replace("\n", "\r\n")) == content_sha256(WAGE_TEXT)


def test_hash_requires_exactly_one_approval_block():
    with pytest.raises(ValueError):
        content_sha256(WAGE_TEXT.replace("\napproval:", "\nnot_approval:"))
    with pytest.raises(ValueError):
        content_sha256(WAGE_TEXT + "approval:\n  status: pending\n")


def test_loaded_ficha_carries_its_hash():
    assert load_ficha_by_code("minimum_wage_monthly").content_sha256 == content_sha256(WAGE_TEXT)


def test_misspelled_plausibility_rule_fails():
    data = load_ficha_by_code("minimum_wage_monthly").model_dump()
    data["plausibility"]["max_stpe"] = 1
    with pytest.raises(ValidationError):
        Ficha.model_validate(data)


def test_contrast_with_is_required():
    data = load_ficha_by_code("minimum_wage_monthly").model_dump()
    del data["contrast_with"]
    with pytest.raises(ValidationError):
        Ficha.model_validate(data)
