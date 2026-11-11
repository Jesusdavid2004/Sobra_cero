import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.domain.rules import MAX_DISCOVERY_QUANTITY, MAX_PARSED_BUDGET

CLOCK_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
CATEGORY_PATTERN = re.compile(r"^[a-z_]{2,40}$")


class PromotionCopy(BaseModel):
    text: str = Field(min_length=1, max_length=240)

    @field_validator("text")
    @classmethod
    def limit_to_25_words(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value.split()) > 25:
            raise ValueError("Promotion text must not exceed 25 words")
        return value


class RiskAdvice(BaseModel):
    text: str = Field(min_length=1, max_length=400)

    @field_validator("text")
    @classmethod
    def keep_advice_qualitative(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value.split()) > 50 or any(character.isdigit() for character in value):
            raise ValueError("Risk advice must be brief and must not introduce numeric decisions")
        return value


class RescueExplanation(BaseModel):
    text: str = Field(min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def keep_explanation_qualitative(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value.split()) > 70 or any(character.isdigit() for character in value):
            raise ValueError("Rescue explanation must be brief and must not state any numbers")
        return value


class ExpiryDateRead(BaseModel):
    printed_date: str | None = Field(default=None, max_length=80)
    expires_on: date | None = None
    confidence: float = Field(ge=0, le=1)


class DiscoveryIntent(BaseModel):
    """Search constraints that the customer wrote in free text; every field is null unless stated."""

    budget: float | None = Field(default=None, ge=0, le=MAX_PARSED_BUDGET)
    pickup_from: str | None = None
    pickup_until: str | None = None
    quantity: int | None = Field(default=None, ge=1, le=MAX_DISCOVERY_QUANTITY)
    category: str | None = None

    @field_validator("pickup_from", "pickup_until")
    @classmethod
    def require_clock_time(cls, value: str | None) -> str | None:
        if value is not None and not CLOCK_TIME_PATTERN.match(value):
            raise ValueError("Times must use the 24-hour HH:MM format")
        return value

    @field_validator("category")
    @classmethod
    def require_category_slug(cls, value: str | None) -> str | None:
        if value is not None and not CATEGORY_PATTERN.match(value):
            raise ValueError("Category must be a lowercase word")
        return value
