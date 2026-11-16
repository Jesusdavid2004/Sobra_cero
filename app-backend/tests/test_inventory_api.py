from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import auth_headers, reset_db

from app import dependencies, main
from app.db import SessionLocal
from app.domain.exceptions import AIProviderUnavailableError, AIQuotaExceededError
from app.models import Lot

NOW = datetime.now(timezone.utc)


@pytest.fixture
def client():
    reset_db()
    main._rate_buckets.clear()
    return TestClient(main.app)


def shop_with_lot(client: TestClient, headers, quantity: int = 10, hours: float = 48) -> tuple[int, int]:
    shop_id = client.post(
        "/api/v1/shops",
        json={"name": "Bakery", "description": "", "latitude": 1.2, "longitude": -77.2},
        headers=headers,
    ).json()["id"]
    product_id = client.post(
        f"/api/v1/shops/{shop_id}/products", json={"name": "Bread", "description": ""}, headers=headers
    ).json()["id"]
    lot_id = client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop_id,
            "product_id": product_id,
            "title": "Bread bag",
            "quantity": quantity,
            "original_price_cents": 1000,
            "discount_percent": 20,
            "expires_at": (NOW + timedelta(hours=hours)).isoformat(),
        },
        headers=headers,
    ).json()["id"]
    return shop_id, lot_id


def lot_state(client: TestClient, lot_id: int) -> tuple[int, str]:
    body = client.get(f"/api/v1/lots/{lot_id}").json()
    return body["quantity"], body["status"]


def waste(client: TestClient, headers, lot_id: int, quantity: int, reason: str = "damaged", note: str = ""):
    return client.post(
        f"/api/v1/lots/{lot_id}/waste", json={"quantity": quantity, "reason": reason, "note": note}, headers=headers
    )


# ---- waste ----


def test_recording_waste_takes_the_units_out_of_the_lot(client):
    owner = auth_headers(client, "shop@example.com")
    _shop, lot_id = shop_with_lot(client, owner)

    response = waste(client, owner, lot_id, 3, note="  fell   off the shelf ")

    assert response.status_code == 201
    assert response.json() == {"lot_id": lot_id, "remaining_quantity": 7}
    assert lot_state(client, lot_id) == (7, "active")


def test_wasting_every_remaining_unit_closes_the_lot_for_sale(client):
    owner = auth_headers(client, "shop@example.com")
    _shop, lot_id = shop_with_lot(client, owner, quantity=4)

    waste(client, owner, lot_id, 4)

    assert lot_state(client, lot_id) == (0, "sold_out")


def test_more_units_than_the_lot_holds_is_rejected_with_a_reason_and_changes_nothing(client):
    owner = auth_headers(client, "shop@example.com")
    _shop, lot_id = shop_with_lot(client, owner, quantity=5)

    response = waste(client, owner, lot_id, 6)

    assert response.status_code == 422
    assert response.json()["code"] == "waste_invalid"
    assert response.json()["details"] == {"reason": "quantity_out_of_range"}
    assert lot_state(client, lot_id) == (5, "active")


def test_two_records_cannot_waste_more_than_the_lot_ever_held(client):
    owner = auth_headers(client, "shop@example.com")
    _shop, lot_id = shop_with_lot(client, owner, quantity=10)

    assert waste(client, owner, lot_id, 6).status_code == 201
    second = waste(client, owner, lot_id, 6)

    assert second.status_code == 422
    assert lot_state(client, lot_id) == (4, "active")


def test_units_of_an_expired_lot_can_still_be_recorded_as_waste(client):
    owner = auth_headers(client, "shop@example.com")
    _shop, lot_id = shop_with_lot(client, owner, quantity=6)
    with SessionLocal() as db:
        db.query(Lot).filter(Lot.id == lot_id).update({"status": "expired"})
        db.commit()

    response = waste(client, owner, lot_id, 6, reason="expired")

    assert response.status_code == 201
    assert lot_state(client, lot_id) == (0, "expired")


def test_only_the_owner_of_a_lot_can_record_its_waste(client):
    owner = auth_headers(client, "shop@example.com")
    _shop, lot_id = shop_with_lot(client, owner)
    other_shop = auth_headers(client, "other@example.com")
    customer = auth_headers(client, "customer@example.com", role="customer")

    stranger = waste(client, other_shop, lot_id, 1)
    forbidden = waste(client, customer, lot_id, 1)

    assert (stranger.status_code, stranger.json()["code"]) == (404, "waste_lot_not_found")
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "waste_permission_denied")
    assert lot_state(client, lot_id) == (10, "active")


