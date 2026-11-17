import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from app.domain.exceptions import (
    DiscountPercentValidationError,
    InvalidMoneyError,
    RiskScoreValidationError,
)

from .rules import HIGH_RISK_THRESHOLD, MAX_DISCOUNT_PERCENT, MEDIUM_RISK_THRESHOLD


@dataclass(frozen=True)
class RiskScore:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or not 0 <= self.value <= 100:
            raise RiskScoreValidationError("Risk score must be between 0 and 100")

    @property
    def level(self) -> Literal["low", "medium", "high"]:
        if self.value >= HIGH_RISK_THRESHOLD:
            return "high"
        if self.value >= MEDIUM_RISK_THRESHOLD:
            return "medium"
        return "low"


class BusinessType(StrEnum):
    RESTAURANT = "restaurant"
    SUPERMARKET = "supermarket"


@dataclass(frozen=True)
class DiscountPercent:
    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or not 0 <= self.value <= MAX_DISCOUNT_PERCENT
        ):
            raise DiscountPercentValidationError(f"Discount must be between 0 and {MAX_DISCOUNT_PERCENT} percent")


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount < 0:
            raise InvalidMoneyError("Money amount must be finite and non-negative")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise InvalidMoneyError("Currency must be a three-letter uppercase code")
