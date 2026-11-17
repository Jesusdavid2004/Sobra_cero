import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import scrapy
from scrapy.http import FormRequest, Request, Response

from app.domain.collection import StopReason
from app.domain.places import PASTO_BOUNDS, BoundingBox, category_from_osm
from scraper.context import CollectionContext
from scraper.items import BusinessItem

OVERPASS_TIMEOUT_SECONDS = 60
OVERPASS_DOWNLOAD_TIMEOUT_SECONDS = OVERPASS_TIMEOUT_SECONDS + 30
OSM_ELEMENT_URL = "https://www.openstreetmap.org/{kind}/{identifier}"
SHOP_TAGS = "supermarket|bakery|convenience|greengrocer|butcher|deli"
AMENITY_TAGS = "restaurant|cafe|fast_food|marketplace"


def build_overpass_query(bounds: BoundingBox) -> str:
    box = f"({bounds.south},{bounds.west},{bounds.north},{bounds.east})"
    return (
        f"[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];"
        f'(nwr["shop"~"{SHOP_TAGS}"]{box};nwr["amenity"~"{AMENITY_TAGS}"]{box};);out center tags;'
    )


def _address(tags: dict[str, str]) -> str:
    street = " ".join(part for part in (tags.get("addr:street"), tags.get("addr:housenumber")) if part)
    return tags.get("addr:full") or street


def _position(element: dict[str, Any]) -> tuple[Any, Any]:
    center = element.get("center") or {}
    return element.get("lat", center.get("lat")), element.get("lon", center.get("lon"))


def business_items(payload: dict[str, Any]) -> Iterator[BusinessItem]:
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        latitude, longitude = _position(element)
        yield BusinessItem(
            external_id=f"{element.get('type', 'node')}/{element.get('id', '')}",
            name=tags.get("name", ""),
            category=category_from_osm(tags).value,
            latitude=latitude,
            longitude=longitude,
            address=_address(tags),
            city=tags.get("addr:city", ""),
            website=tags.get("website") or tags.get("contact:website") or "",
            phone=tags.get("phone") or tags.get("contact:phone") or "",
            opening_hours=tags.get("opening_hours", ""),
            source_url=OSM_ELEMENT_URL.format(kind=element.get("type", "node"), identifier=element.get("id", "")),
        )


class OverpassSpider(scrapy.Spider):
    """Businesses from OpenStreetMap (ODbL). One bounded query per run; attribution is kept per record."""

    name = "overpass"

    def __init__(self, context: CollectionContext, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.context = context

    async def start(self) -> AsyncIterator[Request]:
        bounds = self.context.area or BoundingBox(*PASTO_BOUNDS)
        yield FormRequest(
            self.context.source.base_url,
            formdata={"data": build_overpass_query(bounds)},
            callback=self.parse_elements,
            errback=self.on_failure,
            meta={"download_timeout": OVERPASS_DOWNLOAD_TIMEOUT_SECONDS},
        )

    def parse_elements(self, response: Response) -> Iterator[BusinessItem]:
        yield from business_items(json.loads(response.text))

    def on_failure(self, failure: Any) -> None:
        self.context.stop_reason = StopReason.TIMEOUT.value
        self.logger.error("Overpass request failed: %s", failure.getErrorMessage())
