"""Geocoding adapters: Nominatim (OpenStreetMap) and a deterministic fake for tests and offline demos.

Nominatim's usage policy (read 2026-11-16): at most one request per second, a User-Agent that
identifies the application, no autocomplete and no bulk geocoding, results cached, attribution
shown. The adapter enforces the rate and the cache; the API never calls it per keystroke.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.domain.exceptions import GeocoderUnavailableError
from app.domain.geocoding import MAX_RESULTS, GeocodeResult, clean_query
from app.domain.places import PASTO_BOUNDS

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_SECONDS = 1.0
CACHE_TTL_SECONDS = 24 * 3600
MAX_CACHE_ENTRIES = 500
REQUEST_TIMEOUT_SECONDS = 8.0
COUNTRY_CODE = "co"


class NominatimGeocoder:
    def __init__(
        self,
        client: httpx.Client,
        user_agent: str,
        base_url: str = NOMINATIM_URL,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._headers = {"User-Agent": user_agent}
        self._base_url = base_url
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._cache: dict[tuple[str, int], tuple[float, list[GeocodeResult]]] = {}

    def search(self, query: str, limit: int = MAX_RESULTS) -> list[GeocodeResult]:
        cleaned = clean_query(query)
        key = (cleaned.lower(), limit)
        cached = self._cache.get(key)
        if cached is not None and self._clock() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        self._wait_for_turn()
        results = self._request(cleaned, limit)
        if len(self._cache) >= MAX_CACHE_ENTRIES:
            self._cache.clear()
        self._cache[key] = (self._clock(), results)
        return results

    def _wait_for_turn(self) -> None:
        if self._last_request_at is not None:
            remaining = MIN_INTERVAL_SECONDS - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _request(self, query: str, limit: int) -> list[GeocodeResult]:
        south, west, north, east = PASTO_BOUNDS
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": str(min(limit, MAX_RESULTS)),
            "countrycodes": COUNTRY_CODE,
            "viewbox": f"{west},{north},{east},{south}",
        }
        try:
            response = self._client.get(
                self._base_url, params=params, headers=self._headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            payload: list[dict[str, Any]] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocoderUnavailableError("The place search is unavailable") from exc
        return [
            GeocodeResult(
                display_name=str(item["display_name"]),
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                category=str(item.get("category", "")),
            )
            for item in payload
            if "lat" in item and "lon" in item and "display_name" in item
        ]


GAZETTEER = (
    ("Plaza de Nariño, Pasto", 1.2145, -77.2811, "place"),
    ("Universidad de Nariño, Pasto", 1.2297, -77.2889, "amenity"),
    ("Terminal de Transportes, Pasto", 1.2008, -77.2742, "amenity"),
    ("Centro Comercial Unicentro, Pasto", 1.2036, -77.2644, "shop"),
    ("Plaza de mercado El Potrerillo, Pasto", 1.2100, -77.2790, "amenity"),
)


class FakeGeocoder:
    """Deterministic gazetteer of a few Pasto landmarks; no network."""

    def search(self, query: str, limit: int = MAX_RESULTS) -> list[GeocodeResult]:
        needle = clean_query(query).lower()
        matches = [item for item in GAZETTEER if needle in item[0].lower()]
        return [GeocodeResult(name, lat, lon, category) for name, lat, lon, category in matches[:limit]]
