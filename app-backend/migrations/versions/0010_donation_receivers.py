"""Add donation receivers and the offers made to them."""

from alembic import op
import sqlalchemy as sa

revision = "0010_donation_receivers"
down_revision = "0009_reservation_status_changed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accepted_categories", sa.String(200), nullable=False),
        sa.Column("max_quantity", sa.Integer(), nullable=False),
        sa.Column("can_store_refrigerated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("open_from_minute", sa.Integer(), nullable=False),
        sa.Column("open_until_minute", sa.Integer(), nullable=False),
        sa.Column("utc_offset_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", name="uq_receivers_owner_user_id"),
    )
    op.create_table(
        "donation_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receiver_id", sa.Integer(), sa.ForeignKey("receivers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="offered"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('offered', 'accepted', 'declined', 'delivered')", name="ck_donation_offers_status"
        ),
    )
    op.create_index("ix_donation_offers_lot_id", "donation_offers", ["lot_id"])
    op.create_index("ix_donation_offers_receiver_id", "donation_offers", ["receiver_id"])
    op.create_index(
        "uq_donation_offers_active_lot_receiver",
        "donation_offers",
        ["lot_id", "receiver_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('offered', 'accepted')"),
        postgresql_where=sa.text("status IN ('offered', 'accepted')"),
    )


def downgrade() -> None:
    op.drop_index("uq_donation_offers_active_lot_receiver", table_name="donation_offers")
    op.drop_index("ix_donation_offers_receiver_id", table_name="donation_offers")
    op.drop_index("ix_donation_offers_lot_id", table_name="donation_offers")
    op.drop_table("donation_offers")
    op.drop_table("receivers")
