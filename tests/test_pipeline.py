"""End-to-end ingestion with saved SUAMECA responses: filters 1, 3, 5, 6 and quarantine."""

import calendar
import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.catalog import CATALOG_DIR as FICHA_DIR
from app.catalog import Approval, load_ficha
from app.connectors.base import ShapeError
from app.domain import ContrastLevel, ContrastStatus, Flag, ObservationStatus, Period
from app.pipeline import UnapprovedSeries, ingest
from app.validation.contrast import PeriodContrast
from app.validation.references import ReferenceMismatch
from tests.conftest import FIXTURES, approved, fixture_document, target_series

BOGOTA_UTC_OFFSET_HOURS = 5


def _stamp(period: Period) -> int:
    """SUAMECA timestamp for a month: its last day at midnight Bogotá (UTC-5)."""
    day = calendar.monthrange(period.year, period.month)[1]
    return int(datetime(period.year, period.month, day, BOGOTA_UTC_OFFSET_HOURS, tzinfo=UTC).timestamp() * 1000)


def _month(timestamp_ms: int) -> Period:
    d = datetime.fromtimestamp(timestamp_ms / 1000 - BOGOTA_UTC_OFFSET_HOURS * 3600, UTC)
    return Period(d.year, d.month)


def _values(series: dict) -> dict[Period, Decimal]:
    return {_month(t): v for t, v in series["data"]}


def _run(ficha, connector, raw_store, store, code, **kwargs):
    return ingest(ficha(code), connector, raw_store, store, allow_unapproved=True, **kwargs)


def _add_month(fake_suameca, menu_id, series_id, period, value):
    doc = fixture_document(menu_id)
    target_series(doc, series_id)["data"].append([_stamp(period), value])
    fake_suameca.set(menu_id, doc)


def _set_value(fake_suameca, menu_id, series_id, period, value):
    doc = fixture_document(menu_id)
    for point in target_series(doc, series_id)["data"]:
        if _month(point[0]) == period:
            point[1] = value
    fake_suameca.set(menu_id, doc)


# Filter 1


def test_unapproved_ficha_is_never_connected(ficha, connector, raw_store, store):
    pending = ficha("minimum_wage_monthly").model_copy(update={"approval": Approval(status="pending")})
    with pytest.raises(UnapprovedSeries, match="pending"):
        ingest(pending, connector, raw_store, store)


def test_approved_ficha_connects(ficha, connector, raw_store, store):
    assert ingest(approved(ficha("minimum_wage_monthly")), connector, raw_store, store).stored


def test_approval_without_hash_is_not_valid(ficha, connector, raw_store, store):
    no_hash = ficha("minimum_wage_monthly").model_copy(update={"approval": Approval(status="approved")})
    with pytest.raises(UnapprovedSeries, match="without content_sha256"):
        ingest(no_hash, connector, raw_store, store)


def test_ficha_changed_after_approval_is_not_connected(ficha, connector, raw_store, store, tmp_path):
    original = FICHA_DIR / "minimum_wage_monthly.yaml"
    old_hash = ficha("minimum_wage_monthly").content_sha256
    edited = tmp_path / "minimum_wage_monthly.yaml"
    edited.write_text(original.read_text(encoding="utf-8").replace("min: 0", "min: 1"), encoding="utf-8")

    changed = approved(load_ficha(edited), content_sha256=old_hash)
    with pytest.raises(UnapprovedSeries, match="changed after approval"):
        ingest(changed, connector, raw_store, store)


# Archive and evidence


def test_original_response_is_archived_with_hash(ficha, connector, raw_store, store):
    result = _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    [ref] = result.download.raw_files
    original = raw_store.load(ref.location)
    assert original == (FIXTURES / "menu_500023.json").read_bytes()
    assert ref.sha256 == hashlib.sha256(original).hexdigest()
    assert result.download.source_updated == "07 de enero de 2026"


def test_original_is_archived_even_when_shape_fails(ficha, connector, fake_suameca, raw_store, store):
    fake_suameca.set(100001, b"")
    with pytest.raises(ShapeError):
        _run(ficha, connector, raw_store, store, "inflation_annual_national")
    assert list((raw_store.root / "banrep_suameca").iterdir())
    assert store.downloads("inflation_annual_national") == []


def test_reference_mismatch_fails_the_connector(ficha, connector, fake_suameca, raw_store, store):
    _set_value(fake_suameca, 100001, 15270, Period(2026, 9), 6.35)
    with pytest.raises(ReferenceMismatch):
        _run(ficha, connector, raw_store, store, "inflation_annual_national")
    assert store.downloads("inflation_annual_national") == []


# Filter 5 and quarantine


def test_never_run_contrast_is_pending_never_passed(ficha, connector, raw_store, store):
    for code in ("inflation_annual_national", "unemployment_rate_national"):
        result = _run(ficha, connector, raw_store, store, code)  # no contrast results at all
        assert all(o.contrast is ContrastStatus.PENDING for o in result.stored)
        assert all(o.status is ObservationStatus.QUARANTINED for o in result.stored)
        assert all(Flag.CONTRAST_PENDING in o.flags for o in result.stored)


