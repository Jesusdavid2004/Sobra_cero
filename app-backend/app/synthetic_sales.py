from datetime import date, timedelta
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, SalesHistory

DEFAULT_HISTORY_DAYS = 60
MIN_HISTORY_DAYS = 14
MAX_HISTORY_DAYS = 90


def generate_product_sales_history(
    db: Session,
    product: Product,
    *,
    days: int = DEFAULT_HISTORY_DAYS,
    today: date | None = None,
) -> tuple[int, int]:
    if not MIN_HISTORY_DAYS <= days <= MAX_HISTORY_DAYS:
        raise ValueError(f"days must be between {MIN_HISTORY_DAYS} and {MAX_HISTORY_DAYS}")

    end_date = today or date.today()
    start_date = end_date - timedelta(days=days - 1)
    existing_dates = set(
        db.scalars(
            select(SalesHistory.sales_date).where(
                SalesHistory.product_id == product.id,
                SalesHistory.sales_date >= start_date,
                SalesHistory.sales_date <= end_date,
            )
        )
    )
    randomizer = Random(product.id)
    created = 0
    for day_offset in range(days):
        sales_date = start_date + timedelta(days=day_offset)
        if sales_date in existing_dates:
            continue
        weekday_adjustment = 4 if sales_date.weekday() >= 4 else 0
        seasonal_adjustment = 2 if day_offset % 15 < 5 else 0
        had_promotion = (day_offset + product.id) % 12 == 0
        promotion_adjustment = 3 if had_promotion else 0
        units_sold = max(
            0, 6 + weekday_adjustment + seasonal_adjustment + promotion_adjustment + randomizer.randint(-2, 2)
        )
        db.add(
            SalesHistory(
                product_id=product.id,
                sales_date=sales_date,
                units_sold=units_sold,
                had_promotion=had_promotion,
            )
        )
        created += 1
    return created, len(existing_dates)


def generate_shop_sales_history(db: Session, shop_id: int, *, days: int = DEFAULT_HISTORY_DAYS) -> tuple[int, int]:
    products = db.scalars(select(Product).where(Product.shop_id == shop_id)).all()
    created = 0
    existing = 0
    for product in products:
        product_created, product_existing = generate_product_sales_history(db, product, days=days)
        created += product_created
        existing += product_existing
    db.commit()
    return created, existing
