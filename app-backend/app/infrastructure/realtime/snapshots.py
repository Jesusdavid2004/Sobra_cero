from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.infrastructure.realtime.messages import lot_state
from app.models import Lot


def read_lot_states(lot_ids: set[int]) -> list[dict[str, Any]]:
    """Current public state of the requested lots, read from the database."""
    with SessionLocal() as db:
        rows = db.execute(
            select(Lot.id, Lot.version, Lot.quantity, Lot.status, Lot.discount_percent).where(Lot.id.in_(lot_ids))
        ).all()
    return [lot_state(row.id, row.version, row.quantity, row.status, row.discount_percent) for row in rows]
