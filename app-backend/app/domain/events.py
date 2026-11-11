from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LotStockChanged:
    """A public fact about a lot. It carries no personal data and never a pickup code."""

    lot_id: int
    version: int
    quantity: int
    status: str
    discount_percent: int
    occurred_at: datetime
