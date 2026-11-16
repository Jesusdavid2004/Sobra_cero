"""Add tables for externally collected businesses, products, price history and collection runs."""

from alembic import op
import sqlalchemy as sa

revision = "0011_external_data"
down_revision = "0010_donation_receivers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("domain", sa.String(255), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("terms_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("terms_reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("terms_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terms_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("license_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("schedule_minutes", sa.Integer(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "external_businesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("external_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("normalized_name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address", sa.String(500), nullable=False, server_default=""),
        sa.Column("city", sa.String(80), nullable=False, server_default=""),
        sa.Column("website", sa.String(500), nullable=False, server_default=""),
        sa.Column("phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("opening_hours", sa.String(200), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("affiliation", sa.String(20), nullable=False, server_default="discovered"),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_external_businesses_source_external"),
        sa.CheckConstraint("affiliation IN ('prospect', 'discovered')", name="ck_external_businesses_affiliation"),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')",
            name="ck_external_businesses_verification",
        ),
    )
    op.create_index("ix_external_businesses_location", "external_businesses", ["latitude", "longitude"])
    op.create_index("ix_external_businesses_normalized_name", "external_businesses", ["normalized_name"])
    op.create_index("ix_external_businesses_category", "external_businesses", ["category"])
    op.create_table(
        "external_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("external_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(120), nullable=False, server_default=""),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("shop_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("current_price_cop", sa.Integer(), nullable=False),
        sa.Column("original_price_cop", sa.Integer(), nullable=True),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("availability", sa.String(80), nullable=False, server_default=""),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "url", name="uq_external_products_source_url"),
    )
    op.create_table(
        "external_price_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("external_products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("price_cop", sa.Integer(), nullable=False),
        sa.Column("original_price_cop", sa.Integer(), nullable=True),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_observations_product_time", "external_price_observations", ["product_id", "observed_at"])
    op.create_table(
        "scraping_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("external_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stop_reason", sa.String(60), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(500), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'stopped')", name="ck_scraping_executions_status"
        ),
    )
    op.create_index("ix_scraping_executions_source_started", "scraping_executions", ["source_id", "started_at"])
    op.create_table(
        "scraping_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_id", sa.Integer(), sa.ForeignKey("scraping_executions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(60), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("payload", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('rejected', 'pending_validation')", name="ck_scraping_records_status"),
    )
    op.create_index("ix_scraping_records_execution_id", "scraping_records", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_scraping_records_execution_id", table_name="scraping_records")
    op.drop_table("scraping_records")
    op.drop_index("ix_scraping_executions_source_started", table_name="scraping_executions")
    op.drop_table("scraping_executions")
    op.drop_index("ix_price_observations_product_time", table_name="external_price_observations")
    op.drop_table("external_price_observations")
    op.drop_table("external_products")
    op.drop_index("ix_external_businesses_category", table_name="external_businesses")
    op.drop_index("ix_external_businesses_normalized_name", table_name="external_businesses")
    op.drop_index("ix_external_businesses_location", table_name="external_businesses")
    op.drop_table("external_businesses")
    op.drop_table("external_sources")
