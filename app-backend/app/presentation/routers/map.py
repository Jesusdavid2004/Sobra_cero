from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.map_dto import MapPlace, PlacesQuery, PromotionView
from app.db import get_db
from app.dependencies import (
    build_get_map_opportunities_use_case,
    build_list_map_places_use_case,
    build_list_public_promotions_use_case,
    build_search_geocode_use_case,
)
from app.domain.geocoding import MAX_QUERY_CHARS, MAX_RESULTS, GeocodeResult
from app.domain.opportunities import Cell
from app.domain.places import PASTO_BOUNDS, BoundingBox
from app.presentation.rate_limit import rate_limited

router = APIRouter(prefix="/api/v1", tags=["map"])
GEOCODE_REQUESTS_PER_MINUTE = 20
MAX_PLACE_LIMIT = 500
Layer = Literal["affiliated", "discovered", "receivers"]
DEFAULT_LAYERS: tuple[Layer, ...] = ("affiliated", "discovered", "receivers")


class PlaceOut(BaseModel):
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


class PlacesOut(BaseModel):
    places: list[PlaceOut]
    counts: dict[str, int]
    attribution: str


class CellOut(BaseModel):
    south: float
    west: float
    center_latitude: float
    center_longitude: float
    affiliated_shops: int
    live_offers: int
    receivers: int
    discovered_businesses: int
    total: int
    somewhere_to_invite: bool


class PromotionOut(BaseModel):
    name: str
    category: str
    price_cop: int
    original_price_cop: int | None
    discount_percent: int
    url: str
    source_name: str
    last_seen_at: datetime


class GeocodeOut(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    category: str
    attribution: str


def _bounds(south: float | None, west: float | None, north: float | None, east: float | None) -> BoundingBox:
    if None in (south, west, north, east):
        return BoundingBox(*PASTO_BOUNDS)
    return BoundingBox(south, west, north, east)  # type: ignore[arg-type]


def _place(place: MapPlace) -> PlaceOut:
    return PlaceOut(**place.__dict__)


def _cell(cell: Cell) -> CellOut:
    latitude, longitude = cell.center
    return CellOut(
        south=cell.south,
        west=cell.west,
        center_latitude=latitude,
        center_longitude=longitude,
        affiliated_shops=cell.affiliated_shops,
        live_offers=cell.live_offers,
        receivers=cell.receivers,
        discovered_businesses=cell.discovered_businesses,
        total=cell.total,
        somewhere_to_invite=cell.has_unserved_businesses,
    )


@router.get("/map/places", response_model=PlacesOut)
def map_places(
    south: float | None = Query(None, ge=-90, le=90),
    west: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    layer: list[Layer] = Query(list(DEFAULT_LAYERS)),
    category: list[str] = Query([]),
    q: str = Query("", max_length=MAX_QUERY_CHARS),
    only_with_offers: bool = Query(False),
    include_demo: bool = Query(False),
    limit: int = Query(MAX_PLACE_LIMIT, ge=1, le=MAX_PLACE_LIMIT),
    db: Session = Depends(get_db),
) -> PlacesOut:
    query = PlacesQuery(
        _bounds(south, west, north, east),
        frozenset(layer),
        frozenset(category),
        q,
        only_with_offers,
        include_demo,
        limit,
    )
    result = build_list_map_places_use_case(db).execute(query, datetime.now(timezone.utc))
    return PlacesOut(places=[_place(p) for p in result.places], counts=result.counts, attribution=result.attribution)


@router.get("/map/opportunities", response_model=list[CellOut])
def map_opportunities(include_demo: bool = Query(False), db: Session = Depends(get_db)) -> list[CellOut]:
    cells = build_get_map_opportunities_use_case(db).execute(
        BoundingBox(*PASTO_BOUNDS), include_demo, datetime.now(timezone.utc)
    )
    return [_cell(cell) for cell in cells]


@router.get("/map/promotions", response_model=list[PromotionOut])
def public_promotions(limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)) -> list[PromotionOut]:
    promotions: list[PromotionView] = build_list_public_promotions_use_case(db).execute(
        limit, datetime.now(timezone.utc)
    )
    return [PromotionOut(**promotion.__dict__) for promotion in promotions]


@router.get(
    "/geo/search",
    response_model=list[GeocodeOut],
    dependencies=[Depends(rate_limited(GEOCODE_REQUESTS_PER_MINUTE))],
)
def geocode(
    q: str = Query(max_length=MAX_QUERY_CHARS), limit: int = Query(5, ge=1, le=MAX_RESULTS)
) -> list[GeocodeOut]:
    results: list[GeocodeResult] = build_search_geocode_use_case().execute(q, limit)
    return [GeocodeOut(**result.__dict__) for result in results]
