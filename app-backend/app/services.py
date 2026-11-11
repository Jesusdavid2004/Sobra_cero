from datetime import datetime, timezone
from secrets import token_hex

from fastapi import HTTPException
from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ai_dto import PromotionCopy
from app.application.ports import AIProvider
from app.domain.entities import BatchStatus, ReservationStatus
from app.domain.exceptions import BatchAlreadyReservedError
from app.infrastructure.realtime.notifier import notify_lot_changed
from app.llm import build_client
from app.models import Donation, Lot, Promotion, Reservation
from app.prompts import PROMOTION_PROMPT_VERSION, VARIANTS, build_prompt


def reserve_lot(db: Session, lot_id: int, user_id: int, quantity: int) -> Reservation:
    """Decrement stock conditionally so concurrent requests cannot oversell."""
    lot = db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot is unavailable")
    expires_at = lot.expires_at.replace(tzinfo=timezone.utc) if lot.expires_at.tzinfo is None else lot.expires_at
    now = datetime.now(timezone.utc)
    if expires_at <= now or lot.status not in {BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value}:
        raise HTTPException(status_code=404, detail="Lot is unavailable")
    if lot.status == BatchStatus.SOLD_OUT.value:
        raise HTTPException(status_code=409, detail="Not enough quantity available")
    existing_reservation = db.scalar(
        select(Reservation).where(
            Reservation.lot_id == lot_id,
            Reservation.user_id == user_id,
            Reservation.status == ReservationStatus.RESERVED.value,
        )
    )
    if existing_reservation:
        raise BatchAlreadyReservedError("You have already reserved this batch")

    stock_update = db.execute(
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
                (Lot.quantity == quantity, BatchStatus.SOLD_OUT.value),
                else_=BatchStatus.ACTIVE.value,
            ),
        )
    )
    if stock_update.rowcount != 1:
        db.rollback()
        current_lot = db.get(Lot, lot_id)
        if (
            current_lot is None
            or current_lot.status not in {BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value}
            or (
                current_lot.expires_at.replace(tzinfo=timezone.utc)
                if current_lot.expires_at.tzinfo is None
                else current_lot.expires_at
            )
            <= now
        ):
            raise HTTPException(status_code=404, detail="Lot is unavailable")
        raise HTTPException(status_code=409, detail="Not enough quantity available")

    reservation = Reservation(
        lot_id=lot_id,
        user_id=user_id,
        quantity=quantity,
        pickup_code=token_hex(4).upper(),
    )
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(
            select(Reservation.id).where(
                Reservation.lot_id == lot_id,
                Reservation.user_id == user_id,
                Reservation.status == ReservationStatus.RESERVED.value,
            )
        ):
            raise BatchAlreadyReservedError("You have already reserved this batch") from exc
        raise
    db.refresh(reservation)
    notify_lot_changed(db, lot_id)
    return reservation


