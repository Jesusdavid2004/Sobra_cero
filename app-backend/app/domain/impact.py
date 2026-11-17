"""Verified impact of a shop: what was actually picked up, kept apart from what is only pending.

Only a confirmed pickup counts as rescued. Publishing, reserving, cancelling and expiring are
reported separately, and no environmental equivalence (CO2, water, meals) is invented.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.entities import ReservationStatus

PERCENT = 100


@dataclass(frozen=True)
class ReservationOutcome:
    """Units of one lot in one reservation status, with the lot's current price."""

    status: str
    units: int
    original_price_cents: int
    discount_percent: int


@dataclass(frozen=True)
class ShopImpact:
    picked_up_units: int
    donated_units: int
    pending_units: int
    cancelled_units: int
    expired_units: int
    estimated_revenue_cents: int
    estimated_savings_cents: int


def _unit_price_cents(outcome: ReservationOutcome) -> int:
    return outcome.original_price_cents * (PERCENT - outcome.discount_percent) // PERCENT


def summarize_impact(outcomes: Iterable[ReservationOutcome], donated_units: int) -> ShopImpact:
    """Revenue and savings are estimates: reservations do not store the price they were made at,
    so the lot's current price is used."""
    units = {status.value: 0 for status in ReservationStatus}
    revenue = 0
    savings = 0
    for outcome in outcomes:
        units[outcome.status] = units.get(outcome.status, 0) + outcome.units
        if outcome.status == ReservationStatus.PICKED_UP.value:
            unit_price = _unit_price_cents(outcome)
            revenue += outcome.units * unit_price
            savings += outcome.units * (outcome.original_price_cents - unit_price)
    return ShopImpact(
        picked_up_units=units[ReservationStatus.PICKED_UP.value],
        donated_units=donated_units,
        pending_units=units[ReservationStatus.RESERVED.value],
        cancelled_units=units[ReservationStatus.CANCELLED.value],
        expired_units=units[ReservationStatus.EXPIRED.value],
        estimated_revenue_cents=revenue,
        estimated_savings_cents=savings,
    )
