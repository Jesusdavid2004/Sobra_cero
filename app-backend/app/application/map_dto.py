from dataclasses import dataclass
from datetime import datetime

from app.domain.places import BoundingBox


@dataclass(frozen=True)
class MapPlace:
    """One point of the map, with where it came from and how fresh the information is."""

    place_id: str
    kind: str
    name: str
    category: str
    affiliation: str
    latitude: float
    longitude: float
    address: str
    city: str
    website: str
    opening_hours: str
    source: str
    source_url: str
    last_seen_at: datetime | None
    freshness: str
    verified: bool
    is_demo: bool
    offer_count: int


@dataclass(frozen=True)
class PlacesQuery:
    bounds: BoundingBox
    layers: frozenset[str]
    categories: frozenset[str]
    text: str
    only_with_offers: bool
    include_demo: bool
    limit: int


@dataclass(frozen=True)
class PlacesResult:
    places: tuple[MapPlace, ...]
    counts: dict[str, int]
    attribution: str


@dataclass(frozen=True)
class PromotionView:
    name: str
    category: str
    price_cop: int
    original_price_cop: int | None
    discount_percent: int
    url: str
    source_name: str
    last_seen_at: datetime
