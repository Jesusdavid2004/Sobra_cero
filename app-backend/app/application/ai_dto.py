from datetime import date

from pydantic import BaseModel, Field, field_validator


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


class ExpiryDateRead(BaseModel):
    printed_date: str | None = Field(default=None, max_length=80)
    expires_on: date | None = None
    confidence: float = Field(ge=0, le=1)
