"""Create a repeatable local demo account, shop, product, and sample lots."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import Base, SessionLocal, engine
from app.models import Lot, Product, Shop, User

DEMO_EMAIL = "demo@sobracero.com"
LEGACY_DEMO_EMAIL = "demo@sobracero.local"
DEMO_PASSWORD = "password123"
SHOP_NAME = "Fresh Corner"
PRODUCT_NAME = "Bakery box"
LOT_TITLES = ("Rescue box 1", "Rescue box 2", "Rescue box 3")
LOT_EXPIRATION_HOURS = (24, 36, 72)


def seed_demo_data(db: Session) -> None:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = db.scalar(select(User).where(User.email == LEGACY_DEMO_EMAIL))
        if user is not None:
            user.email = DEMO_EMAIL
        else:
            user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()

    user.password_hash = hash_password(DEMO_PASSWORD)
    user.is_admin = True
    db.flush()

    shop = db.scalar(select(Shop).where(Shop.owner_id == user.id, Shop.name == SHOP_NAME))
    if shop is None:
        shop = Shop(
            owner_id=user.id,
            name=SHOP_NAME,
            description="Rescue good food near you",
            latitude=4.711,
            longitude=-74.072,
        )
        db.add(shop)
        db.flush()

    product = db.scalar(select(Product).where(Product.shop_id == shop.id, Product.name == PRODUCT_NAME))
    if product is None:
        product = Product(
            shop_id=shop.id,
            name=PRODUCT_NAME,
            description="A selection from today's bakery",
            category="bakery",
        )
        db.add(product)
        db.flush()

    now = datetime.now(timezone.utc)
    for title, hours in zip(LOT_TITLES, LOT_EXPIRATION_HOURS):
        lot = db.scalar(
            select(Lot).where(
                Lot.shop_id == shop.id,
                Lot.product_id == product.id,
                Lot.title == title,
            )
        )
        if lot is None:
            db.add(
                Lot(
                    shop_id=shop.id,
                    product_id=product.id,
                    title=title,
                    description="Fresh surplus food",
                    quantity=10,
                    original_price_cents=2000,
                    discount_percent=50,
                    expires_at=now + timedelta(hours=hours),
                )
            )

    db.commit()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_data(db)
    print(f"Seed complete: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
