from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.domain.diagnosis import RECENT_DAYS, LotFact, ShopSnapshot
from app.domain.entities import BatchStatus, ReservationStatus
from app.domain.waste import WasteEntry, WasteLot
from app.models import Donation, Lot, Reservation, Shop, WasteRecordRow


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SqlAlchemyInventoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_lot(self, lot_id: int) -> WasteLot | None:
        row = self._session.execute(
            select(Lot, Shop.owner_id).join(Shop, Lot.shop_id == Shop.id).where(Lot.id == lot_id)
        ).one_or_none()
        if row is None:
            return None
        lot, owner_id = row
        return WasteLot(lot.id, lot.shop_id, owner_id, lot.title, lot.quantity, lot.status)

    def get_shop_owner(self, shop_id: int) -> int | None:
        return self._session.scalar(select(Shop.owner_id).where(Shop.id == shop_id))

    def remove_stock(self, lot_id: int, quantity: int) -> bool:
        """Take units out of a lot that is on sale or already expired, once and atomically."""
        result = self._session.execute(
            update(Lot)
            .where(
                Lot.id == lot_id,
                Lot.status.in_([BatchStatus.ACTIVE.value, BatchStatus.EXPIRED.value]),
                Lot.quantity >= quantity,
            )
            .execution_options(synchronize_session=False)
            .values(
                quantity=Lot.quantity - quantity,
                version=Lot.version + 1,
                status=case(
                    (
                        (Lot.status == BatchStatus.ACTIVE.value) & (Lot.quantity == quantity),
                        BatchStatus.SOLD_OUT.value,
                    ),
                    else_=Lot.status,
                ),
            )
        )
        return result.rowcount == 1

    def add_waste(self, lot_id: int, quantity: int, reason: str, note: str, user_id: int, now: datetime) -> None:
        self._session.add(
            WasteRecordRow(
                lot_id=lot_id, quantity=quantity, reason=reason, note=note, recorded_by=user_id, created_at=now
            )
        )
        self._session.flush()

    def list_waste(self, shop_id: int, limit: int) -> list[WasteEntry]:
        rows = self._session.execute(
            select(WasteRecordRow, Lot.title)
            .join(Lot, WasteRecordRow.lot_id == Lot.id)
            .where(Lot.shop_id == shop_id)
            .order_by(WasteRecordRow.created_at.desc(), WasteRecordRow.id.desc())
            .limit(limit)
        )
        return [
            WasteEntry(r.id, r.lot_id, title, r.quantity, r.reason, r.note, _aware(r.created_at)) for r, title in rows
        ]

    def _units(self, column, *conditions) -> int:  # type: ignore[no-untyped-def]
        return int(self._session.scalar(select(func.coalesce(func.sum(column), 0)).where(*conditions)) or 0)

    def snapshot(self, shop_id: int, now: datetime) -> ShopSnapshot:
        since = now - timedelta(days=RECENT_DAYS)
        active = self._session.scalars(
            select(Lot).where(
                Lot.shop_id == shop_id,
                Lot.status == BatchStatus.ACTIVE.value,
                Lot.quantity > 0,
                Lot.expires_at > now,
            )
        )
        shop_lots = select(Lot.id).where(Lot.shop_id == shop_id)

        def reservations(status: ReservationStatus, *extra):  # type: ignore[no-untyped-def]
            return self._units(
                Reservation.quantity,
                Reservation.lot_id.in_(shop_lots),
                Reservation.status == status.value,
                *extra,
            )

        waste_since = self._units(
            WasteRecordRow.quantity, WasteRecordRow.lot_id.in_(shop_lots), WasteRecordRow.created_at >= since
        )
        ever_waste = self._session.scalar(
            select(func.count()).select_from(WasteRecordRow).where(WasteRecordRow.lot_id.in_(shop_lots))
        )
        return ShopSnapshot(
            active_lots=tuple(LotFact(lot.id, lot.quantity, _aware(lot.expires_at)) for lot in active),
            picked_up_units=reservations(ReservationStatus.PICKED_UP, Reservation.status_changed_at >= since),
            delivered_donation_units=self._units(
                Donation.quantity, Donation.lot_id.in_(shop_lots), Donation.created_at >= since
            ),
            cancelled_units=reservations(ReservationStatus.CANCELLED, Reservation.status_changed_at >= since),
            wasted_units=waste_since,
            pending_pickup_units=reservations(ReservationStatus.RESERVED),
            ever_recorded_waste=bool(ever_waste),
        )
