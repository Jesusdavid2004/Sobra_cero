from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.discovery import LotCandidate
from app.models import Lot, Product, Shop


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SqlAlchemyDiscoveryLotSource:
    def __init__(self, session: Session) -> None:
        self._session = session

    def open_candidates(self, now: datetime) -> list[LotCandidate]:
        rows = self._session.execute(
            select(Lot, Product.category, Shop.latitude, Shop.longitude)
            .join(Product, Lot.product_id == Product.id)
            .join(Shop, Lot.shop_id == Shop.id)
            .where(Lot.status == "active", Lot.quantity > 0, Lot.expires_at > now)
        ).all()
        return [
            LotCandidate(
                lot_id=lot.id,
                shop_id=lot.shop_id,
                title=lot.title,
                category=category,
                available_quantity=lot.quantity,
                original_price_cents=lot.original_price_cents,
                discount_percent=lot.discount_percent,
                closes_at=_aware(lot.pickup_ends_at or lot.expires_at),
                latitude=latitude,
                longitude=longitude,
            )
            for lot, category, latitude, longitude in rows
        ]
