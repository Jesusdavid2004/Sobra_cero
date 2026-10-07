from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.main as main
from app.db import Base, engine


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def register_client(role: str = "business", email: str = "shop@example.com") -> tuple[TestClient, dict[str, str]]:
    client = TestClient(main.app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "role": role},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def create_lot(
    client: TestClient,
    headers: dict[str, str],
    *,
    business_type: str = "restaurant",
    category: str = "bakery",
) -> int:
    response = client.post(
        "/api/v1/shops",
        json={
            "name": "Green Grocer",
            "business_type": business_type,
            "description": "Fresh surplus",
            "latitude": 4.7,
            "longitude": -74.07,
        },
        headers=headers,
    )
    assert response.status_code == 201
    shop_id = response.json()["id"]

    response = client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Fruit box", "description": "Seasonal fruits", "category": category},
        headers=headers,
    )
    assert response.status_code == 201
    product_id = response.json()["id"]

    expires = (datetime.now(timezone.utc) + timedelta(hours=30)).isoformat()
    response = client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop_id,
            "product_id": product_id,
            "title": "Fruit rescue box",
            "description": "Almost expired fruits",
            "quantity": 10,
            "original_price_cents": 1500,
            "discount_percent": 40,
            "expires_at": expires,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_public_vitrine_and_reservation_flow():
    reset_db()
    client, business_headers = register_client()
    lot_id = create_lot(client, business_headers)

    lots = client.get("/api/v1/lots").json()
    assert any(lot["id"] == lot_id for lot in lots)

    _, customer_headers = register_client("customer", "customer@example.com")
    response = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 3}, headers=customer_headers)
    assert response.status_code == 201
    assert len(response.json()["pickup_code"]) == 8

    detail = client.get(f"/api/v1/lots/{lot_id}").json()
    assert detail["quantity"] == 7
    duplicate = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 1}, headers=customer_headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "batch_already_reserved"


def test_reservation_fails_when_quantity_exhausted():
    reset_db()
    client, business_headers = register_client()
    lot_id = create_lot(client, business_headers)
    _, customer_headers = register_client("customer", "customer@example.com")

    response = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 99}, headers=customer_headers)
    assert response.status_code == 409


def test_promos_generate_with_mock_client(monkeypatch):
    reset_db()
    client, headers = register_client()
    lot_id = create_lot(client, headers)

    def raise_(self=None, *args, **kwargs):
        raise RuntimeError("no broker in tests")

    monkeypatch.setattr(main, "generate_promotions_task", type("Task", (), {"delay": raise_})())

    response = client.post(f"/api/v1/lots/{lot_id}/generate-promos?language=es", headers=headers)
    assert response.status_code == 202

    promos = client.get(f"/api/v1/lots/{lot_id}/promos").json()
    assert len(promos) == 3
    assert all(promo["language"] == "es" for promo in promos)
    assert all(promo["prompt"] for promo in promos)


def test_upload_rejects_unsupported_type():
    reset_db()
    client, headers = register_client()
    lot_id = create_lot(client, headers)

    response = client.post(
        f"/api/v1/lots/{lot_id}/image",
        files={"image": ("notes.txt", b"not an image", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 415


def test_account_roles_restrict_business_actions():
    reset_db()
    client, business_headers = register_client()
    _, customer_headers = register_client("customer", "customer@example.com")

    shop_payload = {
        "name": "Green Grocer",
        "description": "Fresh surplus",
        "latitude": 4.7,
        "longitude": -74.07,
    }
    assert client.post("/api/v1/shops", json=shop_payload, headers=customer_headers).status_code == 403
    shop_response = client.post("/api/v1/shops", json=shop_payload, headers=business_headers)
    assert shop_response.status_code == 201
    assert shop_response.json()["business_type"] == "restaurant"
    lot_id = create_lot(client, business_headers)
    assert (
        client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 1}, headers=business_headers).status_code == 403
    )


def test_public_lot_filters_match_category_and_business_type():
    reset_db()
    client, business_headers = register_client()
    bakery_lot_id = create_lot(client, business_headers)
    produce_lot_id = create_lot(
        client,
        business_headers,
        business_type="supermarket",
        category="produce",
    )

    bakery_lots = client.get("/api/v1/lots?category=bakery&business_type=restaurant").json()
    produce_lots = client.get("/api/v1/lots?category=produce&business_type=supermarket").json()

    assert [lot["id"] for lot in bakery_lots] == [bakery_lot_id]
    assert [lot["id"] for lot in produce_lots] == [produce_lot_id]


def test_reservation_endpoint_is_rate_limited():
    reset_db()
    client, customer_headers = register_client("customer")
    main._rate_buckets.clear()

    for _ in range(10):
        response = client.post(
            "/api/v1/lots/999/reserve",
            json={"quantity": 1},
            headers=customer_headers,
        )
        assert response.status_code == 404

    limited_response = client.post(
        "/api/v1/lots/999/reserve",
        json={"quantity": 1},
        headers=customer_headers,
    )
    assert limited_response.status_code == 429
    main._rate_buckets.clear()
