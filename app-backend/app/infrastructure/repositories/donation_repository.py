from datetime import datetime, timezone

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities import BatchStatus
from app.domain.exceptions import DonationOfferConflictError, ReceiverAlreadyExistsError
from app.domain.receivers import (
    COMMITTED_OFFER_STATUSES,
    DonationLot,
    DonationOffer,
    OfferStatus,
    OfferView,
    Receiver,
)
from app.models import Donation, DonationOfferRecord, Lot, Product, ReceiverRecord, Shop

CATEGORY_SEPARATOR = ","


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _to_receiver(row: ReceiverRecord) -> Receiver:
    return Receiver(
        id=row.id,
        owner_user_id=row.owner_user_id,
        name=row.name,
        latitude=row.latitude,
        longitude=row.longitude,
        accepted_categories=frozenset(row.accepted_categories.split(CATEGORY_SEPARATOR)),
        max_quantity=row.max_quantity,
        can_store_refrigerated=row.can_store_refrigerated,
        open_from_minute=row.open_from_minute,
        open_until_minute=row.open_until_minute,
        utc_offset_minutes=row.utc_offset_minutes,
    )


def _to_offer(row: DonationOfferRecord) -> DonationOffer:
    return DonationOffer(
        id=row.id,
        lot_id=row.lot_id,
        receiver_id=row.receiver_id,
        quantity=row.quantity,
        status=OfferStatus(row.status),
        message=row.message,
        created_at=_aware(row.created_at),
        decided_at=_aware(row.decided_at) if row.decided_at else None,
        delivered_at=_aware(row.delivered_at) if row.delivered_at else None,
    )


class SqlAlchemyDonationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_lot(self, lot_id: int) -> DonationLot | None:
        row = self._session.execute(
            select(Lot, Product.category, Shop.owner_id, Shop.latitude, Shop.longitude)
            .join(Product, Lot.product_id == Product.id)
            .join(Shop, Lot.shop_id == Shop.id)
            .where(Lot.id == lot_id)
        ).one_or_none()
        if row is None:
            return None
        lot, category, owner_id, latitude, longitude = row
        return DonationLot(
            lot_id=lot.id,
            shop_id=lot.shop_id,
            owner_id=owner_id,
            title=lot.title,
            category=category,
            available_quantity=lot.quantity,
            status=lot.status,
            closes_at=_aware(lot.pickup_ends_at or lot.expires_at),
            latitude=latitude,
            longitude=longitude,
        )

    def list_receivers(self) -> list[Receiver]:
        return [_to_receiver(row) for row in self._session.scalars(select(ReceiverRecord).order_by(ReceiverRecord.id))]

    def get_receiver(self, receiver_id: int) -> Receiver | None:
        row = self._session.get(ReceiverRecord, receiver_id)
        return _to_receiver(row) if row else None

    def get_receiver_by_owner(self, user_id: int) -> Receiver | None:
        row = self._session.scalar(select(ReceiverRecord).where(ReceiverRecord.owner_user_id == user_id))
        return _to_receiver(row) if row else None

    def add_receiver(self, receiver: Receiver) -> Receiver:
        row = ReceiverRecord(
            owner_user_id=receiver.owner_user_id,
            name=receiver.name.strip(),
            latitude=receiver.latitude,
            longitude=receiver.longitude,
            accepted_categories=CATEGORY_SEPARATOR.join(sorted(receiver.accepted_categories)),
            max_quantity=receiver.max_quantity,
            can_store_refrigerated=receiver.can_store_refrigerated,
            open_from_minute=receiver.open_from_minute,
            open_until_minute=receiver.open_until_minute,
            utc_offset_minutes=receiver.utc_offset_minutes,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ReceiverAlreadyExistsError("This account already has a receiver profile") from exc
        return _to_receiver(row)

    def recent_committed_counts(self, since: datetime) -> dict[int, int]:
        rows = self._session.execute(
            select(DonationOfferRecord.receiver_id, func.count())
            .where(
                DonationOfferRecord.status.in_([status.value for status in COMMITTED_OFFER_STATUSES]),
                DonationOfferRecord.decided_at >= since,
            )
            .group_by(DonationOfferRecord.receiver_id)
        ).all()
        return {receiver_id: count for receiver_id, count in rows}

    def add_offer(self, lot_id: int, receiver_id: int, quantity: int, message: str, now: datetime) -> DonationOffer:
        row = DonationOfferRecord(
            lot_id=lot_id, receiver_id=receiver_id, quantity=quantity, message=message, created_at=now
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DonationOfferConflictError("An active offer for this lot and receiver already exists") from exc
        return _to_offer(row)

    def get_offer(self, offer_id: int) -> DonationOffer | None:
        row = self._session.get(DonationOfferRecord, offer_id)
        return _to_offer(row) if row else None

    def _views(self, condition) -> list[OfferView]:  # type: ignore[no-untyped-def]
        rows = self._session.execute(
            select(DonationOfferRecord, Lot, Product.category, Shop.name, ReceiverRecord.name)
            .join(Lot, DonationOfferRecord.lot_id == Lot.id)
            .join(Product, Lot.product_id == Product.id)
            .join(Shop, Lot.shop_id == Shop.id)
            .join(ReceiverRecord, DonationOfferRecord.receiver_id == ReceiverRecord.id)
            .where(condition)
            .order_by(DonationOfferRecord.id.desc())
        ).all()
        return [
            OfferView(
                _to_offer(offer), lot.title, category, _aware(lot.pickup_ends_at or lot.expires_at), shop, receiver
            )
            for offer, lot, category, shop, receiver in rows
        ]

    def view_offers_for_lot(self, lot_id: int) -> list[OfferView]:
        return self._views(DonationOfferRecord.lot_id == lot_id)

    def view_offers_for_receiver(self, receiver_id: int) -> list[OfferView]:
        return self._views(DonationOfferRecord.receiver_id == receiver_id)

    def claim_offer(self, offer_id: int, current: OfferStatus, target: OfferStatus, now: datetime) -> bool:
        values: dict[str, object] = {"status": target.value}
        if target is OfferStatus.DELIVERED:
            values["delivered_at"] = now
        else:
            values["decided_at"] = now
        result = self._session.execute(
            update(DonationOfferRecord)
            .where(DonationOfferRecord.id == offer_id, DonationOfferRecord.status == current.value)
            .execution_options(synchronize_session=False)
            .values(**values)
        )
        return result.rowcount == 1

    def commit_stock(self, lot_id: int, quantity: int, now: datetime) -> bool:
        result = self._session.execute(
            update(Lot)
            .where(
                Lot.id == lot_id,
                Lot.status == BatchStatus.ACTIVE.value,
                Lot.expires_at > now,
                Lot.quantity >= quantity,
            )
            .execution_options(synchronize_session=False)
            .values(
                quantity=Lot.quantity - quantity,
                version=Lot.version + 1,
                status=case(
                    (Lot.quantity == quantity, BatchStatus.DONATED.value),
                    else_=BatchStatus.ACTIVE.value,
                ),
            )
        )
        return result.rowcount == 1

    def record_delivery(self, lot_id: int, quantity: int) -> None:
        self._session.add(Donation(lot_id=lot_id, quantity=quantity))
