import httpx
import pytest

from app.domain.exceptions import GeocoderUnavailableError, GeocodingQueryInvalidError
from app.domain.geocoding import ATTRIBUTION, clean_query
from app.infrastructure.geocoding import FakeGeocoder, NominatimGeocoder

PAYLOAD = [
    {"display_name": "Plaza de Nariño, Pasto", "lat": "1.2145", "lon": "-77.2811", "category": "place"},
    {"display_name": "Sin coordenadas"},
]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def geocoder(handler, clock: Clock | None = None) -> tuple[NominatimGeocoder, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    clock = clock or Clock()
    client = httpx.Client(transport=httpx.MockTransport(respond))
    return NominatimGeocoder(client, "SobraCeroTest/1.0", clock=clock.time, sleep=clock.sleep), seen


def ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=PAYLOAD)


def test_the_query_is_cleaned_and_bounded():
    assert clean_query("  Plaza   de  Nariño ") == "Plaza de Nariño"
    for bad in ("ab", "  ", "x" * 121):
        with pytest.raises(GeocodingQueryInvalidError):
            clean_query(bad)


def test_the_request_identifies_the_app_is_limited_to_colombia_and_carries_no_autocomplete():
    service, seen = geocoder(ok)

    service.search("plaza de nariño")

    request = seen[0]
    assert request.headers["User-Agent"] == "SobraCeroTest/1.0"
    assert request.url.params["countrycodes"] == "co"
    assert request.url.params["format"] == "jsonv2"
    assert request.url.params["q"] == "plaza de nariño"


def test_results_carry_attribution_and_incomplete_entries_are_dropped():
    service, _seen = geocoder(ok)

    results = service.search("plaza de nariño")

    assert [(r.display_name, r.latitude, r.longitude) for r in results] == [
        ("Plaza de Nariño, Pasto", 1.2145, -77.2811)
    ]
    assert results[0].attribution == ATTRIBUTION


def test_the_same_search_is_served_from_the_cache_without_a_second_request():
    service, seen = geocoder(ok)

    service.search("Plaza de Nariño")
    service.search("  plaza de nariño ")

    assert len(seen) == 1


def test_two_different_searches_are_spaced_at_least_one_second_apart():
    clock = Clock()
    service, seen = geocoder(ok, clock)

    service.search("plaza de nariño")
    service.search("universidad de nariño")

    assert len(seen) == 2
    assert clock.slept and clock.slept[0] == pytest.approx(1.0)


def test_a_provider_failure_becomes_a_typed_error_without_leaking_details():
    service, _seen = geocoder(lambda _request: httpx.Response(503, text="upstream secret detail"))

    with pytest.raises(GeocoderUnavailableError) as error:
        service.search("plaza de nariño")

    assert "secret" not in str(error.value)


def test_a_malformed_response_is_a_provider_failure():
    service, _seen = geocoder(lambda _request: httpx.Response(200, text="not json"))

    with pytest.raises(GeocoderUnavailableError):
        service.search("plaza de nariño")


def test_the_fake_geocoder_answers_from_a_small_gazetteer_without_network():
    results = FakeGeocoder().search("universidad")

    assert [r.display_name for r in results] == ["Universidad de Nariño, Pasto"]
    assert FakeGeocoder().search("zzzz nowhere") == []