def _claim_active_reservation(db: Session, reservation_id: int, target: ReservationStatus) -> None:
    """Move a reservation out of `reserved` exactly once, whatever the database or concurrency level."""
    claimed = db.execute(
        update(Reservation)
        .where(Reservation.id == reservation_id, Reservation.status == ReservationStatus.RESERVED.value)
        .execution_options(synchronize_session=False)
        .values(status=target.value, status_changed_at=datetime.now(timezone.utc))
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Reservation is no longer active")


def donate_lot(db: Session, lot_id: int, quantity: int) -> Donation:
    now = datetime.now(timezone.utc)
    lot = db.get(Lot, lot_id)
    if lot is None or lot.status != BatchStatus.ACTIVE.value:
        raise HTTPException(status_code=404, detail="Lot is unavailable")
    expires_at = lot.expires_at.replace(tzinfo=timezone.utc) if lot.expires_at.tzinfo is None else lot.expires_at
    if expires_at <= now:
        raise HTTPException(status_code=404, detail="Lot is unavailable")
    stock_update = db.execute(
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
    if stock_update.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Not enough quantity available")
    donation = Donation(lot_id=lot_id, quantity=quantity)
    db.add(donation)
    db.commit()
    db.refresh(donation)
    notify_lot_changed(db, lot_id)
    return donation


def cancel_lot(db: Session, lot_id: int) -> Lot:
    result = db.execute(
        update(Lot)
        .where(
            Lot.id == lot_id,
            Lot.status.in_([BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value]),
        )
        .execution_options(synchronize_session=False)
        .values(status=BatchStatus.CANCELLED.value, quantity=0, version=Lot.version + 1)
    )
    if result.rowcount != 1:
        db.rollback()
        lot = db.get(Lot, lot_id)
        if lot is None:
            raise HTTPException(status_code=404, detail="Lot not found")
        raise HTTPException(status_code=409, detail="Lot is no longer available to cancel")
    db.execute(
        update(Reservation)
        .where(
            Reservation.lot_id == lot_id,
            Reservation.status == ReservationStatus.RESERVED.value,
        )
        .execution_options(synchronize_session=False)
        .values(status=ReservationStatus.CANCELLED.value, status_changed_at=datetime.now(timezone.utc))
    )
    db.commit()
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lot not found")
    notify_lot_changed(db, lot_id)
    return lot


def cancel_reservation(db: Session, reservation_id: int, user_id: int) -> Reservation:
    reservation = db.execute(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    ).scalar_one_or_none()
    if reservation is None or reservation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != ReservationStatus.RESERVED.value:
        raise HTTPException(status_code=409, detail="Reservation is no longer active")

    lot = db.execute(select(Lot).where(Lot.id == reservation.lot_id).with_for_update()).scalar_one()
    now = datetime.now(timezone.utc)
    expires_at = lot.expires_at.replace(tzinfo=timezone.utc) if lot.expires_at.tzinfo is None else lot.expires_at
    stock_states = [BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value]
    if expires_at <= now or lot.status == BatchStatus.EXPIRED.value:
        _claim_active_reservation(db, reservation_id, ReservationStatus.EXPIRED)
        db.execute(
            update(Lot)
            .where(Lot.id == lot.id, Lot.status.in_(stock_states))
            .execution_options(synchronize_session=False)
            .values(status=BatchStatus.EXPIRED.value, version=Lot.version + 1)
        )
    else:
        _claim_active_reservation(db, reservation_id, ReservationStatus.CANCELLED)
        db.execute(
            update(Lot)
            .where(Lot.id == lot.id, Lot.status.in_(stock_states))
            .execution_options(synchronize_session=False)
            .values(
                quantity=Lot.quantity + reservation.quantity,
                status=BatchStatus.ACTIVE.value,
                version=Lot.version + 1,
            )
        )
    db.commit()
    db.refresh(reservation)
    notify_lot_changed(db, lot.id)
    return reservation


def confirm_reservation_pickup(db: Session, reservation_id: int, pickup_code: str) -> Reservation:
    reservation = db.execute(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    ).scalar_one_or_none()
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.pickup_code != pickup_code:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != ReservationStatus.RESERVED.value:
        raise HTTPException(status_code=409, detail="Reservation is no longer active")
    lot = db.get(Lot, reservation.lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    expires_at = lot.expires_at.replace(tzinfo=timezone.utc) if lot.expires_at.tzinfo is None else lot.expires_at
    if expires_at <= datetime.now(timezone.utc) or lot.status == BatchStatus.EXPIRED.value:
        if lot.status in {BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value}:
            lot.status = BatchStatus.EXPIRED.value
        reservation.status = ReservationStatus.EXPIRED.value
        db.commit()
        raise HTTPException(status_code=409, detail="Lot has expired")
    if lot.status not in {
        BatchStatus.ACTIVE.value,
        BatchStatus.SOLD_OUT.value,
        BatchStatus.DONATED.value,
    }:
        raise HTTPException(status_code=409, detail="Lot is no longer available for pickup")
    _claim_active_reservation(db, reservation_id, ReservationStatus.PICKED_UP)
    db.commit()
    db.refresh(reservation)
    return reservation


def expire_due_lots(db: Session, now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    due_lot_ids = list(
        db.scalars(
            select(Lot.id).where(
                Lot.status.in_([BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value]),
                Lot.expires_at <= current_time,
            )
        )
    )
    expired_lots = db.execute(
        update(Lot)
        .where(
            Lot.status.in_([BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value]),
            Lot.expires_at <= current_time,
        )
        .execution_options(synchronize_session=False)
        .values(status=BatchStatus.EXPIRED.value, version=Lot.version + 1)
    )
    db.execute(
        update(Reservation)
        .where(
            Reservation.status == ReservationStatus.RESERVED.value,
            Reservation.lot_id.in_(select(Lot.id).where(Lot.expires_at <= current_time)),
        )
        .values(status=ReservationStatus.EXPIRED.value, status_changed_at=current_time)
    )
    db.commit()
    for lot_id in due_lot_ids:
        notify_lot_changed(db, lot_id)
    return max(expired_lots.rowcount or 0, 0)


def build_promotions(
    db: Session,
    lot: Lot,
    language: str = "en",
    *,
    user_id: int = 0,
    ai_provider: AIProvider | None = None,
) -> list[Promotion]:
    """Generate three auditable promotional variants for a lot via the LLM client."""
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    provider = ai_provider or build_client()
    promotions = []
    for variant in VARIANTS:
        prompt = build_prompt(lot, language, variant)
        text = provider.generate_structured(
            prompt=prompt,
            response_model=PromotionCopy,
            user_id=user_id,
            locale=language,
            prompt_version=PROMOTION_PROMPT_VERSION,
        ).text
        promotions.append(
            Promotion(lot_id=lot.id, language=language, variant=f"variant-{variant}", text=text, prompt=prompt)
        )
    db.add_all(promotions)
    db.commit()
    for promotion in promotions:
        db.refresh(promotion)
    return promotions
