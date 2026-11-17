"""A deterministic daily diagnosis of one shop, built only from records the platform holds.

Every number comes from here. The language model later words the alerts and limitations; it never
sees or decides a number. The diagnosis says what data it used and what it could not know.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

EXPIRING_SOON_HOURS = 24
CLOSING_SOON_HOURS = 6
RECENT_DAYS = 7


class AlertCode(StrEnum):
    NOTHING_PUBLISHED = "nothing_published"
    EXPIRING_SOON = "expiring_soon"
    STOCK_CLOSING_SOON = "stock_closing_soon"
    WASTE_RECORDED = "waste_recorded"
    PENDING_PICKUPS = "pending_pickups"


class LimitationCode(StrEnum):
    NO_ACTIVE_LOTS = "no_active_lots"
    NO_PICKUPS_RECORDED = "no_pickups_recorded"
    NO_WASTE_RECORDS = "no_waste_records"
    FORECAST_NOT_INCLUDED = "forecast_not_included"


class DataSource(StrEnum):
    LOTS = "lots"
    RESERVATIONS = "reservations"
    DONATIONS = "donations"
    WASTE_RECORDS = "waste_records"


@dataclass(frozen=True)
class LotFact:
    lot_id: int
    quantity: int
    expires_at: datetime


@dataclass(frozen=True)
class ShopSnapshot:
    active_lots: tuple[LotFact, ...]
    picked_up_units: int
    delivered_donation_units: int
    cancelled_units: int
    wasted_units: int
    pending_pickup_units: int
    ever_recorded_waste: bool


@dataclass(frozen=True)
class DiagnosisFacts:
    active_lots: int
    units_available: int
    lots_expiring_soon: int
    units_expiring_soon: int
    units_closing_soon: int
    picked_up_units: int
    delivered_donation_units: int
    cancelled_units: int
    wasted_units: int
    pending_pickup_units: int


@dataclass(frozen=True)
class Diagnosis:
    facts: DiagnosisFacts
    alerts: tuple[AlertCode, ...]
    limitations: tuple[LimitationCode, ...]
    data_used: tuple[DataSource, ...]


def diagnose(snapshot: ShopSnapshot, now: datetime) -> Diagnosis:
    soon = now + timedelta(hours=EXPIRING_SOON_HOURS)
    closing = now + timedelta(hours=CLOSING_SOON_HOURS)
    expiring = [lot for lot in snapshot.active_lots if lot.expires_at <= soon]
    facts = DiagnosisFacts(
        active_lots=len(snapshot.active_lots),
        units_available=sum(lot.quantity for lot in snapshot.active_lots),
        lots_expiring_soon=len(expiring),
        units_expiring_soon=sum(lot.quantity for lot in expiring),
        units_closing_soon=sum(lot.quantity for lot in snapshot.active_lots if lot.expires_at <= closing),
        picked_up_units=snapshot.picked_up_units,
        delivered_donation_units=snapshot.delivered_donation_units,
        cancelled_units=snapshot.cancelled_units,
        wasted_units=snapshot.wasted_units,
        pending_pickup_units=snapshot.pending_pickup_units,
    )
    alerts: list[AlertCode] = []
    if facts.active_lots == 0:
        alerts.append(AlertCode.NOTHING_PUBLISHED)
    if facts.lots_expiring_soon:
        alerts.append(AlertCode.EXPIRING_SOON)
    if facts.units_closing_soon:
        alerts.append(AlertCode.STOCK_CLOSING_SOON)
    if facts.wasted_units:
        alerts.append(AlertCode.WASTE_RECORDED)
    if facts.pending_pickup_units:
        alerts.append(AlertCode.PENDING_PICKUPS)
    limitations = [LimitationCode.FORECAST_NOT_INCLUDED]
    if facts.active_lots == 0:
        limitations.append(LimitationCode.NO_ACTIVE_LOTS)
    if facts.picked_up_units == 0:
        limitations.append(LimitationCode.NO_PICKUPS_RECORDED)
    if not snapshot.ever_recorded_waste:
        limitations.append(LimitationCode.NO_WASTE_RECORDS)
    return Diagnosis(facts, tuple(alerts), tuple(limitations), tuple(DataSource))
