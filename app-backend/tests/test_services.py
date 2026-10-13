from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain.entities import BatchStatus, ReservationStatus
from app.domain.exceptions import BatchAlreadyReservedError
from app.models import Lot, Product, Reservation, Shop, User
from app.services import (
    cancel_reservation,
    confirm_reservation_pickup,
    expire_due_lots,
    reserve_lot,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(email="test@example.com", password_hash="hash")
    session.add(user)
    session.flush()
    shop = Shop(owner_id=user.id, name="Test shop", latitude=0, longitude=0)
    session.add(shop)
    session.flush()
    product = Product(shop_id=shop.id, name="Test product")
    session.add(product)
    session.flush()
    lot = Lot(
        shop_id=shop.id,
        product_id=product.id,
        title="Test lot",
        quantity=3,
        original_price_cents=100,
        discount_percent=20,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
    )
    session.add(lot)
    session.commit()
    yield session, user, lot
    session.close()


def test_reservation_reduces_quantity(db):
    session, user, lot = db
    reservation = reserve_lot(session, lot.id, user.id, 2)
    assert reservation.quantity == 2
    assert len(reservation.pickup_code) == 8
    assert session.get(Lot, lot.id).quantity == 1
    with pytest.raises(BatchAlreadyReservedError):
        reserve_lot(session, lot.id, user.id, 1)


def test_reservation_rejects_insufficient_quantity(db):
    session, user, lot = db
    with pytest.raises(HTTPException):
        reserve_lot(session, lot.id, user.id, 4)


def test_cancelled_reservation_restores_stock_and_can_be_rebooked(db):
    session, user, lot = db
    reservation = reserve_lot(session, lot.id, user.id, 2)

    cancelled = cancel_reservation(session, reservation.id, user.id)
    assert cancelled.status == ReservationStatus.CANCELLED.value
    assert session.get(Lot, lot.id).quantity == 3

    replacement = reserve_lot(session, lot.id, user.id, 1)
    assert replacement.status == ReservationStatus.RESERVED.value


def test_pickup_requires_valid_code_and_is_one_time(db):
    session, user, lot = db
    reservation = reserve_lot(session, lot.id, user.id, 2)

    with pytest.raises(HTTPException) as invalid_code:
        confirm_reservation_pickup(session, reservation.id, "BADCODE1")
    assert invalid_code.value.status_code == 404

    picked_up = confirm_reservation_pickup(session, reservation.id, reservation.pickup_code)
    assert picked_up.status == ReservationStatus.PICKED_UP.value
    with pytest.raises(HTTPException) as already_picked_up:
        confirm_reservation_pickup(session, reservation.id, reservation.pickup_code)
    assert already_picked_up.value.status_code == 409


def test_expiration_marks_lots_and_outstanding_reservations(db):
    session, user, lot = db
    reservation = reserve_lot(session, lot.id, user.id, 2)
    now = datetime.now(timezone.utc)
    lot.expires_at = now - timedelta(minutes=1)
    session.commit()

    assert expire_due_lots(session, now) == 1
    assert session.get(Lot, lot.id).status == BatchStatus.EXPIRED.value
    assert session.get(Reservation, reservation.id).status == ReservationStatus.EXPIRED.value


def test_concurrent_reservations_cannot_oversell(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reservation-race.db'}",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as session:
        owner = User(email="owner@example.com", password_hash="hash")
        first_customer = User(email="first@example.com", password_hash="hash", role="customer")
        second_customer = User(email="second@example.com", password_hash="hash", role="customer")
        session.add_all([owner, first_customer, second_customer])
        session.flush()
        shop = Shop(owner_id=owner.id, name="Test shop", latitude=0, longitude=0)
        session.add(shop)
        session.flush()
        product = Product(shop_id=shop.id, name="Test product")
        session.add(product)
        session.flush()
        lot = Lot(
            shop_id=shop.id,
            product_id=product.id,
            title="Single item",
            quantity=1,
            original_price_cents=100,
            discount_percent=20,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        session.add(lot)
        session.flush()
        lot_id, customer_ids = lot.id, [first_customer.id, second_customer.id]

    def reserve_for(customer_id: int) -> str:
        with sessions() as session:
            try:
                reserve_lot(session, lot_id, customer_id, 1)
                return "reserved"
            except HTTPException as exc:
                return f"http_{exc.status_code}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve_for, customer_ids))

    with sessions() as session:
        assert sorted(results) == ["http_409", "reserved"]
        assert session.get(Lot, lot_id).quantity == 0
        assert session.scalar(select(func.count(Reservation.id)).where(Reservation.lot_id == lot_id)) == 1
    engine.dispose()
