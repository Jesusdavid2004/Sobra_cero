"""Tables for data collected from outside the platform.

Kept apart from the marketplace tables on purpose: an external business is never an affiliated
shop, an external product is never stock, and nothing here becomes a lot or an offer.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now_utc


class ExternalSourceRow(Base):
    """A place data is collected from. A source may only run when a person reviewed its terms."""

    __tablename__ = "external_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(30))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    domain: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    terms_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    terms_reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    terms_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_note: Mapped[str] = mapped_column(Text, default="")
    license_note: Mapped[str] = mapped_column(Text, default="")
    schedule_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExternalBusinessRow(Base):
    """A business found in an external source. It is never an affiliated shop."""

    __tablename__ = "external_businesses"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_external_businesses_source_external"),
        Index("ix_external_businesses_location", "latitude", "longitude"),
        CheckConstraint("affiliation IN ('prospect', 'discovered')", name="ck_external_businesses_affiliation"),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')",
            name="ck_external_businesses_verification",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("external_sources.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    address: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    website: Mapped[str] = mapped_column(String(500), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    opening_hours: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    affiliation: Mapped[str] = mapped_column(String(20), default="discovered", server_default="discovered")
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified", server_default="unverified")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExternalProductRow(Base):
    """A product with the price a source published. It is not stock and not a surplus."""

    __tablename__ = "external_products"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_external_products_source_url"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("external_sources.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(500))
    shop_name: Mapped[str] = mapped_column(String(160), default="")
    current_price_cop: Mapped[int] = mapped_column(Integer)
    original_price_cop: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    availability: Mapped[str] = mapped_column(String(80), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PriceObservationRow(Base):
    __tablename__ = "external_price_observations"
    __table_args__ = (Index("ix_price_observations_product_time", "product_id", "observed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("external_products.id", ondelete="CASCADE"))
    price_cop: Mapped[int] = mapped_column(Integer)
    original_price_cop: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ScrapingExecutionRow(Base):
    __tablename__ = "scraping_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'stopped')",
            name="ck_scraping_executions_status",
        ),
        Index("ix_scraping_executions_source_started", "source_id", "started_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("external_sources.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_accepted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_pending: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    stop_reason: Mapped[str] = mapped_column(String(60), default="")
    error_message: Mapped[str] = mapped_column(String(500), default="")


class ScrapingRecordRow(Base):
    """A record that was rejected or is waiting for validation. Accepted records live in external_*."""

    __tablename__ = "scraping_records"
    __table_args__ = (
        CheckConstraint("status IN ('rejected', 'pending_validation')", name="ck_scraping_records_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("scraping_executions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(60), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    payload: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