def test_minimum_wage_contrast_does_not_apply_and_is_accepted(ficha, connector, raw_store, store):
    result = _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    assert all(o.contrast is ContrastStatus.NOT_APPLICABLE for o in result.stored)
    assert all(o.status is ObservationStatus.ACCEPTED for o in result.stored)
    assert all(o.flags == {Flag.NO_SECOND_SOURCE} for o in result.stored)


def _every_period(contrast: PeriodContrast):
    return lambda values: {(v.period, v.territory): contrast for v in values}


def test_failed_contrast_quarantines(ficha, connector, raw_store, store):
    result = _run(
        ficha, connector, raw_store, store, "unemployment_rate_national",
        contrast=_every_period(PeriodContrast(ContrastStatus.FAILED)),
    )
    assert all(o.contrast is ContrastStatus.FAILED for o in result.stored)
    assert all(Flag.CONTRAST_MISMATCH in o.flags for o in result.stored)


def test_passed_contrast_accepts_and_keeps_its_level(ficha, connector, raw_store, store):
    result = _run(
        ficha, connector, raw_store, store, "unemployment_rate_national",
        contrast=_every_period(PeriodContrast(ContrastStatus.PASSED, ContrastLevel.ANNUAL)),
    )
    assert all(o.contrast is ContrastStatus.PASSED for o in result.stored)
    assert all(o.contrast_level is ContrastLevel.ANNUAL for o in result.stored)
    assert all(o.status is ObservationStatus.ACCEPTED for o in result.stored)


def test_unavailable_contrast_leaves_quarantine_but_is_flagged(ficha, connector, raw_store, store):
    result = _run(
        ficha, connector, raw_store, store, "unemployment_rate_national",
        contrast=_every_period(PeriodContrast(ContrastStatus.UNAVAILABLE)),
    )
    assert all(o.status is ObservationStatus.ACCEPTED for o in result.stored)
    assert all(Flag.CONTRAST_UNAVAILABLE in o.flags for o in result.stored)


def test_period_missing_from_contrast_report_is_pending(ficha, connector, raw_store, store):
    result = _run(ficha, connector, raw_store, store, "unemployment_rate_national", contrast=lambda values: {})
    assert all(o.contrast is ContrastStatus.PENDING for o in result.stored)


def test_value_leaves_quarantine_when_its_contrast_later_passes(ficha, connector, raw_store, store):
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")  # pending
    assert store.latest("unemployment_rate_national") == {}
    second = _run(
        ficha, connector, raw_store, store, "unemployment_rate_national",
        contrast=_every_period(PeriodContrast(ContrastStatus.PASSED, ContrastLevel.MONTHLY)),
    )
    assert len(second.stored) == 308  # same values, new validation state: new versions
    assert len(store.latest("unemployment_rate_national")) == 308


def test_quarantined_data_is_read_only_when_asked(ficha, connector, raw_store, store):
    _run(ficha, connector, raw_store, store, "inflation_annual_national")
    assert store.latest("inflation_annual_national") == {}
    explicit = store.latest("inflation_annual_national", include_quarantined=True)
    assert explicit[(Period(2026, 9), "national")].value == Decimal("6.29")


# Filter 3: the initial load is not jump-checked; new observations are


def test_initial_load_has_no_jump_flags(ficha, connector, raw_store, store):
    for code in ("inflation_annual_national", "unemployment_rate_national"):
        result = _run(ficha, connector, raw_store, store, code)
        assert not any(Flag.JUMP in o.flags for o in result.stored)


@pytest.mark.parametrize(("delta", "jumps"), [("4.01", True), ("4.00", False), ("-4.01", True)])
def test_unemployment_jump_is_year_over_year_and_strict(ficha, connector, fake_suameca, raw_store, store, delta, jumps):
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    year_ago = _values(target_series(fixture_document(500021), 15312))[Period(2025, 9)]
    _add_month(fake_suameca, 500021, 15312, Period(2026, 9), year_ago + Decimal(delta))

    result = _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    [new] = result.stored
    assert new.period == Period(2026, 9)
    assert (Flag.JUMP in new.flags) is jumps


def test_unemployment_january_rise_is_not_a_jump(ficha, connector, fake_suameca, raw_store, store):
    # A typical December-to-January rise (+3.5 pp) with the same level as a year before.
    doc = fixture_document(500021)
    series = target_series(doc, 15312)
    values = _values(series)
    series["data"].append([_stamp(Period(2026, 9)), values[Period(2025, 9)]])
    series["data"].append([_stamp(Period(2026, 10)), values[Period(2025, 10)]])
    series["data"].append([_stamp(Period(2026, 11)), values[Period(2025, 11)]])
    series["data"].append([_stamp(Period(2026, 12)), values[Period(2025, 12)]])
    series["data"].append([_stamp(Period(2027, 1)), values[Period(2025, 12)] + Decimal("3.5")])
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    fake_suameca.set(500021, doc)

    result = _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    january = next(o for o in result.stored if o.period == Period(2027, 1))
    assert abs(january.value - values[Period(2026, 1)]) <= Decimal("4.0")
    assert Flag.JUMP not in january.flags


