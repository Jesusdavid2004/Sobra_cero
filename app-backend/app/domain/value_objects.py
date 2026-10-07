from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.domain.exceptions import RiskScoreValidationError


@dataclass(frozen=True)
class RiskScore:
    value: int

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise RiskScoreValidationError("Risk score must be between 0 and 100")

    @property
    def level(self) -> Literal["low", "medium", "high"]:
        if self.value >= 70:
            return "high"
        if self.value >= 35:
            return "medium"
        return "low"


class BusinessType(StrEnum):
    RESTAURANT = "restaurant"
    SUPERMARKET = "supermarket"
