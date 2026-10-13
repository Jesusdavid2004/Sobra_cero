from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.rules import MAX_DISCOUNT_PERCENT


class AuthCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value


class UserCreate(AuthCredentials):
    role: Literal["business", "customer"] = "business"


class LoginRequest(AuthCredentials):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: Literal["business", "customer"]
    is_admin: bool


class ShopCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    business_type: Literal["restaurant", "supermarket"] = "restaurant"
    description: str = ""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ShopOut(ShopCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = ""
    category: str = Field(default="other", min_length=2, max_length=80)


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shop_id: int


class LotCreate(BaseModel):
    shop_id: int
    product_id: int
    title: str = Field(min_length=2, max_length=160)
    description: str = ""
    quantity: int = Field(gt=0, le=10000)
    original_price_cents: int = Field(ge=0)
    discount_percent: int = Field(ge=0, le=MAX_DISCOUNT_PERCENT)
    expires_at: datetime


class LotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shop_id: int
    product_id: int
    title: str
    description: str
    quantity: int = Field(ge=0, le=10000)
    original_price_cents: int = Field(ge=0)
    discount_percent: int = Field(ge=0, le=MAX_DISCOUNT_PERCENT)
    expires_at: datetime
    status: Literal["draft", "active", "sold_out", "expired", "donated", "cancelled"] = "active"
    image_url: str | None = None
    category: str = "other"
    business_type: Literal["restaurant", "supermarket"] = "restaurant"


class ReservationCreate(BaseModel):
    quantity: int = Field(gt=0, le=100)


class DonationCreate(BaseModel):
    quantity: int = Field(gt=0, le=10000)


class PickupConfirmation(BaseModel):
    pickup_code: str = Field(min_length=8, max_length=8, pattern="^[A-F0-9]{8}$")


class ExpiryScanSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    printed_date: str | None
    expires_on: date | None
    confidence: float = Field(ge=0, le=1)
    status: Literal["awaiting_confirmation", "confirmed", "rejected", "unreadable"]


class PromotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    language: str
    variant: str
    text: str
    prompt: str


class DailySalesCreate(BaseModel):
    sales_date: date
    units_sold: int = Field(ge=0, le=100000)
    had_promotion: bool = False


class SalesHistoryCreate(BaseModel):
    entries: list[DailySalesCreate] = Field(min_length=1, max_length=90)


class SalesHistoryCreated(BaseModel):
    created: int
    existing: int


class WasteRiskOut(BaseModel):
    product_id: int
    product_name: str
    lot_id: int
    current_stock: int
    days_remaining: int
    data_points: int
    average_daily_sales: float
    expected_sales: float
    units_at_risk: float
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high"]
    recommendation: str
    calculated_at: datetime
    prediction_model: str


class SalesForecastTrainingOut(BaseModel):
    model_version: str
    training_samples: int
    evaluation_samples: int
    baseline_mae: float
    model_mae: float
    activated: bool