def test_inflation_monthly_step_jump(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "inflation_annual_national")
    _add_month(fake_suameca, 100001, 15270, Period(2026, 10), Decimal("6.29") + Decimal("2.01"))
    [new] = _run(ficha, connector, raw_store, store, "inflation_annual_national").stored
    assert Flag.JUMP in new.flags


def test_out_of_range_new_value_is_quarantined_not_rejected(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    _add_month(fake_suameca, 500021, 15312, Period(2026, 9), Decimal("31"))
    [new] = _run(ficha, connector, raw_store, store, "unemployment_rate_national").stored
    assert new.value == Decimal("31")
    assert Flag.OUT_OF_RANGE in new.flags and new.status is ObservationStatus.QUARANTINED


def test_gap_is_flagged(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    _add_month(fake_suameca, 500021, 15312, Period(2026, 10), Decimal("9.0"))  # September missing
    [new] = _run(ficha, connector, raw_store, store, "unemployment_rate_national").stored
    assert Flag.GAP_BEFORE in new.flags


# Filter 6


def test_changed_final_value_raises_alert_and_falls_back(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    doc = fixture_document(500023)
    series = target_series(doc, 15416)
    series["data"][-2][1] = Decimal("1423501")  # 2025
    fake_suameca.set(500023, doc)

    result = _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    [changed] = result.stored
    assert changed.period == Period(2025)
    assert Flag.HISTORY_CHANGED in changed.flags and changed.status is ObservationStatus.QUARANTINED
    # Users keep the last validated value; the changed one is visible only on request.
    assert store.latest("minimum_wage_monthly")[(Period(2025), "national")].value == Decimal("1423500")
    assert store.latest("minimum_wage_monthly", include_quarantined=True)[(Period(2025), "national")].value == Decimal(
        "1423501"
    )


def test_review_flags_persist_on_later_runs(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    doc = fixture_document(500023)
    target_series(doc, 15416)["data"][-2][1] = Decimal("1423501")
    fake_suameca.set(500023, doc)
    _run(ficha, connector, raw_store, store, "minimum_wage_monthly")

    third = _run(ficha, connector, raw_store, store, "minimum_wage_monthly")  # same changed value again
    assert third.stored == []  # nothing new, and the alert was not dropped
    latest = store.latest("minimum_wage_monthly", include_quarantined=True)[(Period(2025), "national")]
    assert Flag.HISTORY_CHANGED in latest.flags and latest.status is ObservationStatus.QUARANTINED


def test_jump_flag_persists_on_later_runs(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "inflation_annual_national")
    _add_month(fake_suameca, 100001, 15270, Period(2026, 10), Decimal("8.30"))
    _run(ficha, connector, raw_store, store, "inflation_annual_national")
    third = _run(
        ficha, connector, raw_store, store, "inflation_annual_national",
        contrast=_every_period(PeriodContrast(ContrastStatus.PASSED, ContrastLevel.MONTHLY)),
    )
    october = next(o for o in third.stored if o.period == Period(2026, 10))
    assert Flag.JUMP in october.flags and october.status is ObservationStatus.QUARANTINED


def test_provisional_period_change_is_not_an_alert(ficha, connector, raw_store, store):
    homicides = ficha("homicides_intentional_national")
    assert not homicides.is_final(Period(2026, 9), date(2026, 10, 25))
    assert not homicides.is_final(Period(2025, 9), date(2026, 3, 31))
    assert homicides.is_final(Period(2025, 9), date(2026, 4, 1))
    assert ficha("inflation_annual_national").is_final(Period(2026, 9), date(2026, 10, 25))


def test_changed_2021_unemployment_value_is_not_jump_checked(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    _set_value(fake_suameca, 500021, 15312, Period(2021, 6), 30.0)
    [changed] = _run(ficha, connector, raw_store, store, "unemployment_rate_national").stored
    assert Flag.HISTORY_CHANGED in changed.flags
    assert Flag.JUMP not in changed.flags


def test_known_exception_period_is_not_jump_checked(ficha, connector, fake_suameca, raw_store, store):
    _run(ficha, connector, raw_store, store, "unemployment_rate_national")
    _set_value(fake_suameca, 500021, 15312, Period(2020, 5), 25.0)  # 2020-05 is a documented exception
    [changed] = _run(ficha, connector, raw_store, store, "unemployment_rate_national").stored
    assert Flag.JUMP not in changed.flags


def test_unchanged_values_are_not_stored_again(ficha, connector, raw_store, store):
    _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    second = _run(ficha, connector, raw_store, store, "minimum_wage_monthly")
    assert second.stored == [] and second.unchanged == 43
    assert len(store.downloads("minimum_wage_monthly")) == 2
