"""Feasible-pickup discovery: which lots can a customer actually collect, and why not the others.

Distance is the straight-line (haversine) distance and travel time is derived from one declared
average speed. Both are approximations and must be presented as such; no routing data is used.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import asin, cos, radians, sin, sqrt

from app.domain.exceptions import DiscoveryInvalidError
from app.domain.rules import (
    ASSUMED_TRAVEL_SPEED_KMH,
    EARTH_RADIUS_KM,
    MAX_DISCOVERY_RADIUS_KM,
    MINUTES_PER_HOUR,
)

PERCENT = 100


class ExclusionReason(StrEnum):
    TOO_FAR = "too_far"
    CLOSES_BEFORE_ARRIVAL = "closes_before_arrival"
    OUTSIDE_PICKUP_WINDOW = "outside_pickup_window"
    OVER_BUDGET = "over_budget"
    NOT_ENOUGH_STOCK = "not_enough_stock"
    CATEGORY_MISMATCH = "category_mismatch"


class RankingMethod(StrEnum):
    DISTANCE_ONLY = "distance_only"
    FEASIBILITY = "feasibility"


@dataclass(frozen=True)
class DiscoveryQuery:
    latitude: float
    longitude: float
    window_start: datetime
    window_end: datetime
    max_distance_km: float
    quantity: int = 1
    budget_cents: int | None = None
    category: str | None = None

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise DiscoveryInvalidError("Location is out of range")
        if self.window_end <= self.window_start:
            raise DiscoveryInvalidError("The pickup window must end after it starts")
        if not 0 < self.max_distance_km <= MAX_DISCOVERY_RADIUS_KM:
            raise DiscoveryInvalidError("Distance limit is out of range")
        if self.quantity < 1:
            raise DiscoveryInvalidError("Quantity must be at least one")
        if self.budget_cents is not None and self.budget_cents < 0:
            raise DiscoveryInvalidError("Budget cannot be negative")


@dataclass(frozen=True)
class LotCandidate:
    lot_id: int
    shop_id: int
    title: str
    category: str
    available_quantity: int
    original_price_cents: int
    discount_percent: int
    closes_at: datetime
    latitude: float
    longitude: float

    @property
    def unit_price_cents(self) -> int:
        return self.original_price_cents * (PERCENT - self.discount_percent) // PERCENT


@dataclass(frozen=True)
class LotAssessment:
    candidate: LotCandidate
    distance_km: float
    travel_minutes: int
    slack_minutes: int
    reasons: tuple[ExclusionReason, ...]

    @property
    def feasible(self) -> bool:
        return not self.reasons


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    delta_lat = radians(lat_b - lat_a)
    delta_lon = radians(lon_b - lon_a)
    haversine = sin(delta_lat / 2) ** 2 + cos(radians(lat_a)) * cos(radians(lat_b)) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))


def travel_minutes(distance: float) -> int:
    return round(distance / ASSUMED_TRAVEL_SPEED_KMH * MINUTES_PER_HOUR)


def assess_lot(candidate: LotCandidate, query: DiscoveryQuery, now: datetime) -> LotAssessment:
    distance = distance_km(query.latitude, query.longitude, candidate.latitude, candidate.longitude)
    minutes = travel_minutes(distance)
    earliest_arrival = max(query.window_start, now + timedelta(minutes=minutes))
    latest_arrival = min(query.window_end, candidate.closes_at)
    slack = int((latest_arrival - earliest_arrival).total_seconds() // MINUTES_PER_HOUR)
    reasons: list[ExclusionReason] = []
    if distance > query.max_distance_km:
        reasons.append(ExclusionReason.TOO_FAR)
    if slack < 0:
        reasons.append(
            ExclusionReason.CLOSES_BEFORE_ARRIVAL
            if candidate.closes_at < earliest_arrival
            else ExclusionReason.OUTSIDE_PICKUP_WINDOW
        )
    if candidate.available_quantity < query.quantity:
        reasons.append(ExclusionReason.NOT_ENOUGH_STOCK)
    if query.budget_cents is not None and candidate.unit_price_cents * query.quantity > query.budget_cents:
        reasons.append(ExclusionReason.OVER_BUDGET)
    if query.category is not None and candidate.category != query.category:
        reasons.append(ExclusionReason.CATEGORY_MISMATCH)
    return LotAssessment(candidate, round(distance, 2), minutes, slack, tuple(reasons))


def rank(assessments: list[LotAssessment], method: RankingMethod) -> list[LotAssessment]:
    """Order assessments by one documented method.

    DISTANCE_ONLY is the baseline: nearest first, constraints ignored. FEASIBILITY keeps only the
    lots that can be collected and puts the ones closing soonest first (they are the most at risk
    of being wasted), then the nearest.
    """
    if method is RankingMethod.DISTANCE_ONLY:
        return sorted(assessments, key=lambda item: (item.distance_km, item.candidate.lot_id))
    feasible = [item for item in assessments if item.feasible]
    return sorted(feasible, key=lambda item: (item.candidate.closes_at, item.distance_km, item.candidate.lot_id))
