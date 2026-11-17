import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import (
    ADMIN,
    CUSTOMER,
    OTHER_BUSINESS,
    OWNER,
    FakeLots,
    auth_headers,
    make_snapshot,
    reset_db,
    seed_lot,
)

from app import main
from app.application.use_cases.lot_timeline import GetLotTimeline
from app.domain.exceptions import RescueLotNotFoundError, RescuePermissionError
from app.domain.timeline import (
    DonationRow,
    PlanEventRow,
    ReservationRow,
    TimelineEventKind,
    build_timeline,
)

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


# ---- domain ----


def test_the_timeline_orders_plan_decisions_reservations_pickups_and_donations():
    timeline = build_timeline(
        [PlanEventRow(1, "approved", at(5), "{}"), PlanEventRow(1, "generated", at(1), "{}")],
        [ReservationRow(2, "picked_up", at(10), at(30)), ReservationRow(1, "cancelled", at(15), at(20))],
        [DonationRow(3, at(25))],
    )

    assert [event.kind for event in timeline] == [
        TimelineEventKind.PLAN_GENERATED,
        TimelineEventKind.PLAN_APPROVED,
        TimelineEventKind.RESERVED,
        TimelineEventKind.RESERVED,
        TimelineEventKind.RESERVATION_CANCELLED,
        TimelineEventKind.DONATED,
        TimelineEventKind.PICKED_UP,
    ]


def test_an_applied_discount_keeps_its_percentage():
    timeline = build_timeline(
        [PlanEventRow(1, "discount_applied", at(1), json.dumps({"discount_percent": 30}))], [], []
    )

    assert timeline[0].kind is TimelineEventKind.DISCOUNT_APPLIED
    assert timeline[0].discount_percent == 30


def test_internal_plan_events_and_malformed_payloads_are_handled():
    timeline = build_timeline(
        [PlanEventRow(1, "superseded", at(1), "{}"), PlanEventRow(1, "discount_applied", at(2), "not json")], [], []
    )

    assert [event.kind for event in timeline] == [TimelineEventKind.DISCOUNT_APPLIED]
    assert timeline[0].discount_percent is None


def test_a_reservation_that_is_still_active_only_shows_the_reservation():
    timeline = build_timeline([], [ReservationRow(2, "reserved", at(1), None)], [])

    assert [event.kind for event in timeline] == [TimelineEventKind.RESERVED]
    assert timeline[0].units == 2


def test_older_reservations_without_a_status_time_fall_back_to_their_creation_time():
    timeline = build_timeline([], [ReservationRow(1, "picked_up", at(1), None)], [])

    assert timeline[-1].kind is TimelineEventKind.PICKED_UP
    assert timeline[-1].occurred_at == at(1)


def test_naive_datetimes_from_the_database_are_treated_as_utc():
    timeline = build_timeline([], [ReservationRow(1, "reserved", datetime(2026, 11, 10, 9, 0), None)], [])

    assert timeline[0].occurred_at.tzinfo is not None


# ---- use case ----


class FakeSource:
    def plan_events(self, lot_id: int) -> list[PlanEventRow]:
        return [PlanEventRow(1, "generated", at(1), "{}")]

    def reservations(self, lot_id: int) -> list[ReservationRow]:
        return []

    def donations(self, lot_id: int) -> list[DonationRow]:
        return []


def test_only_the_owner_and_admins_can_read_a_lot_timeline():
    use_case = GetLotTimeline(FakeLots(make_snapshot()), FakeSource())  # type: ignore[arg-type]

    assert len(use_case.execute(10, OWNER)) == 1
    assert len(use_case.execute(10, ADMIN)) == 1
    with pytest.raises(RescueLotNotFoundError):
        use_case.execute(10, OTHER_BUSINESS)
    with pytest.raises(RescuePermissionError):
        use_case.execute(10, CUSTOMER)


# ---- HTTP, real database ----


@pytest.fixture(autouse=True)
def reset_rate_limits():
    main._rate_buckets.clear()


def test_http_timeline_follows_the_decision_through_to_the_pickup():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=30)
    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=owner).json()
    client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=owner)
    buyer = auth_headers(client, "buyer@example.com", role="customer")
    booking = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 2}, headers=buyer).json()
    client.post(
        f"/api/v1/reservations/{booking['id']}/pickup", json={"pickup_code": booking["pickup_code"]}, headers=owner
    )

    response = client.get(f"/api/v1/lots/{lot_id}/timeline", headers=owner)

    events = response.json()
    assert response.status_code == 200
    assert [event["kind"] for event in events] == ["plan_generated", "plan_approved", "reserved", "picked_up"]
    assert events[2]["units"] == events[3]["units"] == 2
    assert events[3]["occurred_at"] >= events[2]["occurred_at"]


def test_http_timeline_never_exposes_who_reserved_or_the_pickup_code():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=0)
    buyer = auth_headers(client, "secret-buyer@example.com", role="customer")
    booking = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 1}, headers=buyer).json()

    body = client.get(f"/api/v1/lots/{lot_id}/timeline", headers=owner).text

    assert "secret-buyer" not in body
    assert booking["pickup_code"] not in body
    assert "user" not in body


def test_http_timeline_records_cancellations_with_their_own_time():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=0)
    buyer = auth_headers(client, "buyer@example.com", role="customer")
    booking = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 1}, headers=buyer).json()
    client.post(f"/api/v1/reservations/{booking['id']}/cancel", headers=buyer)

    kinds = [event["kind"] for event in client.get(f"/api/v1/lots/{lot_id}/timeline", headers=owner).json()]

    assert kinds == ["reserved", "reservation_cancelled"]


def test_http_timeline_is_private_to_the_shop_owner():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    other = auth_headers(client, "other@example.com")
    customer = auth_headers(client, "customer@example.com", role="customer")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=0)
    url = f"/api/v1/lots/{lot_id}/timeline"

    assert client.get(url, headers=other).status_code == 404
    assert client.get(url, headers=customer).status_code == 403
    assert client.get(url).status_code == 401
