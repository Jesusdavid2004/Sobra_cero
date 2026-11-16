from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import auth_headers, reset_db

from app import dependencies, main
from app.config import settings
from app.db import SessionLocal
from app.domain.exceptions import GeocoderUnavailableError
from app.domain.external_data import ExternalBusinessRecord, ExternalProductRecord
from app.domain.places import PlaceCategory
from app.infrastructure.repositories.external_data_repository import (
    SqlAlchemyExternalDataRepository,
)
from app.models_external import ExternalBusinessRow, ExternalSourceRow
from app.presentation import rate_limit

NOW = datetime.now(timezone.utc)
PASTO = (1.2136, -77.2811)


def business(name: str, external_id: str, latitude: float = 1.2140, longitude: float = -77.2800, **extra):
    return ExternalBusinessRecord(
        "osm", external_id, name, extra.get("category", PlaceCategory.BAKERY), latitude, longitude,
        "Calle 18", "Pasto", "", "", "", "https://www.openstreetmap.org/node/1", NOW,
    )  # fmt: skip


def product(name: str, price: int, original: int | None, seen_at: datetime):
    discount = round((1 - price / original) * 100) if original else 0
    return ExternalProductRecord(
        "catalog",
        name,
        "Panadería",
        f"https://tienda.example/{name}",
        price,
        original,
        discount,
        "InStock",
        "Tienda",
        seen_at,
    )


@pytest.fixture
def client(monkeypatch):
    reset_db()
    main._rate_buckets.clear()
    rate_limit.buckets.clear()
    monkeypatch.setattr(settings, "geocoder_provider", "fake")
    return TestClient(main.app)


def seed_world(client: TestClient) -> None:
    owner = auth_headers(client, "shop@example.com")
    shop = client.post(
        "/api/v1/shops",
        json={"name": "Green Bakery", "description": "", "latitude": PASTO[0], "longitude": PASTO[1]},
        headers=owner,
    ).json()
    unset = client.post(
        "/api/v1/shops", json={"name": "No location", "description": "", "latitude": 0, "longitude": 0}, headers=owner
    ).json()
    product_id = client.post(
        f"/api/v1/shops/{shop['id']}/products", json={"name": "Bread", "description": ""}, headers=owner
    ).json()["id"]
    client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop["id"],
            "product_id": product_id,
            "title": "Bread bag",
            "quantity": 5,
            "original_price_cents": 1000,
            "discount_percent": 20,
            "expires_at": (NOW + timedelta(hours=6)).isoformat(),
        },
        headers=owner,
    )
    assert unset["id"]
    with SessionLocal() as db:
        osm = ExternalSourceRow(key="osm", name="OpenStreetMap", kind="overpass")
        demo = ExternalSourceRow(key="demo", name="Demo", kind="demo")
        catalog = ExternalSourceRow(key="catalog", name="Catalog", kind="jsonld_catalog")
        db.add_all([osm, demo, catalog])
        db.flush()
        repository = SqlAlchemyExternalDataRepository(db)
        repository.upsert_business(osm, business("Panadería El Trigo", "node/1"))
        repository.upsert_business(osm, business("Restaurante La Plaza", "node/2", category=PlaceCategory.RESTAURANT))
        repository.upsert_business(osm, business("Cafe Rechazado", "node/3", latitude=1.2200))
        repository.upsert_business(demo, business("Tienda de demostración", "demo/1", latitude=1.2250))
        repository.upsert_product(catalog, product("pan-oferta", 4990, 7990, NOW))
        repository.upsert_product(catalog, product("leche", 4500, None, NOW))
        repository.upsert_product(catalog, product("pan-viejo", 3000, 6000, NOW - timedelta(days=5)))
        db.query(ExternalBusinessRow).filter(ExternalBusinessRow.name == "Cafe Rechazado").update(
            {"verification_status": "rejected"}
        )
        db.commit()


def places(client: TestClient, **params) -> list[dict]:
    response = client.get("/api/v1/map/places", params=params)
    assert response.status_code == 200, response.text
    return response.json()["places"]


def test_affiliated_shops_and_discovered_businesses_are_kept_visibly_apart(client):
    seed_world(client)

    found = places(client)

    by_name = {place["name"]: place for place in found}
    assert by_name["Green Bakery"]["affiliation"] == "affiliated"
    assert by_name["Green Bakery"]["offer_count"] == 1
    assert by_name["Panadería El Trigo"]["affiliation"] == "discovered"
    assert by_name["Panadería El Trigo"]["verified"] is False
    assert {p["affiliation"] for p in found if p["place_id"].startswith("ext:")} == {"discovered"}


