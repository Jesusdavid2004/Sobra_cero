"""Generate deterministic sample sales history for every catalog product."""

import logging

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Product
from app.synthetic_sales import DEFAULT_HISTORY_DAYS, generate_product_sales_history

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        products = db.scalars(select(Product).order_by(Product.id)).all()
        if not products:
            logger.info("No products found. Create a shop and at least one product first.")
            return
        created = 0
        existing = 0
        for product in products:
            product_created, product_existing = generate_product_sales_history(db, product, days=DEFAULT_HISTORY_DAYS)
            created += product_created
            existing += product_existing
        db.commit()
        logger.info(
            "Generated %s daily sales records across %s products; %s existing records were kept.",
            created,
            len(products),
            existing,
        )


if __name__ == "__main__":
    main()
