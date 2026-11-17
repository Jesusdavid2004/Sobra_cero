"""Wire format of the lot stream. One place, so the hub, the publishers and the tests agree."""

from datetime import timezone
from typing import Any

from app.domain.events import LotStockChanged

EVENT_STOCK_CHANGED = "lot.stock_changed"
MESSAGE_SNAPSHOT = "snapshot"
MESSAGE_ERROR = "error"
LOT_EVENTS_CHANNEL = "sobracero:lot-events"


def lot_state(lot_id: int, version: int, quantity: int, status: str, discount_percent: int) -> dict[str, Any]:
    return {
        "lot_id": lot_id,
        "version": version,
        "quantity": quantity,
        "status": status,
        "discount_percent": discount_percent,
    }


def event_message(event: LotStockChanged) -> dict[str, Any]:
    occurred_at = event.occurred_at.astimezone(timezone.utc).isoformat()
    return {
        "type": EVENT_STOCK_CHANGED,
        **lot_state(event.lot_id, event.version, event.quantity, event.status, event.discount_percent),
        "occurred_at": occurred_at,
    }


def snapshot_message(lots: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": MESSAGE_SNAPSHOT, "lots": lots}


def error_message(code: str) -> dict[str, Any]:
    return {"type": MESSAGE_ERROR, "code": code}
