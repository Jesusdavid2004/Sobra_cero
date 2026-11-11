"""Donation receivers: hard compatibility rules first, then an explainable fairness ordering.

Receivers declare what they accept, how much, whether they can keep refrigerated food and when
they are open (a daily window in their own UTC offset). Distance is straight-line and travel time
comes from one declared average speed, so both are approximations. Nothing here certifies that
an organization is authorized to receive food: a real launch needs that checked outside the app.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.discovery import distance_km, travel_minutes
from app.domain.exceptions import ReceiverInvalidError
from app.domain.rules import (
    MAX_RECEIVER_CAPACITY,
    MAX_UTC_OFFSET_MINUTES,
    MINUTES_PER_DAY,
    RECEIVER_WINDOW_LOOKAHEAD_DAYS,
    REFRIGERATED_CATEGORIES,
)


class ReceiverExclusion(StrEnum):
    CATEGORY_NOT_ACCEPTED = "category_not_accepted"
    OVER_CAPACITY = "over_capacity"
    NEEDS_REFRIGERATION = "needs_refrigeration"
    TOO_FAR = "too_far"
    CLOSED_BEFORE_PICKUP = "closed_before_pickup"


class OfferStatus(StrEnum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    DELIVERED = "delivered"


ACTIVE_OFFER_STATUSES = (OfferStatus.OFFERED, OfferStatus.ACCEPTED)
COMMITTED_OFFER_STATUSES = (OfferStatus.ACCEPTED, OfferStatus.DELIVERED)


@dataclass(frozen=True)
class Receiver:
    id: int
    owner_user_id: int
    name: str
    latitude: float
    longitude: float
    accepted_categories: frozenset[str]
    max_quantity: int
    can_store_refrigerated: bool
    open_from_minute: int
    open_until_minute: int
    utc_offset_minutes: int

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.accepted_categories:
            raise ReceiverInvalidError("A receiver needs a name and at least one accepted category")
        if not 1 <= self.max_quantity <= MAX_RECEIVER_CAPACITY:
            raise ReceiverInvalidError("Capacity is outside the allowed range")
        if not 0 <= self.open_from_minute < self.open_until_minute <= MINUTES_PER_DAY:
            raise ReceiverInvalidError("The opening window must start before it ends within one day")
        if abs(self.utc_offset_minutes) > MAX_UTC_OFFSET_MINUTES:
            raise ReceiverInvalidError("UTC offset is out of range")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ReceiverInvalidError("Location is out of range")

    def is_open_during(self, start: datetime, end: datetime) -> bool:
        """Whether the daily opening window overlaps [start, end] on any of the next few days."""
        offset = timedelta(minutes=self.utc_offset_minutes)
        first_day = (start + offset).replace(hour=0, minute=0, second=0, microsecond=0)
        for day in range(RECEIVER_WINDOW_LOOKAHEAD_DAYS):
            day_start = first_day + timedelta(days=day) - offset
            opens = day_start + timedelta(minutes=self.open_from_minute)
            closes = day_start + timedelta(minutes=self.open_until_minute)
            if max(opens, start) < min(closes, end):
                return True
        return False


@dataclass(frozen=True)
class DonationLot:
    lot_id: int
    shop_id: int
    owner_id: int
    title: str
    category: str
    available_quantity: int
    status: str
    closes_at: datetime
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ReceiverAssessment:
    receiver: Receiver
    distance_km: float
    travel_minutes: int
    recent_accepted: int
    reasons: tuple[ReceiverExclusion, ...]

    @property
    def compatible(self) -> bool:
        return not self.reasons


def assess_receiver(
    receiver: Receiver,
    lot: DonationLot,
    quantity: int,
    now: datetime,
    recent_accepted: int,
    radius_km: float,
) -> ReceiverAssessment:
    distance = distance_km(receiver.latitude, receiver.longitude, lot.latitude, lot.longitude)
    minutes = travel_minutes(distance)
    reasons: list[ReceiverExclusion] = []
    if lot.category not in receiver.accepted_categories:
        reasons.append(ReceiverExclusion.CATEGORY_NOT_ACCEPTED)
    if quantity > receiver.max_quantity:
        reasons.append(ReceiverExclusion.OVER_CAPACITY)
    if lot.category in REFRIGERATED_CATEGORIES and not receiver.can_store_refrigerated:
        reasons.append(ReceiverExclusion.NEEDS_REFRIGERATION)
    if distance > radius_km:
        reasons.append(ReceiverExclusion.TOO_FAR)
    if not receiver.is_open_during(now + timedelta(minutes=minutes), lot.closes_at):
        reasons.append(ReceiverExclusion.CLOSED_BEFORE_PICKUP)
    return ReceiverAssessment(receiver, round(distance, 2), minutes, recent_accepted, tuple(reasons))


def rank_receivers(assessments: list[ReceiverAssessment]) -> list[ReceiverAssessment]:
    """Compatible receivers only, those who received fewer donations recently first, then nearest.

    Among equally compatible receivers this avoids always favouring the same one; it does not
    claim to be an optimal allocation.
    """
    compatible = [item for item in assessments if item.compatible]
    return sorted(compatible, key=lambda item: (item.recent_accepted, item.distance_km, item.receiver.id))


NEW_RECEIVER_ID = 0


@dataclass(frozen=True)
class DonationOffer:
    id: int
    lot_id: int
    receiver_id: int
    quantity: int
    status: OfferStatus
    message: str
    created_at: datetime
    decided_at: datetime | None
    delivered_at: datetime | None


@dataclass(frozen=True)
class OfferView:
    """An offer with the names a screen needs; it never includes private account data."""

    offer: DonationOffer
    lot_title: str
    category: str
    closes_at: datetime
    shop_name: str
    receiver_name: str
