import logging
from datetime import datetime, timezone

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.events import LotStockChanged
from app.models import Lot

logger = logging.getLogger(__name__)


def notify_lot_changed(db: Session, lot_id: int) -> None:
    """Announce a committed lot change. Best effort: realtime must never fail a reservation."""
    from app.dependencies import get_lot_event_publisher

    try:
        row = db.execute(
            select(Lot.version, Lot.quantity, Lot.status, Lot.discount_percent).where(Lot.id == lot_id)
        ).one_or_none()
        if row is None:
            return
        get_lot_event_publisher().publish(
            LotStockChanged(
                lot_id=lot_id,
                version=row.version,
                quantity=row.quantity,
                status=row.status,
                discount_percent=row.discount_percent,
                occurred_at=datetime.now(timezone.utc),
            )
        )
    except (RedisError, SQLAlchemyError, RuntimeError, OSError):
        logger.warning("Could not publish a lot event", extra={"lot_id": lot_id})
