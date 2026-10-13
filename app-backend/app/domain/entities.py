from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.exceptions import (
    BatchExpiredError,
    BatchNotReservableError,
    InsufficientStockError,
    InvalidBatchQuantityError,
)
from app.domain.value_objects import DiscountPercent, Money


class BatchStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SOLD_OUT = "sold_out"
    EXPIRED = "expired"
    DONATED = "donated"


class OfferType(StrEnum):
    SALE = "sale"
    DONATION = "donation"
    BOTH = "both"


@dataclass
class Batch:
    id: int | None
    quantity: int
    available_quantity: int
    expiration_date: datetime
    original_price: Money
    discount_percent: DiscountPercent
    status: BatchStatus
    offer_type: OfferType
    photo_key: str | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise InvalidBatchQuantityError("Batch quantity must be positive")
        if not 0 <= self.available_quantity <= self.quantity:
            raise InvalidBatchQuantityError("Available quantity must be between zero and batch quantity")
        if self.expiration_date.tzinfo is None or self.expiration_date.utcoffset() is None:
            raise ValueError("Batch expiration date must be timezone-aware")

    def is_reservable(self, now: datetime) -> bool:
        return (
            self.status is BatchStatus.ACTIVE
            and self.available_quantity > 0
            and self.expiration_date > now
            and self.offer_type in {OfferType.SALE, OfferType.BOTH}
        )

    def apply_discount(self, percent: DiscountPercent) -> None:
        if self.status not in {BatchStatus.DRAFT, BatchStatus.ACTIVE}:
            raise BatchNotReservableError("Discount cannot be changed for a terminal batch")
        self.discount_percent = percent

    def reserve(self, quantity: int, now: datetime) -> None:
        if quantity <= 0:
            raise InvalidBatchQuantityError("Reservation quantity must be positive")
        if self.expiration_date <= now:
            raise BatchExpiredError("Batch has expired")
        if self.status is not BatchStatus.ACTIVE:
            raise BatchNotReservableError("Batch is not active")
        if self.offer_type is OfferType.DONATION:
            raise BatchNotReservableError("Batch is not offered for sale")
        if quantity > self.available_quantity:
            raise InsufficientStockError("Not enough batch stock available")
        self.available_quantity -= quantity
        if self.available_quantity == 0:
            self.status = BatchStatus.SOLD_OUT

    def expire_if_due(self, now: datetime) -> bool:
        if self.status is not BatchStatus.ACTIVE or self.expiration_date > now:
            return False
        self.status = BatchStatus.EXPIRED
        return True
