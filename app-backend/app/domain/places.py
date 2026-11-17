"""Places on the map: affiliated shops and businesses found in external sources.

An external business is never an affiliated shop. `Affiliation` is set by how a record entered
the system (a shop registered itself, or a connector found it) and nothing here infers it.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.discovery import distance_km
from app.domain.exceptions import PlaceInvalidError

METERS_PER_KM = 1000
DUPLICATE_DISTANCE_METERS = 75
DUPLICATE_NAME_SIMILARITY = 0.85
MAX_PLACE_NAME_CHARS = 160
PASTO_CENTER = (1.2136, -77.2811)
PASTO_BOUNDS = (1.15, -77.35, 1.28, -77.22)
NAME_NOISE = re.compile(r"[^a-z0-9 ]+")
SPACES = re.compile(r"\s+")


class Affiliation(StrEnum):
    AFFILIATED = "affiliated"
    PROSPECT = "prospect"
    DISCOVERED = "discovered"


class PlaceCategory(StrEnum):
    SUPERMARKET = "supermarket"
    RESTAURANT = "restaurant"
    BAKERY = "bakery"
    CAFE = "cafe"
    STORE = "store"
    MARKET = "market"
    OTHER = "other"


OSM_SHOP_CATEGORIES = {
    "supermarket": PlaceCategory.SUPERMARKET,
    "bakery": PlaceCategory.BAKERY,
    "convenience": PlaceCategory.STORE,
    "greengrocer": PlaceCategory.STORE,
    "butcher": PlaceCategory.STORE,
    "deli": PlaceCategory.STORE,
}
OSM_AMENITY_CATEGORIES = {
    "restaurant": PlaceCategory.RESTAURANT,
    "fast_food": PlaceCategory.RESTAURANT,
    "cafe": PlaceCategory.CAFE,
    "marketplace": PlaceCategory.MARKET,
}


@dataclass(frozen=True)
class BoundingBox:
    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        if not (-90 <= self.south < self.north <= 90 and -180 <= self.west < self.east <= 180):
            raise PlaceInvalidError("The bounding box is not valid")

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east


@dataclass(frozen=True)
class Place:
    """One point on the map, with where it came from and how fresh the information is."""

    place_id: str
    name: str
    category: PlaceCategory
    affiliation: Affiliation
    latitude: float
    longitude: float
    address: str
    city: str
    website: str
    opening_hours: str
    source: str
    source_url: str
    last_seen_at: datetime | None
    verified: bool


def category_from_osm(tags: dict[str, str]) -> PlaceCategory:
    shop = OSM_SHOP_CATEGORIES.get(tags.get("shop", ""))
    if shop is not None:
        return shop
    return OSM_AMENITY_CATEGORIES.get(tags.get("amenity", ""), PlaceCategory.OTHER)


def normalize_name(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    return SPACES.sub(" ", NAME_NOISE.sub(" ", folded)).strip()


def _trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def name_similarity(first: str, second: str) -> float:
    left, right = _trigrams(normalize_name(first)), _trigrams(normalize_name(second))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def are_duplicates(first: Place, second: Place) -> bool:
    """Same business: very close together and with a nearly identical name."""
    meters = distance_km(first.latitude, first.longitude, second.latitude, second.longitude) * METERS_PER_KM
    return meters <= DUPLICATE_DISTANCE_METERS and name_similarity(first.name, second.name) >= DUPLICATE_NAME_SIMILARITY


def validate_place_name(name: str) -> str:
    cleaned = SPACES.sub(" ", name).strip()
    if not cleaned or len(cleaned) > MAX_PLACE_NAME_CHARS:
        raise PlaceInvalidError("A place needs a name of at most 160 characters")
    return cleaned


def shop_category(business_type: str, dominant_product_category: str | None) -> PlaceCategory:
    """Category shown on the map for an affiliated shop.

    A shop only declares restaurant or supermarket. A restaurant whose products are mostly bread
    is shown as a bakery; a supermarket always stays a supermarket.
    """
    if business_type == "supermarket":
        return PlaceCategory.SUPERMARKET
    if dominant_product_category == "bakery":
        return PlaceCategory.BAKERY
    return PlaceCategory.RESTAURANT if business_type == "restaurant" else PlaceCategory.OTHER
