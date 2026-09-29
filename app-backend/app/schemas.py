from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    is_admin: bool


class ShopCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
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
