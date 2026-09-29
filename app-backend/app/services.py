from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Donation, Lot, Promotion, Reservation


def reserve_lot(db: Session, lot_id: int, user_id: int, quantity: int) -> Reservation:
    """Reserve stock atomically; callers commit the surrounding transaction."""
    lot = db.execute(select(Lot).where(Lot.id == lot_id).with_for_update()).scalar_one_or_none()
    expires_at = (
        lot.expires_at.replace(tzinfo=timezone.utc)
        if lot and lot.expires_at.tzinfo is None
        else lot.expires_at if lot else None
    )
    if not lot or expires_at <= datetime.now(timezone.utc):
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
    """Create auditable deterministic promo variants for the MVP/mock provider."""
    prompt = f"Create three short promotional texts for {lot.title}, discount {lot.discount_percent}%."
    templates = {
        "en": [
            f"Save {lot.discount_percent}% on {lot.title} before it expires!",
            f"Good food, less waste: {lot.title} at a special price.",
            f"Last chance for {lot.title}. Reserve yours today!",
        ],
        "es": [
            f"Ahorra un {lot.discount_percent}% en {lot.title} antes de que caduque.",
            f"Buena comida, menos desperdicio: {lot.title} a precio especial.",
            f"Ultima oportunidad para {lot.title}. Reservalo hoy.",
        ],
    }
    items = [
        Promotion(lot_id=lot.id, language=language, variant=f"variant-{index + 1}", text=text, prompt=prompt)
        for index, text in enumerate(templates.get(language, templates["en"]))
    ]
    db.add_all(items)
    db.commit()
    return items
