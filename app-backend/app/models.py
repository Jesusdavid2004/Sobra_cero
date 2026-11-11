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
    pickup_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class RescuePlanRecord(Base):
    __tablename__ = "rescue_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'superseded', 'not_actionable')",
            name="ck_rescue_plans_status",
        ),
        CheckConstraint(
            "action IN ('keep_offer', 'apply_discount_rule', 'prepare_donation_offer', 'insufficient_history')",
            name="ck_rescue_plans_action",
        ),
        Index(
            "uq_rescue_plans_pending_lot",
            "lot_id",
            unique=True,
            sqlite_where=text("status = 'pending_approval'"),
            postgresql_where=text("status = 'pending_approval'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(30))
    reasons_json: Mapped[str] = mapped_column(Text)
    available_quantity: Mapped[int] = mapped_column(Integer)
    expected_sales: Mapped[float | None] = mapped_column(Float, nullable=True)
    surplus_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    horizon_hours: Mapped[float] = mapped_column(Float)
    data_points: Mapped[int] = mapped_column(Integer)
    rule_version: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(100))
    inputs_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RescuePlanEventRecord(Base):
    __tablename__ = "rescue_plan_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("rescue_plans.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


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


class ReceiverRecord(Base):
    __tablename__ = "receivers"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accepted_categories: Mapped[str] = mapped_column(String(200))
    max_quantity: Mapped[int] = mapped_column(Integer)
    can_store_refrigerated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    open_from_minute: Mapped[int] = mapped_column(Integer)
    open_until_minute: Mapped[int] = mapped_column(Integer)
    utc_offset_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DonationOfferRecord(Base):
    __tablename__ = "donation_offers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('offered', 'accepted', 'declined', 'delivered')",
            name="ck_donation_offers_status",
        ),
        Index(
            "uq_donation_offers_active_lot_receiver",
            "lot_id",
            "receiver_id",
            unique=True,
            sqlite_where=text("status IN ('offered', 'accepted')"),
            postgresql_where=text("status IN ('offered', 'accepted')"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"), index=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("receivers.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="offered", server_default="offered")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
