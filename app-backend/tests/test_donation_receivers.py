import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import auth_headers, reset_db

from app import main
from app.application.dto import Actor
from app.application.use_cases.donation_offers import RespondToDonationOffer
from app.db import SessionLocal
from app.domain.exceptions import DonationOfferStateError, ReceiverInvalidError
from app.domain.receivers import (
    DonationLot,
    OfferStatus,
    Receiver,
    ReceiverExclusion,
    assess_receiver,
    rank_receivers,
)
from app.infrastructure.repositories.donation_repository import (
    SqlAlchemyDonationRepository,
)
from app.infrastructure.repositories.rescue_plan_repository import SqlAlchemyUnitOfWork

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
RADIUS_KM = 15.0


def receiver(receiver_id: int = 1, **overrides) -> Receiver:
    fields = {
        "id": receiver_id,
        "owner_user_id": receiver_id,
        "name": "Community kitchen",
        "latitude": 4.7,
        "longitude": -74.0,
        "accepted_categories": frozenset({"bakery", "dairy"}),
        "max_quantity": 50,
        "can_store_refrigerated": True,
        "open_from_minute": 0,
        "open_until_minute": 1440,
        "utc_offset_minutes": 0,
        **overrides,
    }
    return Receiver(**fields)


def lot(category: str = "bakery", **overrides) -> DonationLot:
    fields = {
        "lot_id": 1,
        "shop_id": 1,
        "owner_id": 1,
        "title": "Bread bag",
        "category": category,
        "available_quantity": 20,
        "status": "active",
        "closes_at": NOW + timedelta(hours=6),
        "latitude": 4.7,
        "longitude": -74.0,
        **overrides,
    }
    return DonationLot(**fields)


def assess(candidate: Receiver, target: DonationLot, quantity: int = 5, recent: int = 0):
    return assess_receiver(candidate, target, quantity, NOW, recent, RADIUS_KM)


# ---- domain rules ----


def test_a_compatible_receiver_has_no_exclusion_reasons():
    assert assess(receiver(), lot()).compatible


def test_each_hard_constraint_excludes_a_receiver():
    assert assess(receiver(), lot("meat")).reasons == (ReceiverExclusion.CATEGORY_NOT_ACCEPTED,)
    assert ReceiverExclusion.OVER_CAPACITY in assess(receiver(max_quantity=3), lot(), quantity=5).reasons
    assert assess(receiver(can_store_refrigerated=False), lot("dairy")).reasons == (
        ReceiverExclusion.NEEDS_REFRIGERATION,
    )
    assert ReceiverExclusion.TOO_FAR in assess(receiver(latitude=5.5), lot()).reasons


def test_a_receiver_that_is_closed_for_the_whole_pickup_period_is_excluded():
    only_morning = receiver(open_from_minute=6 * 60, open_until_minute=9 * 60)

    assessment = assess(only_morning, lot(closes_at=NOW + timedelta(hours=1)))

    assert assessment.reasons == (ReceiverExclusion.CLOSED_BEFORE_PICKUP,)


def test_opening_hours_are_read_in_the_receivers_own_utc_offset():
    local_nine_to_five = receiver(open_from_minute=9 * 60, open_until_minute=17 * 60, utc_offset_minutes=-300)

    assert local_nine_to_five.is_open_during(NOW, NOW + timedelta(hours=4))
    assert not local_nine_to_five.is_open_during(NOW, NOW + timedelta(hours=1))


def test_receivers_who_received_fewer_recent_donations_come_first_then_the_nearest():
    busy = assess(receiver(1), lot(), recent=3)
    far_but_fair = assess(receiver(2, latitude=4.75), lot(), recent=0)
    near_and_fair = assess(receiver(3, latitude=4.71), lot(), recent=0)
    incompatible = assess(receiver(4, accepted_categories=frozenset({"meat"})), lot())

    ordered = rank_receivers([busy, far_but_fair, incompatible, near_and_fair])

    assert [item.receiver.id for item in ordered] == [3, 2, 1]


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": " "},
        {"accepted_categories": frozenset()},
        {"max_quantity": 0},
        {"open_from_minute": 600, "open_until_minute": 600},
        {"utc_offset_minutes": 900},
        {"latitude": 91.0},
    ],
)
def test_an_invalid_receiver_profile_is_rejected(overrides):
    with pytest.raises(ReceiverInvalidError):
        receiver(**overrides)


# ---- HTTP flow ----

RECEIVER_BODY = {
    "name": "Community kitchen",
    "latitude": 4.7,
    "longitude": -74.0,
    "accepted_categories": ["bakery"],
    "max_quantity": 50,
    "can_store_refrigerated": False,
    "open_from": "00:00",
    "open_until": "24:00",
    "utc_offset_minutes": 0,
}