def test_the_waste_a_shop_recorded_can_be_listed_newest_first(client):
    owner = auth_headers(client, "shop@example.com")
    shop_id, lot_id = shop_with_lot(client, owner)
    waste(client, owner, lot_id, 1, reason="damaged")
    waste(client, owner, lot_id, 2, reason="unsold", note="end of day")

    entries = client.get(f"/api/v1/shops/{shop_id}/waste", headers=owner).json()

    assert [(e["quantity"], e["reason"], e["note"]) for e in entries] == [
        (2, "unsold", "end of day"),
        (1, "damaged", ""),
    ]
    assert entries[0]["lot_title"] == "Bread bag"


def test_another_shops_waste_cannot_be_read(client):
    owner = auth_headers(client, "shop@example.com")
    shop_id, _lot = shop_with_lot(client, owner)
    other = auth_headers(client, "other@example.com")

    response = client.get(f"/api/v1/shops/{shop_id}/waste", headers=other)

    assert response.status_code == 404
    assert response.json()["code"] == "shop_not_found"


# ---- diagnosis ----


def diagnosis(client: TestClient, headers, shop_id: int, language: str = "en") -> dict:
    response = client.get(f"/api/v1/shops/{shop_id}/diagnosis", params={"language": language}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_shop_with_nothing_published_is_told_so_and_the_limits_are_stated(client):
    owner = auth_headers(client, "shop@example.com")
    shop_id = client.post(
        "/api/v1/shops", json={"name": "Empty", "description": "", "latitude": 1.2, "longitude": -77.2}, headers=owner
    ).json()["id"]

    body = diagnosis(client, owner, shop_id)

    assert body["alerts"] == ["nothing_published"]
    assert {"no_active_lots", "no_pickups_recorded", "no_waste_records", "forecast_not_included"} == set(
        body["limitations"]
    )
    assert body["facts"]["active_lots"] == 0
    assert set(body["data_used"]) == {"lots", "reservations", "donations", "waste_records"}


def test_the_diagnosis_counts_stock_waste_and_pending_pickups(client):
    owner = auth_headers(client, "shop@example.com")
    shop_id, lot_id = shop_with_lot(client, owner, quantity=10, hours=3)
    customer = auth_headers(client, "customer@example.com", role="customer")
    assert client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 2}, headers=customer).status_code == 201
    waste(client, owner, lot_id, 1)

    body = diagnosis(client, owner, shop_id)

    facts = body["facts"]
    assert (facts["active_lots"], facts["units_available"]) == (1, 7)
    assert (facts["units_expiring_soon"], facts["units_closing_soon"]) == (7, 7)
    assert (facts["wasted_units"], facts["pending_pickup_units"]) == (1, 2)
    assert {"expiring_soon", "stock_closing_soon", "waste_recorded", "pending_pickups"} <= set(body["alerts"])
    assert "no_waste_records" not in body["limitations"]


def test_the_narrative_is_worded_by_the_model_in_the_requested_language_without_numbers(client):
    owner = auth_headers(client, "shop@example.com")
    shop_id, _lot = shop_with_lot(client, owner)

    spanish = diagnosis(client, owner, shop_id, language="es")

    assert spanish["narrative_status"] == "ai"
    assert "alertas" in spanish["narrative"]
    assert not any(character.isdigit() for character in spanish["narrative"])


@pytest.mark.parametrize(
    ("error", "status"),
    [(AIProviderUnavailableError("down"), "unavailable"), (AIQuotaExceededError("quota"), "quota_exceeded")],
)
def test_the_diagnosis_still_works_when_the_model_cannot_answer(client, monkeypatch, error, status):
    class Broken:
        def generate_structured(self, **_kwargs):
            raise error

    monkeypatch.setattr(dependencies, "build_client", lambda: Broken())
    owner = auth_headers(client, "shop@example.com")
    shop_id, _lot = shop_with_lot(client, owner)

    body = diagnosis(client, owner, shop_id)

    assert (body["narrative"], body["narrative_status"]) == (None, status)
    assert body["facts"]["active_lots"] == 1


def test_only_the_owner_can_read_a_shops_diagnosis(client):
    owner = auth_headers(client, "shop@example.com")
    shop_id, _lot = shop_with_lot(client, owner)
    other = auth_headers(client, "other@example.com")
    customer = auth_headers(client, "customer@example.com", role="customer")

    assert client.get(f"/api/v1/shops/{shop_id}/diagnosis", headers=other).status_code == 404
    assert client.get(f"/api/v1/shops/{shop_id}/diagnosis", headers=customer).status_code == 403
    assert client.get(f"/api/v1/shops/{shop_id}/diagnosis").status_code == 401
