"""Load a complete demonstration dataset for Pasto so every screen has something to show.

Usage (from the repository root, with the target database in DATABASE_URL):

    DEMO_PASSWORD=<password for the demo accounts> python scripts/seed_expo_demo.py

Safe to run again. Run it again on the morning of a presentation: lots that were created earlier
get a fresh expiry time and stock, so the storefront is never empty. Accounts, shops, products,
reservations, donations and waste records are matched by name and created only once.

Everything here is invented. Shop names start with "Demo" and nothing is presented as a real
business. The password is read from the environment and never stored in the repository.
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app-backend"))

from app.auth import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.domain.entities import BatchStatus  # noqa: E402
from app.migrations import upgrade_database_schema  # noqa: E402
from app.models import (DonationOfferRecord, Lot, Product,  # noqa: E402
                        ReceiverRecord, Reservation, Shop, User,
                        WasteRecordRow)
from app.services import (confirm_reservation_pickup, donate_lot,  # noqa: E402
                          reserve_lot)
from app.synthetic_sales import generate_shop_sales_history  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

PASSWORD_ENV = "DEMO_PASSWORD"
MIN_PASSWORD_LENGTH = 10
BUSINESS_ROLE = "business"
CUSTOMER_ROLE = "customer"
CUSTOMER_EMAIL = "cliente@sobracero.com"
RECEIVER_EMAIL = "banco@sobracero.com"
RECEIVER_NAME = "Banco de Alimentos Pasto"
RECEIVER_CATEGORIES = "bakery,dairy,produce"
RECEIVER_CAPACITY = 100
RECEIVER_LATITUDE = 1.2175
RECEIVER_LONGITUDE = -77.2790
MINUTES_PER_DAY = 24 * 60
PASTO_UTC_OFFSET_MINUTES = -300
EXPIRED_LOT_TITLE = "Pan del día anterior"
EXPIRED_LOT_AGE = timedelta(days=2)
RESERVED_QUANTITY = 2
PICKED_UP_QUANTITY = 1
DONATED_QUANTITY = 3
OFFERED_QUANTITY = 4
WASTE_QUANTITY = 4
WASTE_NOTE = "Not sold before closing"


@dataclass(frozen=True)
class LotSpec:
    title: str
    product: str
    quantity: int
    price_cents: int
    discount_percent: int
    hours_to_expiry: int


@dataclass(frozen=True)
class ProductSpec:
    name: str
    category: str
    description: str


@dataclass(frozen=True)
class ShopSpec:
    owner_email: str
    name: str
    business_type: str
    description: str
    latitude: float
    longitude: float
    products: tuple[ProductSpec, ...]
    lots: tuple[LotSpec, ...]


SHOPS = (
    ShopSpec(
        owner_email="panaderia@sobracero.com",
        name="Demo Panadería Centro",
        business_type="restaurant",
        description="Panadería de barrio con horno propio (datos de demostración).",
        latitude=1.2140,
        longitude=-77.2810,
        products=(
            ProductSpec("Pan campesino", "bakery", "Hogaza del día"),
            ProductSpec("Pan de yuca", "bakery", "Bolsa de seis unidades"),
            ProductSpec("Croissant", "bakery", "Croissant de mantequilla"),
        ),
        lots=(
            LotSpec("Caja de pan del día", "Pan campesino", 12, 1800, 40, 5),
            LotSpec("Bolsa de pan de yuca", "Pan de yuca", 15, 1200, 35, 9),
            LotSpec("Croissants de la tarde", "Croissant", 8, 2400, 50, 26),
        ),
    ),
    ShopSpec(
        owner_email="restaurante@sobracero.com",
        name="Demo Restaurante La Esquina",
        business_type="restaurant",
        description="Comida casera de mediodía (datos de demostración).",
        latitude=1.2128,
        longitude=-77.2825,
        products=(
            ProductSpec("Almuerzo ejecutivo", "prepared", "Sopa, seco y jugo"),
            ProductSpec("Ensalada de la casa", "produce", "Ensalada fresca"),
        ),
        lots=(
            LotSpec("Almuerzos sobrantes", "Almuerzo ejecutivo", 10, 1500, 45, 6),
            LotSpec("Ensaladas frescas", "Ensalada de la casa", 14, 900, 30, 14),
        ),
    ),
    ShopSpec(
        owner_email="supermercado@sobracero.com",
        name="Demo Supermercado Plaza",
        business_type="supermarket",
        description="Supermercado de barrio (datos de demostración).",
        latitude=1.2152,
        longitude=-77.2796,
        products=(
            ProductSpec("Leche entera", "dairy", "Bolsa de un litro"),
            ProductSpec("Yogur natural", "dairy", "Vaso de 200 g"),
            ProductSpec("Frutas variadas", "produce", "Canasta de frutas de temporada"),
            ProductSpec("Pasta", "pantry", "Paquete de 500 g"),
        ),
        lots=(
            LotSpec("Leche próxima a vencer", "Leche entera", 24, 800, 40, 20),
            LotSpec("Yogures de la semana", "Yogur natural", 18, 500, 50, 30),
            LotSpec("Canasta de frutas", "Frutas variadas", 10, 1600, 35, 12),
            LotSpec("Pasta en oferta", "Pasta", 20, 700, 25, 72),
        ),
    ),
)


def read_password() -> str:
    password = os.environ.get(PASSWORD_ENV, "")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.stderr.write(
            f"Set {PASSWORD_ENV} to a password of at least {MIN_PASSWORD_LENGTH} characters.\n"
        )
        raise SystemExit(1)
    return password


def get_or_create_user(db: Session, email: str, role: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(password), role=role)
        db.add(user)
        db.flush()
    return user


def get_or_create_shop(db: Session, spec: ShopSpec, owner: User) -> Shop:
    shop = db.scalar(
        select(Shop).where(Shop.owner_id == owner.id, Shop.name == spec.name)
    )
    if shop is None:
        shop = Shop(
            owner_id=owner.id,
            name=spec.name,
            business_type=spec.business_type,
            description=spec.description,
            latitude=spec.latitude,
            longitude=spec.longitude,
        )
        db.add(shop)
        db.flush()
    return shop


def get_or_create_product(db: Session, shop: Shop, spec: ProductSpec) -> Product:
    product = db.scalar(
        select(Product).where(Product.shop_id == shop.id, Product.name == spec.name)
    )
    if product is None:
        product = Product(
            shop_id=shop.id,
            name=spec.name,
            category=spec.category,
            description=spec.description,
        )
        db.add(product)
        db.flush()
    return product


def upsert_lot(
    db: Session, shop: Shop, product: Product, spec: LotSpec, now: datetime
) -> Lot:
    """Create the lot, or give an existing one a fresh expiry and stock so it is on sale today."""
    lot = db.scalar(select(Lot).where(Lot.shop_id == shop.id, Lot.title == spec.title))
    expires_at = now + timedelta(hours=spec.hours_to_expiry)
    if lot is None:
        lot = Lot(
            shop_id=shop.id,
            product_id=product.id,
            title=spec.title,
            description=product.description,
            quantity=spec.quantity,
            original_price_cents=spec.price_cents,
            discount_percent=spec.discount_percent,
            expires_at=expires_at,
        )
        db.add(lot)
    else:
        lot.expires_at = expires_at
        lot.quantity = spec.quantity
        lot.status = BatchStatus.ACTIVE.value
    db.flush()
    return lot


def seed_shops(db: Session, password: str, now: datetime) -> dict[str, Lot]:
    lots: dict[str, Lot] = {}
    for spec in SHOPS:
        owner = get_or_create_user(db, spec.owner_email, BUSINESS_ROLE, password)
        shop = get_or_create_shop(db, spec, owner)
        products = {
            item.name: get_or_create_product(db, shop, item) for item in spec.products
        }
        for lot_spec in spec.lots:
            lots[lot_spec.title] = upsert_lot(
                db, shop, products[lot_spec.product], lot_spec, now
            )
        generate_shop_sales_history(db, shop.id)
    return lots


def seed_expired_lot_with_waste(db: Session, now: datetime) -> None:
    shop = db.scalar(select(Shop).where(Shop.name == SHOPS[0].name))
    product = db.scalar(select(Product).where(Product.shop_id == shop.id))
    if db.scalar(
        select(Lot).where(Lot.shop_id == shop.id, Lot.title == EXPIRED_LOT_TITLE)
    ):
        return
    lot = Lot(
        shop_id=shop.id,
        product_id=product.id,
        title=EXPIRED_LOT_TITLE,
        description=product.description,
        quantity=WASTE_QUANTITY,
        original_price_cents=1800,
        discount_percent=40,
        expires_at=now - EXPIRED_LOT_AGE,
        status=BatchStatus.EXPIRED.value,
    )
    db.add(lot)
    db.flush()
    db.add(
        WasteRecordRow(
            lot_id=lot.id,
            quantity=WASTE_QUANTITY,
            reason="expired",
            note=WASTE_NOTE,
            recorded_by=shop.owner_id,
            created_at=now - EXPIRED_LOT_AGE,
        )
    )


def seed_customer_activity(db: Session, password: str, lots: dict[str, Lot]) -> None:
    customer = get_or_create_user(db, CUSTOMER_EMAIL, CUSTOMER_ROLE, password)
    if db.scalar(select(Reservation).where(Reservation.user_id == customer.id)):
        return
    db.commit()
    reserve_lot(db, lots["Caja de pan del día"].id, customer.id, RESERVED_QUANTITY)
    picked_up = reserve_lot(
        db, lots["Almuerzos sobrantes"].id, customer.id, PICKED_UP_QUANTITY
    )
    confirm_reservation_pickup(db, picked_up.id, picked_up.pickup_code)


def seed_receiver_and_donations(
    db: Session, password: str, lots: dict[str, Lot], now: datetime
) -> None:
    owner = get_or_create_user(db, RECEIVER_EMAIL, BUSINESS_ROLE, password)
    receiver = db.scalar(
        select(ReceiverRecord).where(ReceiverRecord.owner_user_id == owner.id)
    )
    if receiver is not None:
        return
    receiver = ReceiverRecord(
        owner_user_id=owner.id,
        name=RECEIVER_NAME,
        latitude=RECEIVER_LATITUDE,
        longitude=RECEIVER_LONGITUDE,
        accepted_categories=RECEIVER_CATEGORIES,
        max_quantity=RECEIVER_CAPACITY,
        can_store_refrigerated=True,
        open_from_minute=0,
        open_until_minute=MINUTES_PER_DAY,
        utc_offset_minutes=PASTO_UTC_OFFSET_MINUTES,
    )
    db.add(receiver)
    db.flush()
    db.add(
        DonationOfferRecord(
            lot_id=lots["Yogures de la semana"].id,
            receiver_id=receiver.id,
            quantity=OFFERED_QUANTITY,
            message="Yogures próximos a vencer, listos para recoger.",
            created_at=now,
        )
    )
    db.commit()
    donate_lot(db, lots["Pasta en oferta"].id, DONATED_QUANTITY)


def main() -> int:
    password = read_password()
    upgrade_database_schema(engine.url)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        lots = seed_shops(db, password, now)
        seed_expired_lot_with_waste(db, now)
        db.commit()
        seed_customer_activity(db, password, lots)
        seed_receiver_and_donations(db, password, lots, now)
        db.commit()
    sys.stdout.write(
        "Demonstration data loaded. Run scripts/seed_pasto_demo.py for the map businesses.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
