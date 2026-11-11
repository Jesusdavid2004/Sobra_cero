import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import auth_headers, reset_db, seed_lot

from app import main
from app.application.use_cases.get_public_shop import GetPublicShop
from app.domain.exceptions import ShopNotFoundError
from app.domain.public_shop import PublicShop

SHOP = PublicShop(1, "Bakery", "Fresh bread", "restaurant", 4.7, -74.0)


class FakeShops:
    def get(self, shop_id: int) -> PublicShop | None:
        return SHOP if shop_id == 1 else None


def test_a_public_shop_is_returned_by_id():
    assert GetPublicShop(FakeShops()).execute(1) == SHOP  # type: ignore[arg-type]


def test_an_unknown_shop_is_reported_as_not_found():
    with pytest.raises(ShopNotFoundError):
        GetPublicShop(FakeShops()).execute(2)  # type: ignore[arg-type]


def test_http_the_profile_is_public_and_exposes_no_owner_data():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "private-owner@example.com")
    shop_id, _product_id, _lot_id = seed_lot(client, owner, history_days=0)

    response = client.get(f"/api/v1/public/shops/{shop_id}")

    assert response.status_code == 200
    assert set(response.json()) == {"id", "name", "description", "business_type", "latitude", "longitude"}
    assert "private-owner" not in response.text


def test_http_an_unknown_shop_uses_the_error_contract():
    reset_db()
    client = TestClient(main.app)

    response = client.get("/api/v1/public/shops/999")

    assert response.status_code == 404
    assert response.json() == {"code": "shop_not_found", "message_key": "errors.shop_not_found"}
