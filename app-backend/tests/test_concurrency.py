"""Concurrency and idempotency of stock-changing operations, against the real (SQLite) database."""

import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.db import Base, SessionLocal, engine
from app.models import Lot, Product, Reservation, Shop, User
from app.services import (
    cancel_reservation,
    confirm_reservation_pickup,
    donate_lot,
    reserve_lot,
)

COMPETITOR_COUNT = 8
THREAD_JOIN_SECONDS = 30


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_lot(quantity: int, customers: int, expires_in: timedelta = timedelta(days=1)) -> tuple[int, list[int]]:
    with SessionLocal() as db:
        owner = User(email="owner@example.com", password_hash="x", role="business")
        db.add(owner)
        db.flush()
        shop = Shop(owner_id=owner.id, name="Bakery", description="", latitude=4.7, longitude=-74.0)
        db.add(shop)
        db.flush()
        product = Product(shop_id=shop.id, name="Bread", description="", category="bakery")
        db.add(product)
        db.flush()
        lot = Lot(
            shop_id=shop.id,
            product_id=product.id,
            title="Bread bag",
            quantity=quantity,
            original_price_cents=1000,
            discount_percent=30,
            expires_at=datetime.now(timezone.utc) + expires_in,
        )
        db.add(lot)
        customer_rows = [
            User(email=f"customer{i}@example.com", password_hash="x", role="customer") for i in range(customers)
        ]
        db.add_all(customer_rows)
        db.commit()
        return lot.id, [row.id for row in customer_rows]


Outcome = tuple[str, object]


def race(actions: list[Callable[[], object]]) -> list[Outcome]:
    """Run every action in its own thread, released at the same moment."""
    barrier = threading.Barrier(len(actions))
    outcomes: list[Outcome] = [("pending", None)] * len(actions)

    def worker(index: int, action: Callable[[], object]) -> None:
        barrier.wait()
        try:
            outcomes[index] = ("ok", action())
        except HTTPException as exc:
            outcomes[index] = ("rejected", exc.status_code)

    threads = [threading.Thread(target=worker, args=(i, action)) for i, action in enumerate(actions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(THREAD_JOIN_SECONDS)
    return outcomes


def reserve_as(lot_id: int, user_id: int, quantity: int = 1) -> Callable[[], object]:
    def action() -> object:
        with SessionLocal() as db:
            return reserve_lot(db, lot_id, user_id, quantity).id

    return action


def lot_state(lot_id: int) -> tuple[int, str]:
    with SessionLocal() as db:
        lot = db.get(Lot, lot_id)
        assert lot is not None
        return lot.quantity, lot.status


def count(outcomes: list[Outcome], kind: str) -> int:
    return sum(1 for outcome, _ in outcomes if outcome == kind)


def test_only_one_customer_gets_the_last_unit():
    lot_id, customers = seed_lot(quantity=1, customers=2)

    outcomes = race([reserve_as(lot_id, customers[0]), reserve_as(lot_id, customers[1])])

    assert count(outcomes, "ok") == 1
    assert count(outcomes, "rejected") == 1
    assert lot_state(lot_id) == (0, "sold_out")


def test_stock_never_goes_negative_when_many_customers_compete():
    stock = 3
    lot_id, customers = seed_lot(quantity=stock, customers=COMPETITOR_COUNT)

    outcomes = race([reserve_as(lot_id, user_id) for user_id in customers])

    assert count(outcomes, "ok") == stock
    assert count(outcomes, "rejected") == COMPETITOR_COUNT - stock
    assert lot_state(lot_id) == (0, "sold_out")
    with SessionLocal() as db:
        assert db.query(Reservation).filter(Reservation.lot_id == lot_id).count() == stock


def test_a_reservation_and_a_donation_never_allocate_the_same_unit():
    lot_id, customers = seed_lot(quantity=1, customers=1)

    def donate() -> object:
        with SessionLocal() as db:
            return donate_lot(db, lot_id, 1).id

    outcomes = race([reserve_as(lot_id, customers[0]), donate])

    assert count(outcomes, "ok") == 1
    assert count(outcomes, "rejected") == 1
    assert lot_state(lot_id)[0] == 0


def reserve_one(lot_id: int, user_id: int) -> tuple[int, str]:
    with SessionLocal() as db:
        reservation = reserve_lot(db, lot_id, user_id, 1)
        return reservation.id, reservation.pickup_code


def confirm(reservation_id: int, code: str) -> Callable[[], object]:
    def action() -> object:
        with SessionLocal() as db:
            return confirm_reservation_pickup(db, reservation_id, code).status

    return action


def test_confirming_a_pickup_twice_is_rejected_and_changes_nothing():
    lot_id, customers = seed_lot(quantity=2, customers=1)
    reservation_id, code = reserve_one(lot_id, customers[0])

    first = race([confirm(reservation_id, code)])
    second = race([confirm(reservation_id, code)])

    assert first == [("ok", "picked_up")]
    assert second == [("rejected", 409)]
    assert lot_state(lot_id) == (1, "active")


def test_simultaneous_pickup_confirmations_succeed_exactly_once():
    lot_id, customers = seed_lot(quantity=2, customers=1)
    reservation_id, code = reserve_one(lot_id, customers[0])

    outcomes = race([confirm(reservation_id, code) for _ in range(4)])

    assert count(outcomes, "ok") == 1
    assert count(outcomes, "rejected") == 3


def test_an_expired_lot_rejects_reservations_even_if_the_expiry_job_has_not_run():
    lot_id, customers = seed_lot(quantity=5, customers=1, expires_in=timedelta(minutes=-1))

    outcomes = race([reserve_as(lot_id, customers[0])])

    assert outcomes == [("rejected", 404)]
    with SessionLocal() as db:
        lot = db.get(Lot, lot_id)
        assert lot is not None and lot.status == "active" and lot.quantity == 5


def test_simultaneous_cancellations_give_the_stock_back_only_once():
    lot_id, customers = seed_lot(quantity=2, customers=1)
    reservation_id, _code = reserve_one(lot_id, customers[0])
    assert lot_state(lot_id) == (1, "active")

    def cancel() -> object:
        with SessionLocal() as db:
            return cancel_reservation(db, reservation_id, customers[0]).status

    outcomes = race([cancel for _ in range(4)])

    assert count(outcomes, "ok") == 1
    assert count(outcomes, "rejected") == 3
    assert lot_state(lot_id) == (2, "active")