def seed_donatable_lot(client: TestClient, owner: dict[str, str], category: str = "bakery", quantity: int = 20) -> int:
    shop_id = client.post(
        "/api/v1/shops", json={"name": "Bakery", "description": "", "latitude": 4.7, "longitude": -74.0}, headers=owner
    ).json()["id"]
    product_id = client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Bread", "description": "", "category": category},
        headers=owner,
    ).json()["id"]
    response = client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop_id,
            "product_id": product_id,
            "title": "Bread bag",
            "quantity": quantity,
            "original_price_cents": 1000,
            "discount_percent": 20,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(),
        },
        headers=owner,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def setup_flow(quantity: int = 20):
    reset_db()
    main._rate_buckets.clear()
    client = TestClient(main.app)
    owner = auth_headers(client, "shop@example.com")
    lot_id = seed_donatable_lot(client, owner, quantity=quantity)
    receiver_headers = auth_headers(client, "kitchen@example.com", role="customer")
    assert client.post("/api/v1/receivers", json=RECEIVER_BODY, headers=receiver_headers).status_code == 201
    return client, owner, receiver_headers, lot_id


def make_offer(client: TestClient, owner, lot_id: int, quantity: int = 5) -> dict:
    candidates = client.get(
        f"/api/v1/lots/{lot_id}/donation-candidates", params={"quantity": quantity}, headers=owner
    ).json()
    response = client.post(
        f"/api/v1/lots/{lot_id}/donation-offers",
        json={"receiver_id": candidates["compatible"][0]["receiver"]["id"], "quantity": quantity, "message": "Hello"},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    return response.json()


def lot_quantity(client: TestClient, lot_id: int) -> int:
    return client.get(f"/api/v1/lots/{lot_id}").json()["quantity"]


def test_http_the_owner_sees_compatible_receivers_and_why_others_are_left_out():
    client, owner, receiver_headers, lot_id = setup_flow()
    other = {**RECEIVER_BODY, "name": "Dairy only", "accepted_categories": ["dairy"]}
    other_headers = auth_headers(client, "dairy@example.com", role="customer")
    client.post("/api/v1/receivers", json=other, headers=other_headers)

    body = client.get(f"/api/v1/lots/{lot_id}/donation-candidates", params={"quantity": 5}, headers=owner).json()

    assert body["approximate"] is True
    assert [item["receiver"]["name"] for item in body["compatible"]] == ["Community kitchen"]
    assert body["excluded"][0]["reasons"] == ["category_not_accepted"]


def test_http_an_offer_does_not_touch_stock_until_the_receiver_accepts():
    client, owner, receiver_headers, lot_id = setup_flow()

    offer = make_offer(client, owner, lot_id, quantity=5)

    assert offer["status"] == "offered"
    assert lot_quantity(client, lot_id) == 20


def test_http_accepting_commits_the_units_once_and_a_repeat_is_rejected():
    client, owner, receiver_headers, lot_id = setup_flow()
    offer = make_offer(client, owner, lot_id, quantity=5)

    first = client.post(f"/api/v1/donation-offers/{offer['id']}/accept", headers=receiver_headers)
    repeat = client.post(f"/api/v1/donation-offers/{offer['id']}/accept", headers=receiver_headers)

    assert first.status_code == 200 and first.json()["status"] == "accepted"
    assert repeat.status_code == 409
    assert repeat.json()["code"] == "donation_offer_state"
    assert lot_quantity(client, lot_id) == 15


def test_http_only_a_delivered_offer_counts_as_donated_impact():
    client, owner, receiver_headers, lot_id = setup_flow()
    shop_id = client.get("/api/v1/shops", headers=owner).json()[0]["id"]
    offer = make_offer(client, owner, lot_id, quantity=5)
    client.post(f"/api/v1/donation-offers/{offer['id']}/accept", headers=receiver_headers)
    assert client.get(f"/api/v1/shops/{shop_id}/impact", headers=owner).json()["donated_units"] == 0

    delivered = client.post(f"/api/v1/donation-offers/{offer['id']}/delivered", headers=owner)
    repeat = client.post(f"/api/v1/donation-offers/{offer['id']}/delivered", headers=owner)

    assert delivered.json()["status"] == "delivered"
    assert repeat.status_code == 409
    assert client.get(f"/api/v1/shops/{shop_id}/impact", headers=owner).json()["donated_units"] == 5


def test_http_declining_leaves_the_stock_untouched():
    client, owner, receiver_headers, lot_id = setup_flow()
    offer = make_offer(client, owner, lot_id, quantity=5)

    response = client.post(f"/api/v1/donation-offers/{offer['id']}/decline", headers=receiver_headers)

    assert response.json()["status"] == "declined"
    assert lot_quantity(client, lot_id) == 20


def test_http_another_account_cannot_answer_or_deliver_someone_elses_offer():
    client, owner, receiver_headers, lot_id = setup_flow()
    offer = make_offer(client, owner, lot_id, quantity=5)
    stranger = auth_headers(client, "stranger@example.com", role="customer")
    other_shop = auth_headers(client, "othershop@example.com")

    assert client.post(f"/api/v1/donation-offers/{offer['id']}/accept", headers=stranger).status_code == 404
    client.post(f"/api/v1/donation-offers/{offer['id']}/accept", headers=receiver_headers)
    assert client.post(f"/api/v1/donation-offers/{offer['id']}/delivered", headers=other_shop).status_code == 404
    assert client.post(f"/api/v1/donation-offers/{offer['id']}/delivered", headers=stranger).status_code == 403


def test_http_another_shop_cannot_offer_a_lot_it_does_not_own():
    client, owner, receiver_headers, lot_id = setup_flow()
    other_shop = auth_headers(client, "othershop@example.com")

    response = client.get(f"/api/v1/lots/{lot_id}/donation-candidates", params={"quantity": 1}, headers=other_shop)

    assert response.status_code == 404
    assert response.json()["code"] == "donation_lot_not_found"


def test_http_a_second_active_offer_for_the_same_lot_and_receiver_is_a_conflict():
    client, owner, receiver_headers, lot_id = setup_flow()
    make_offer(client, owner, lot_id, quantity=5)
    candidates = client.get(f"/api/v1/lots/{lot_id}/donation-candidates", params={"quantity": 2}, headers=owner).json()

    response = client.post(
        f"/api/v1/lots/{lot_id}/donation-offers",
        json={"receiver_id": candidates["compatible"][0]["receiver"]["id"], "quantity": 2},
        headers=owner,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "donation_offer_conflict"


def test_http_accepting_after_the_units_were_sold_fails_and_leaves_the_offer_open():
    client, owner, receiver_headers, lot_id = setup_flow(quantity=3)
    offer = make_offer(client, owner, lot_id, quantity=3)
    customer = auth_headers(client, "customer@example.com", role="customer")
    assert client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 1}, headers=customer).status_code == 201

    response = client.post(f"/api/v1/donation-offers/{offer['id']}/accept", headers=receiver_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "donation_stock_unavailable"
    offers = client.get("/api/v1/receivers/me/offers", headers=receiver_headers).json()
    assert offers[0]["status"] == "offered"
    assert lot_quantity(client, lot_id) == 2


def test_http_an_incompatible_receiver_cannot_be_offered_the_lot():
    client, owner, _receiver_headers, lot_id = setup_flow()
    dairy_only = auth_headers(client, "dairy@example.com", role="customer")
    created = client.post(
        "/api/v1/receivers",
        json={**RECEIVER_BODY, "name": "Dairy only", "accepted_categories": ["dairy"]},
        headers=dairy_only,
    ).json()

    response = client.post(
        f"/api/v1/lots/{lot_id}/donation-offers",
        json={"receiver_id": created["id"], "quantity": 2},
        headers=owner,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "donation_receiver_incompatible"


def test_http_an_account_has_at_most_one_receiver_profile():
    client, _owner, receiver_headers, _lot_id = setup_flow()

    response = client.post("/api/v1/receivers", json=RECEIVER_BODY, headers=receiver_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "receiver_already_exists"


def test_http_the_offer_message_is_drafted_by_the_language_model_for_the_owner_to_review():
    client, owner, _receiver_headers, lot_id = setup_flow()
    receiver_id = client.get(
        f"/api/v1/lots/{lot_id}/donation-candidates", params={"quantity": 2}, headers=owner
    ).json()["compatible"][0]["receiver"]["id"]

    response = client.post(
        f"/api/v1/lots/{lot_id}/donation-offers/draft",
        json={"receiver_id": receiver_id},
        params={"language": "es"},
        headers=owner,
    )

    assert response.status_code == 200
    assert "excedente" in response.json()["text"]
    assert not any(character.isdigit() for character in response.json()["text"])


# ---- concurrency ----


def test_simultaneous_acceptances_commit_the_units_exactly_once():
    client, owner, receiver_headers, lot_id = setup_flow()
    offer = make_offer(client, owner, lot_id, quantity=5)
    receiver_owner_id = client.get("/api/v1/auth/me", headers=receiver_headers).json()["id"]
    actor = Actor(user_id=receiver_owner_id, role="customer", is_admin=False)
    barrier = threading.Barrier(4)
    outcomes: list[str] = []

    def accept() -> None:
        with SessionLocal() as db:
            use_case = RespondToDonationOffer(SqlAlchemyDonationRepository(db), SqlAlchemyUnitOfWork(db))
            barrier.wait()
            try:
                use_case.execute(actor, offer["id"], True, datetime.now(timezone.utc))
                outcomes.append("ok")
            except DonationOfferStateError:
                outcomes.append("rejected")

    threads = [threading.Thread(target=accept) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["ok", "rejected", "rejected", "rejected"]
    assert lot_quantity(client, lot_id) == 15
    with SessionLocal() as db:
        stored = SqlAlchemyDonationRepository(db).get_offer(offer["id"])
        assert stored is not None and stored.status is OfferStatus.ACCEPTED
