from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain.exceptions import BatchAlreadyReservedError
from app.models import Lot, Product, Shop, User
from app.services import reserve_lot


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
