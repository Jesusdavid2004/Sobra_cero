"""Place search by name. Providers are interchangeable behind the `GeocodingProvider` port."""

from dataclasses import dataclass

from app.domain.exceptions import GeocodingQueryInvalidError

ATTRIBUTION = "© OpenStreetMap contributors"
MIN_QUERY_CHARS = 3
MAX_QUERY_CHARS = 120
MAX_RESULTS = 8


@dataclass(frozen=True)
class GeocodeResult:
    display_name: str
    latitude: float
    longitude: float
    category: str
    attribution: str = ATTRIBUTION


def clean_query(query: str) -> str:
    """Trim and collapse whitespace; reject queries too short or too long to be a place search."""
    cleaned = " ".join(query.split())
    if not MIN_QUERY_CHARS <= len(cleaned) <= MAX_QUERY_CHARS:
        raise GeocodingQueryInvalidError("The search text must have between 3 and 120 characters")
    return cleaned
