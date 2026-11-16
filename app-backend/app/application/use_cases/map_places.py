from datetime import datetime

from app.application.map_dto import MapPlace, PlacesQuery, PlacesResult, PromotionView
from app.application.ports import GeocodingProvider, MapRepository
from app.domain.geocoding import ATTRIBUTION, GeocodeResult
from app.domain.opportunities import Cell, aggregate
from app.domain.places import BoundingBox, normalize_name

LAYER_AFFILIATED = "affiliated"
LAYER_DISCOVERED = "discovered"
LAYER_RECEIVERS = "receivers"
ALL_LAYERS = frozenset({LAYER_AFFILIATED, LAYER_DISCOVERED, LAYER_RECEIVERS})
MAX_PLACES = 500
MAX_PROMOTIONS = 50


class ListMapPlaces:
    """Affiliated shops, businesses found in external sources and receivers, kept visibly apart."""

    def __init__(self, maps: MapRepository) -> None:
        self._maps = maps

    def execute(self, query: PlacesQuery, now: datetime) -> PlacesResult:
        text = normalize_name(query.text)
        limit = min(query.limit, MAX_PLACES)
        layers: dict[str, list[MapPlace]] = {}
        if LAYER_AFFILIATED in query.layers:
            layers[LAYER_AFFILIATED] = self._maps.affiliated(
                query.bounds, query.categories, text, query.only_with_offers, limit, now
            )
        if LAYER_DISCOVERED in query.layers and not query.only_with_offers:
            layers[LAYER_DISCOVERED] = self._maps.discovered(
                query.bounds, query.categories, text, query.include_demo, limit, now
            )
        if LAYER_RECEIVERS in query.layers and not query.only_with_offers and not query.categories:
            layers[LAYER_RECEIVERS] = self._maps.receivers(query.bounds, text, limit)
        places = tuple(place for found in layers.values() for place in found)[:limit]
        shows_osm_data = any(place.source != "sobracero" and not place.is_demo for place in places)
        return PlacesResult(
            places, {name: len(found) for name, found in layers.items()}, ATTRIBUTION if shows_osm_data else ""
        )


class GetMapOpportunities:
    """Counts of verifiable records per grid cell. It never estimates waste."""

    def __init__(self, maps: MapRepository) -> None:
        self._maps = maps

    def execute(self, bounds: BoundingBox, include_demo: bool, now: datetime) -> list[Cell]:
        return aggregate(self._maps.signal_points(bounds, include_demo, now))


class ListPublicPromotions:
    """Recent promotions published by external catalogs. They are prices, not surplus or expiry."""

    def __init__(self, maps: MapRepository) -> None:
        self._maps = maps

    def execute(self, limit: int, now: datetime) -> list[PromotionView]:
        return self._maps.fresh_promotions(min(limit, MAX_PROMOTIONS), now)


class SearchGeocode:
    def __init__(self, provider: GeocodingProvider) -> None:
        self._provider = provider

    def execute(self, text: str, limit: int) -> list[GeocodeResult]:
        return self._provider.search(text, limit)
