from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import build_client
from app.models import Donation, Lot, Promotion, Reservation
from app.prompts import VARIANTS, build_prompt


def reserve_lot(db: Session, lot_id: int, user_id: int, quantity: int) -> Reservation:
    """Reserve stock atomically; callers commit the surrounding transaction."""
    lot = db.execute(select(Lot).where(Lot.id == lot_id).with_for_update()).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot is unavailable")
    expires_at = lot.expires_at.replace(tzinfo=timezone.utc) if lot.expires_at.tzinfo is None else lot.expires_at
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail="Lot is unavailable")
    if lot.quantity < quantity:
        raise HTTPException(status_code=409, detail="Not enough quantity available")
    lot.quantity -= quantity
    reservation = Reservation(lot_id=lot_id, user_id=user_id, quantity=quantity)
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def donate_lot(db: Session, lot_id: int, quantity: int) -> Donation:
    lot = db.execute(select(Lot).where(Lot.id == lot_id).with_for_update()).scalar_one_or_none()
    if not lot or lot.quantity < quantity:
        raise HTTPException(status_code=409, detail="Not enough quantity available")
    lot.quantity -= quantity
    donation = Donation(lot_id=lot_id, quantity=quantity)
    db.add(donation)
    db.commit()
    db.refresh(donation)
    return donation


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
