from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.application.ai_dto import ExpiryDateRead
from app.db import Base, engine

image_buffer = BytesIO()
Image.new("RGB", (2, 2), "white").save(image_buffer, format="PNG")
IMAGE = image_buffer.getvalue()


class StorageStub:
    def upload(self, key: str, content: bytes, content_type: str) -> None:
        self.key = key

    def signed_url(self, key: str) -> str:
        return f"https://images.example/{key}"

    def download(self, key: str) -> tuple[bytes, str]:
        assert key == self.key
        return IMAGE, "image/png"


class ProviderStub:
    def __init__(self, result: ExpiryDateRead) -> None:
        self.result = result
        self.request: dict[str, object] = {}

    def generate_structured(self, **kwargs: object) -> ExpiryDateRead:
        self.request = kwargs
        return self.result


def register_business(email: str) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(main.app)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "role": "business"},
    )
    assert response.status_code == 201
    return client, {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_lot(client: TestClient, headers: dict[str, str]) -> int:
    shop = client.post(
        "/api/v1/shops",
        json={"name": "Expiry Shop", "latitude": 4.7, "longitude": -74.07},
        headers=headers,
    )
    assert shop.status_code == 201
    product = client.post(
        f"/api/v1/shops/{shop.json()['id']}/products",
        json={"name": "Fresh bread"},
        headers=headers,
    )
    assert product.status_code == 201
    lot = client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop.json()["id"],
            "product_id": product.json()["id"],
            "title": "Bread lot",
            "quantity": 5,
            "original_price_cents": 1000,
            "discount_percent": 20,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=headers,
    )
    assert lot.status_code == 201
    return lot.json()["id"]


def setup_api(monkeypatch, result: ExpiryDateRead, email: str):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    main._rate_buckets.clear()
    provider = ProviderStub(result)
    storage = StorageStub()
    monkeypatch.setattr(main, "get_storage", lambda: storage)
    monkeypatch.setattr(main, "build_client", lambda: provider)
    client, headers = register_business(email)
    lot_id = create_lot(client, headers)
    uploaded = client.post(
        f"/api/v1/lots/{lot_id}/image",
        files={"image": ("bread.png", IMAGE, "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    return client, headers, lot_id, provider


def test_expiry_scan_requires_explicit_confirmation_to_change_lot_date(monkeypatch) -> None:
    suggested_date = date.today() + timedelta(days=7)
    client, headers, lot_id, provider = setup_api(
        monkeypatch,
        ExpiryDateRead(printed_date="Best before", expires_on=suggested_date, confidence=0.97),
        "expiry-confirm@example.com",
    )
    original_expiry = client.get(f"/api/v1/lots/{lot_id}").json()["expires_at"]

    scan = client.post(f"/api/v1/lots/{lot_id}/expiry-scans?language=es", headers=headers)

    assert scan.status_code == 201
    assert scan.json()["status"] == "awaiting_confirmation"
    assert scan.json()["expires_on"] == suggested_date.isoformat()
    assert provider.request["locale"] == "es"
    assert provider.request["image_data"] != IMAGE
    assert provider.request["image_mime_type"] == "image/png"
    assert client.get(f"/api/v1/lots/{lot_id}").json()["expires_at"] == original_expiry

    confirmation = client.post(
        f"/api/v1/lots/{lot_id}/expiry-scans/{scan.json()['id']}/confirm",
        headers=headers,
    )

    assert confirmation.status_code == 200
    assert confirmation.json()["status"] == "confirmed"
    updated_expiry = datetime.fromisoformat(
        client.get(f"/api/v1/lots/{lot_id}").json()["expires_at"].replace("Z", "+00:00")
    )
    assert updated_expiry.date() == suggested_date


def test_unreadable_expiry_date_cannot_be_confirmed(monkeypatch) -> None:
    client, headers, lot_id, _ = setup_api(
        monkeypatch,
        ExpiryDateRead(printed_date=None, expires_on=None, confidence=0.1),
        "expiry-unreadable@example.com",
    )

    scan = client.post(f"/api/v1/lots/{lot_id}/expiry-scans", headers=headers)
    confirmation = client.post(
        f"/api/v1/lots/{lot_id}/expiry-scans/{scan.json()['id']}/confirm",
        headers=headers,
    )

    assert scan.status_code == 201
    assert scan.json()["status"] == "unreadable"
    assert confirmation.status_code == 409


def test_other_business_cannot_scan_lot_image(monkeypatch) -> None:
    client, _, lot_id, _ = setup_api(
        monkeypatch,
        ExpiryDateRead(printed_date=None, expires_on=None, confidence=0),
        "expiry-owner@example.com",
    )
    _, other_headers = register_business("expiry-other@example.com")

    response = client.post(f"/api/v1/lots/{lot_id}/expiry-scans", headers=other_headers)

    assert response.status_code == 404


def test_rejecting_expiry_suggestion_keeps_existing_date(monkeypatch) -> None:
    suggested_date = date.today() + timedelta(days=9)
    client, headers, lot_id, _ = setup_api(
        monkeypatch,
        ExpiryDateRead(printed_date="Use by", expires_on=suggested_date, confidence=0.92),
        "expiry-reject@example.com",
    )
    original_expiry = client.get(f"/api/v1/lots/{lot_id}").json()["expires_at"]
    scan = client.post(f"/api/v1/lots/{lot_id}/expiry-scans", headers=headers)

    rejection = client.post(
        f"/api/v1/lots/{lot_id}/expiry-scans/{scan.json()['id']}/reject",
        headers=headers,
    )

    assert rejection.status_code == 200
    assert rejection.json()["status"] == "rejected"
    assert client.get(f"/api/v1/lots/{lot_id}").json()["expires_at"] == original_expiry