def test_a_shop_without_a_location_and_a_rejected_business_are_not_shown(client):
    seed_world(client)

    names = {place["name"] for place in places(client)}

    assert "No location" not in names and "Cafe Rechazado" not in names


def test_demonstration_data_is_excluded_unless_asked_for_and_is_flagged(client):
    seed_world(client)

    assert "Tienda de demostración" not in {p["name"] for p in places(client)}
    demo = [p for p in places(client, include_demo=True) if p["name"] == "Tienda de demostración"]
    assert demo and demo[0]["is_demo"] is True


def test_layers_categories_and_accent_insensitive_text_filter_the_results(client):
    seed_world(client)

    assert {p["affiliation"] for p in places(client, layer="discovered")} == {"discovered"}
    assert [p["name"] for p in places(client, layer="discovered", category="restaurant")] == ["Restaurante La Plaza"]
    assert [p["name"] for p in places(client, layer="discovered", q="panaderia")] == ["Panadería El Trigo"]


def test_only_affiliated_shops_with_live_offers_are_returned_when_asked(client):
    seed_world(client)

    assert [p["name"] for p in places(client, only_with_offers=True)] == ["Green Bakery"]


def test_a_bounding_box_limits_the_area_and_an_invalid_one_uses_the_error_contract(client):
    seed_world(client)

    assert places(client, south=4.0, west=-74.2, north=4.1, east=-74.0) == []
    invalid = client.get("/api/v1/map/places", params={"south": 2, "west": -77, "north": 1, "east": -76})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "place_invalid"


def test_osm_attribution_is_present_only_when_externally_sourced_places_are_shown(client):
    seed_world(client)

    with_osm = client.get("/api/v1/map/places").json()
    only_shops = client.get("/api/v1/map/places", params={"layer": "affiliated"}).json()

    assert with_osm["attribution"] == "© OpenStreetMap contributors"
    assert only_shops["attribution"] == ""


def test_opportunities_count_verifiable_records_and_flag_places_to_invite(client):
    seed_world(client)

    cells = client.get("/api/v1/map/opportunities").json()

    total = {
        key: sum(cell[key] for cell in cells) for key in ("affiliated_shops", "live_offers", "discovered_businesses")
    }
    assert total == {"affiliated_shops": 1, "live_offers": 1, "discovered_businesses": 2}
    assert all(
        cell["somewhere_to_invite"]
        is (cell["affiliated_shops"] == 0 and cell["live_offers"] == 0 and cell["discovered_businesses"] > 0)
        for cell in cells
    )


def test_public_promotions_list_only_fresh_discounted_products(client):
    seed_world(client)

    promotions = client.get("/api/v1/map/promotions").json()

    assert [(p["name"], p["discount_percent"]) for p in promotions] == [("pan-oferta", 38)]


def test_a_place_search_returns_results_with_attribution(client):
    response = client.get("/api/v1/geo/search", params={"q": "universidad"})

    assert response.status_code == 200
    assert response.json()[0]["display_name"] == "Universidad de Nariño, Pasto"
    assert response.json()[0]["attribution"] == "© OpenStreetMap contributors"


def test_a_search_that_is_too_short_uses_the_error_contract(client):
    response = client.get("/api/v1/geo/search", params={"q": "ab"})

    assert response.status_code == 422
    assert response.json()["code"] == "geocoding_query_invalid"


def test_the_place_search_is_rate_limited_per_client(client):
    for _ in range(20):
        assert client.get("/api/v1/geo/search", params={"q": "plaza"}).status_code == 200

    blocked = client.get("/api/v1/geo/search", params={"q": "plaza"})

    assert blocked.status_code == 429
    assert blocked.json() == {"code": "rate_limited", "message_key": "errors.rate_limited"}


def test_a_geocoder_outage_is_a_503_without_provider_details(client, monkeypatch):
    class Down:
        def search(self, *_args, **_kwargs):
            raise GeocoderUnavailableError("upstream detail")

    monkeypatch.setattr(dependencies, "FakeGeocoder", Down)

    response = client.get("/api/v1/geo/search", params={"q": "plaza"})

    assert response.status_code == 503
    assert response.json()["code"] == "geocoder_unavailable"
    assert "upstream" not in response.text
