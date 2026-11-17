from datetime import datetime, timedelta, timezone

import pytest

from app.domain.diagnosis import (
    AlertCode,
    DataSource,
    LimitationCode,
    LotFact,
    ShopSnapshot,
    diagnose,
)
from app.domain.exceptions import WasteInvalidError
from app.domain.waste import validate_waste

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def lot(lot_id: int, quantity: int, hours: float) -> LotFact:
    return LotFact(lot_id, quantity, NOW + timedelta(hours=hours))


def snapshot(*lots: LotFact, **overrides) -> ShopSnapshot:
    fields = {
        "active_lots": tuple(lots),
        "picked_up_units": 5,
        "delivered_donation_units": 0,
        "cancelled_units": 0,
        "wasted_units": 0,
        "pending_pickup_units": 0,
        "ever_recorded_waste": True,
        **overrides,
    }
    return ShopSnapshot(**fields)


# ---- waste ----


def test_a_waste_note_is_cleaned_and_a_valid_quantity_is_accepted():
    assert validate_waste(3, 10, "  fell   from the shelf ") == "fell from the shelf"


@pytest.mark.parametrize("quantity", [0, -1, 11])
def test_a_quantity_outside_one_and_the_available_units_is_rejected(quantity):
    with pytest.raises(WasteInvalidError) as error:
        validate_waste(quantity, 10, "")

    assert str(error.value) == "quantity_out_of_range"


def test_a_note_longer_than_the_limit_is_rejected():
    with pytest.raises(WasteInvalidError) as error:
        validate_waste(1, 10, "x" * 201)

    assert str(error.value) == "note_too_long"


# ---- diagnosis ----


def test_the_facts_are_counted_from_the_active_lots():
    result = diagnose(snapshot(lot(1, 10, 3), lot(2, 5, 20), lot(3, 8, 60)), NOW)

    facts = result.facts
    assert (facts.active_lots, facts.units_available) == (3, 23)
    assert (facts.lots_expiring_soon, facts.units_expiring_soon) == (2, 15)
    assert facts.units_closing_soon == 10


def test_a_shop_with_stock_closing_soon_gets_the_matching_alerts():
    result = diagnose(snapshot(lot(1, 10, 3)), NOW)

    assert AlertCode.EXPIRING_SOON in result.alerts
    assert AlertCode.STOCK_CLOSING_SOON in result.alerts


def test_a_shop_with_nothing_published_is_told_so_and_the_diagnosis_admits_what_it_cannot_know():
    result = diagnose(snapshot(picked_up_units=0, ever_recorded_waste=False), NOW)

    assert result.alerts == (AlertCode.NOTHING_PUBLISHED,)
    assert set(result.limitations) == {
        LimitationCode.FORECAST_NOT_INCLUDED,
        LimitationCode.NO_ACTIVE_LOTS,
        LimitationCode.NO_PICKUPS_RECORDED,
        LimitationCode.NO_WASTE_RECORDS,
    }


def test_recorded_waste_and_pending_pickups_raise_their_own_alerts():
    result = diagnose(snapshot(lot(1, 4, 48), wasted_units=2, pending_pickup_units=3), NOW)

    assert AlertCode.WASTE_RECORDED in result.alerts
    assert AlertCode.PENDING_PICKUPS in result.alerts
    assert AlertCode.EXPIRING_SOON not in result.alerts


def test_a_healthy_shop_has_no_alerts_and_only_the_standing_forecast_limitation():
    result = diagnose(snapshot(lot(1, 4, 48)), NOW)

    assert result.alerts == ()
    assert result.limitations == (LimitationCode.FORECAST_NOT_INCLUDED,)


def test_the_diagnosis_always_names_every_source_it_read():
    assert set(diagnose(snapshot(), NOW).data_used) == set(DataSource)
