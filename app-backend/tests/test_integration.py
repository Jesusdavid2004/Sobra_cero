from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.main as main
from app.db import Base, engine


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def register_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(main.app)
    response = client.post("/api/v1/auth/register", json={"email": "shop@example.com", "password": "password123"})
    assert response.status_code == 201
    token = response.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def create_lot(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/shops",
        json={"name": "Green Grocer", "description": "Fresh surplus", "latitude": 4.7, "longitude": -74.07},
        headers=headers,
    )
    assert response.status_code == 201
    shop_id = response.json()["id"]

    response = client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Fruit box", "description": "Seasonal fruits"},
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
    client, headers = register_client()
    lot_id = create_lot(client, headers)

    lots = client.get("/api/v1/lots").json()
    assert any(lot["id"] == lot_id for lot in lots)

    response = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 3}, headers=headers)
    assert response.status_code == 201

    detail = client.get(f"/api/v1/lots/{lot_id}").json()
    assert detail["quantity"] == 7


def test_reservation_fails_when_quantity_exhausted():
    reset_db()
    client, headers = register_client()
    lot_id = create_lot(client, headers)

    response = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 99}, headers=headers)
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
