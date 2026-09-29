from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Lot, Product, Promotion, Shop, User
from app.prompts import VARIANTS
from app.services import build_promotions


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(email="owner@example.com", password_hash="hash")
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
        quantity=5,
        original_price_cents=1000,
        discount_percent=30,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    session.add(lot)
    session.commit()
    yield session, lot
    session.close()


def test_build_promotions_creates_three_variants(db):
    session, lot = db
    promotions = build_promotions(session, lot, "es")
    assert len(promotions) == 3
    assert {p.variant for p in promotions} == {f"variant-{v}" for v in VARIANTS}
    assert all(p.language == "es" for p in promotions)


def test_build_promotions_persists_prompt_for_audit(db):
    session, lot = db
    build_promotions(session, lot, "en")
    stored = session.query(Promotion).filter(Promotion.lot_id == lot.id).all()
    assert len(stored) == 3
    assert all(p.prompt for p in stored)
    assert all("Test lot" in p.prompt for p in stored)
