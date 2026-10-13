from datetime import datetime, timezone
from secrets import token_hex

from fastapi import HTTPException
from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities import BatchStatus, ReservationStatus
from app.domain.exceptions import BatchAlreadyReservedError
from app.llm import build_client
from app.models import Donation, Lot, Promotion, Reservation
from app.prompts import VARIANTS, build_prompt


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
    return reservation


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
    return donation


def cancel_lot(db: Session, lot_id: int) -> Lot:
    result = db.execute(
        update(Lot)
        .where(
            Lot.id == lot_id,
            Lot.status.in_([BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value]),
        )
        .execution_options(synchronize_session=False)
        .values(status=BatchStatus.CANCELLED.value, quantity=0)
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
        .values(status=ReservationStatus.CANCELLED.value)
    )
    db.commit()
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lot not found")
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
    if expires_at <= now or lot.status == BatchStatus.EXPIRED.value:
        if lot.status in {BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value}:
            lot.status = BatchStatus.EXPIRED.value
        reservation.status = ReservationStatus.EXPIRED.value
    else:
        if lot.status in {BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value}:
            lot.quantity += reservation.quantity
            lot.status = BatchStatus.ACTIVE.value
        reservation.status = ReservationStatus.CANCELLED.value
    db.commit()
    db.refresh(reservation)
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
    reservation.status = ReservationStatus.PICKED_UP.value
    db.commit()
    db.refresh(reservation)
    return reservation


def expire_due_lots(db: Session, now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    expired_lots = db.execute(
        update(Lot)
        .where(
            Lot.status.in_([BatchStatus.ACTIVE.value, BatchStatus.SOLD_OUT.value]),
            Lot.expires_at <= current_time,
        )
        .execution_options(synchronize_session=False)
        .values(status=BatchStatus.EXPIRED.value)
    )
    db.execute(
        update(Reservation)
        .where(
            Reservation.status == ReservationStatus.RESERVED.value,
            Reservation.lot_id.in_(select(Lot.id).where(Lot.expires_at <= current_time)),
        )
        .values(status=ReservationStatus.EXPIRED.value)
    )
    db.commit()
    return max(expired_lots.rowcount or 0, 0)


def build_promotions(db: Session, lot: Lot, language: str = "en") -> list[Promotion]:
    """Generate three auditable promotional variants for a lot via the LLM client."""
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    client = build_client()
    promotions = []
    for variant in VARIANTS:
        prompt = build_prompt(lot, language, variant)
        text = client.complete(prompt)
        promotions.append(
            Promotion(lot_id=lot.id, language=language, variant=f"variant-{variant}", text=text, prompt=prompt)
        )
    db.add_all(promotions)
    db.commit()
    for promotion in promotions:
        db.refresh(promotion)
    return promotions
