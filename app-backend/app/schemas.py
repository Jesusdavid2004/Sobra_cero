from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: Literal["business", "customer"] = "business"


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
    discount_percent: int = Field(ge=0, le=100)
    expires_at: datetime


class LotOut(LotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    image_url: str | None = None
    category: str = "other"
    business_type: Literal["restaurant", "supermarket"] = "restaurant"


class ReservationCreate(BaseModel):
    quantity: int = Field(gt=0, le=100)


class DonationCreate(BaseModel):
    quantity: int = Field(gt=0, le=10000)


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
