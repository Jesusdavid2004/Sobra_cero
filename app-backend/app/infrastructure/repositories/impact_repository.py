from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.impact import ReservationOutcome
from app.models import Donation, Lot, Reservation


class SqlAlchemyImpactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def reservation_outcomes(self, shop_id: int) -> list[ReservationOutcome]:
        rows = self._session.execute(
            select(
                Reservation.status,
                func.sum(Reservation.quantity),
                Lot.original_price_cents,
                Lot.discount_percent,
            )
            .join(Lot, Lot.id == Reservation.lot_id)
            .where(Lot.shop_id == shop_id)
            .group_by(Reservation.status, Lot.id, Lot.original_price_cents, Lot.discount_percent)
        ).all()
        return [
            ReservationOutcome(
                status=status,
                units=int(units),
                original_price_cents=original_price_cents,
                discount_percent=discount_percent,
            )
            for status, units, original_price_cents, discount_percent in rows
        ]

    def donated_units(self, shop_id: int) -> int:
        total = self._session.scalar(
            select(func.coalesce(func.sum(Donation.quantity), 0))
            .join(Lot, Lot.id == Donation.lot_id)
            .where(Lot.shop_id == shop_id)
        )
        return int(total or 0)
