import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import auth_headers, reset_db, seed_lot

from app import main
from app.application.dto import Actor
from app.application.use_cases.shop_impact import GetShopImpact
from app.domain.exceptions import RescueLotNotFoundError, RescuePermissionError
from app.domain.impact import ReservationOutcome, summarize_impact

OWNER = Actor(user_id=1, role="business", is_admin=False)
OTHER = Actor(user_id=2, role="business", is_admin=False)
CUSTOMER = Actor(user_id=3, role="customer", is_admin=False)
ADMIN = Actor(user_id=9, role="customer", is_admin=True)


def outcome(status: str, units: int, price: int = 1000, discount: int = 20) -> ReservationOutcome:
    return ReservationOutcome(status=status, units=units, original_price_cents=price, discount_percent=discount)


# ---- domain ----


def test_only_picked_up_units_count_as_rescued_and_priced():
    impact = summarize_impact(
        [outcome("picked_up", 2), outcome("reserved", 5), outcome("cancelled", 3), outcome("expired", 1)],
        donated_units=4,
    )

    assert (impact.picked_up_units, impact.pending_units, impact.cancelled_units, impact.expired_units) == (2, 5, 3, 1)
    assert impact.donated_units == 4
    assert impact.estimated_revenue_cents == 2 * 800
    assert impact.estimated_savings_cents == 2 * 200


def test_each_lot_is_priced_with_its_own_discount():
    impact = summarize_impact(
        [outcome("picked_up", 1, price=1000, discount=50), outcome("picked_up", 1, price=2000, discount=0)], 0
    )

    assert impact.estimated_revenue_cents == 500 + 2000
    assert impact.estimated_savings_cents == 500


def test_a_shop_without_activity_has_zero_impact():
    impact = summarize_impact([], 0)

    assert (impact.picked_up_units, impact.donated_units, impact.estimated_revenue_cents) == (0, 0, 0)


# ---- use case ----


class FakeLots:
    def get_shop_owner_id(self, shop_id: int) -> int | None:
        return 1 if shop_id == 10 else None


class FakeImpact:
    def reservation_outcomes(self, shop_id: int) -> list[ReservationOutcome]:
        return [outcome("picked_up", 3)]

    def donated_units(self, shop_id: int) -> int:
        return 1


def build_use_case() -> GetShopImpact:
    return GetShopImpact(FakeLots(), FakeImpact())  # type: ignore[arg-type]


def test_the_owner_and_admins_can_read_the_impact():
    use_case = build_use_case()

    assert use_case.execute(10, OWNER).picked_up_units == 3
    assert use_case.execute(10, ADMIN).donated_units == 1


def test_other_shops_are_hidden_and_customers_are_blocked():
    use_case = build_use_case()

    with pytest.raises(RescueLotNotFoundError):
        use_case.execute(10, OTHER)
    with pytest.raises(RescueLotNotFoundError):
        use_case.execute(404, OWNER)
    with pytest.raises(RescuePermissionError):
        use_case.execute(10, CUSTOMER)


# ---- HTTP, real database ----


@pytest.fixture(autouse=True)
def reset_rate_limits():
    main._rate_buckets.clear()


def reserve(client: TestClient, lot_id: int, email: str, quantity: int) -> dict:
    headers = auth_headers(client, email, role="customer")
    response = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": quantity}, headers=headers)
    assert response.status_code == 201, response.text
    return {**response.json(), "headers": headers}


def test_http_impact_separates_pickups_donations_cancellations_and_pending():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=0, quantity=10)
    picked = reserve(client, lot_id, "picked@example.com", 2)
    cancelled = reserve(client, lot_id, "cancelled@example.com", 3)
    reserve(client, lot_id, "pending@example.com", 1)

    pickup = client.post(
        f"/api/v1/reservations/{picked['id']}/pickup", json={"pickup_code": picked["pickup_code"]}, headers=owner
    )
    cancel = client.post(f"/api/v1/reservations/{cancelled['id']}/cancel", headers=cancelled["headers"])
    donate = client.post(f"/api/v1/lots/{lot_id}/donate", json={"quantity": 2}, headers=owner)
    assert (pickup.status_code, cancel.status_code, donate.status_code) == (200, 200, 201)

    impact = client.get(f"/api/v1/shops/{shop_id}/impact", headers=owner).json()

    assert impact == {
        "picked_up_units": 2,
        "donated_units": 2,
        "pending_units": 1,
        "cancelled_units": 3,
        "expired_units": 0,
        "estimated_revenue_cents": 2 * 800,
        "estimated_savings_cents": 2 * 200,
    }


def test_http_a_repeated_pickup_is_not_counted_twice():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=0, quantity=5)
    booking = reserve(client, lot_id, "customer@example.com", 2)
    body = {"pickup_code": booking["pickup_code"]}

    first = client.post(f"/api/v1/reservations/{booking['id']}/pickup", json=body, headers=owner)
    second = client.post(f"/api/v1/reservations/{booking['id']}/pickup", json=body, headers=owner)

    assert (first.status_code, second.status_code) == (200, 409)
    assert client.get(f"/api/v1/shops/{shop_id}/impact", headers=owner).json()["picked_up_units"] == 2


def test_http_impact_is_private_to_the_shop_owner():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    other = auth_headers(client, "other@example.com")
    customer = auth_headers(client, "customer@example.com", role="customer")
    shop_id, _product_id, _lot_id = seed_lot(client, owner, history_days=0)

    assert client.get(f"/api/v1/shops/{shop_id}/impact", headers=other).status_code == 404
    assert client.get(f"/api/v1/shops/{shop_id}/impact", headers=customer).status_code == 403
    assert client.get(f"/api/v1/shops/{shop_id}/impact").status_code == 401
