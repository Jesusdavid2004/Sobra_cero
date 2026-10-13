from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.entities import BatchStatus, ReservationStatus


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="business", server_default="business")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    shops: Mapped[list["Shop"]] = relationship(back_populates="owner")


class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160))
    business_type: Mapped[str] = mapped_column(String(20), default="restaurant", server_default="restaurant")
    description: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[float] = mapped_column(default=0)
    longitude: Mapped[float] = mapped_column(default=0)
    owner: Mapped[User] = relationship(back_populates="shops")
    products: Mapped[list["Product"]] = relationship(back_populates="shop", cascade="all, delete-orphan")
    lots: Mapped[list["Lot"]] = relationship(back_populates="shop", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="other", server_default="other")
    shop: Mapped[Shop] = relationship(back_populates="products")
    lots: Mapped[list["Lot"]] = relationship(back_populates="product")


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'sold_out', 'expired', 'donated', 'cancelled')",
            name="ck_lots_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[int] = mapped_column(Integer)
    original_price_cents: Mapped[int] = mapped_column(Integer)
    discount_percent: Mapped[int] = mapped_column(Integer, default=30)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=BatchStatus.ACTIVE.value, server_default=BatchStatus.ACTIVE.value, index=True
    )
    shop: Mapped[Shop] = relationship(back_populates="lots")
    product: Mapped[Product] = relationship(back_populates="lots")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="lot", cascade="all, delete-orphan")

    @property
    def category(self) -> str:
        return self.product.category

    @property
    def business_type(self) -> str:
        return self.shop.business_type


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'cancelled', 'picked_up', 'expired')",
            name="ck_reservations_status",
        ),
        Index(
            "uq_reservations_active_lot_user",
            "lot_id",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'reserved'"),
            postgresql_where=text("status = 'reserved'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    pickup_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=ReservationStatus.RESERVED.value, server_default=ReservationStatus.RESERVED.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExpiryScanSuggestion(Base):
    __tablename__ = "expiry_scan_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_confirmation', 'confirmed', 'rejected', 'unreadable')",
            name="ck_expiry_scan_suggestions_status",
        ),
        Index("ix_expiry_scan_suggestions_lot_id", "lot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    printed_date: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="unreadable", server_default="unreadable")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Donation(Base):
    __tablename__ = "donations"
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Promotion(Base):
    __tablename__ = "promotions"
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    language: Mapped[str] = mapped_column(String(5), default="en")
    variant: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    lot: Mapped[Lot] = relationship(back_populates="promotions")


class SalesHistory(Base):
    __tablename__ = "sales_history"
    __table_args__ = (
        UniqueConstraint("product_id", "sales_date", name="uq_sales_history_product_date"),
        CheckConstraint("units_sold >= 0", name="ck_sales_history_nonnegative_units"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sales_date: Mapped[date] = mapped_column(Date, index=True)
    units_sold: Mapped[int] = mapped_column(Integer)
    had_promotion: Mapped[bool] = mapped_column(Boolean, default=False)


class WastePrediction(Base):
    __tablename__ = "waste_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    units_at_risk: Mapped[float] = mapped_column(Float)
    expected_sales: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(100), default="legacy", server_default="legacy")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SalesForecastModel(Base):
    __tablename__ = "sales_forecast_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(100), unique=True)
    artifact_json: Mapped[str] = mapped_column(Text)
    training_samples: Mapped[int] = mapped_column(Integer)
    evaluation_samples: Mapped[int] = mapped_column(Integer)
    baseline_mae: Mapped[float] = mapped_column(Float)
    model_mae: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), index=True)
    active_slot: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
