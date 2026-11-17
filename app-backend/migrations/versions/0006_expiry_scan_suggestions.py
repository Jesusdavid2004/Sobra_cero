"""Persist expiry-date reads until explicit business confirmation."""

from alembic import op
import sqlalchemy as sa

revision = "0006_expiry_scan_suggestions"
down_revision = "0005_lot_reservation_lifecycle_and_private_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expiry_scan_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("printed_date", sa.String(length=80), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="unreadable", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('awaiting_confirmation', 'confirmed', 'rejected', 'unreadable')",
            name="ck_expiry_scan_suggestions_status",
        ),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expiry_scan_suggestions_lot_id", "expiry_scan_suggestions", ["lot_id"])


def downgrade() -> None:
    op.drop_index("ix_expiry_scan_suggestions_lot_id", table_name="expiry_scan_suggestions")
    op.drop_table("expiry_scan_suggestions")
