"""Synthetic comparison of two ways to order open lots for one pickup per search.

The scenarios are generated from a fixed seed and declared ranges; they are not real demand.
Results only describe behaviour under these assumptions and must never be read as a measured
reduction of food waste. The feasibility method keeps only lots that can be collected, so its
top result is collectable by construction; the quantity worth measuring is how often the
distance-only baseline recommends a lot that cannot be collected.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.domain.discovery import (
    DiscoveryQuery,
    LotCandidate,
    RankingMethod,
    assess_lot,
    rank,
)

EVALUATION_SEED = 20261110
SEARCH_COUNT = 1000
LOTS_PER_SEARCH = 30
REGION_CENTER_LAT = 4.7
REGION_CENTER_LON = -74.0
REGION_SPAN_DEGREES = 0.2
CLOSES_IN_MINUTES = (15, 360)
WINDOW_START_OFFSET_MINUTES = (0, 60)
WINDOW_LENGTH_MINUTES = (30, 180)
LOT_QUANTITY = (1, 10)
ORIGINAL_PRICE_CENTS = (500, 3000)
DISCOUNT_PERCENT = (10, 50)
BUDGET_CENTS = (1000, 4000)
SEARCH_QUANTITY = (1, 3)
SEARCH_RADIUS_KM = 10.0
CATEGORIES = ("bakery", "dairy", "produce", "meals")
EVALUATION_NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class MethodResult:
    method: RankingMethod
    searches_answered: int
    collectable_top_results: int

    @property
    def collectable_rate(self) -> float:
        return self.collectable_top_results / self.searches_answered if self.searches_answered else 0.0


@dataclass(frozen=True)
class EvaluationReport:
    seed: int
    searches: int
    searches_with_a_collectable_lot: int
    results: tuple[MethodResult, ...]


def _scatter(rng: random.Random) -> tuple[float, float]:
    return (
        REGION_CENTER_LAT + rng.uniform(-REGION_SPAN_DEGREES, REGION_SPAN_DEGREES) / 2,
        REGION_CENTER_LON + rng.uniform(-REGION_SPAN_DEGREES, REGION_SPAN_DEGREES) / 2,
    )


def _lot(rng: random.Random, lot_id: int) -> LotCandidate:
    latitude, longitude = _scatter(rng)
    return LotCandidate(
        lot_id=lot_id,
        shop_id=lot_id,
        title=f"Lot {lot_id}",
        category=rng.choice(CATEGORIES),
        available_quantity=rng.randint(*LOT_QUANTITY),
        original_price_cents=rng.randint(*ORIGINAL_PRICE_CENTS),
        discount_percent=rng.randint(*DISCOUNT_PERCENT),
        closes_at=EVALUATION_NOW + timedelta(minutes=rng.randint(*CLOSES_IN_MINUTES)),
        latitude=latitude,
        longitude=longitude,
    )


def _search(rng: random.Random) -> DiscoveryQuery:
    latitude, longitude = _scatter(rng)
    start = EVALUATION_NOW + timedelta(minutes=rng.randint(*WINDOW_START_OFFSET_MINUTES))
    return DiscoveryQuery(
        latitude=latitude,
        longitude=longitude,
        window_start=start,
        window_end=start + timedelta(minutes=rng.randint(*WINDOW_LENGTH_MINUTES)),
        max_distance_km=SEARCH_RADIUS_KM,
        quantity=rng.randint(*SEARCH_QUANTITY),
        budget_cents=rng.randint(*BUDGET_CENTS),
    )


def evaluate(seed: int = EVALUATION_SEED, searches: int = SEARCH_COUNT) -> EvaluationReport:
    rng = random.Random(seed)
    answered = {method: 0 for method in RankingMethod}
    collectable = {method: 0 for method in RankingMethod}
    with_a_collectable_lot = 0
    for _ in range(searches):
        lots = [_lot(rng, lot_id) for lot_id in range(1, LOTS_PER_SEARCH + 1)]
        query = _search(rng)
        assessments = [assess_lot(lot, query, EVALUATION_NOW) for lot in lots]
        if not any(item.feasible for item in assessments):
            continue
        with_a_collectable_lot += 1
        for method in RankingMethod:
            top = rank(assessments, method)[0]
            answered[method] += 1
            collectable[method] += int(top.feasible)
    return EvaluationReport(
        seed=seed,
        searches=searches,
        searches_with_a_collectable_lot=with_a_collectable_lot,
        results=tuple(MethodResult(method, answered[method], collectable[method]) for method in RankingMethod),
    )
