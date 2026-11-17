"""Add the waste a shop declares for its lots."""

from alembic import op
import sqlalchemy as sa

revision = "0012_waste_records"
down_revision = "0011_external_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waste_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("note", sa.String(200), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("reason IN ('expired', 'damaged', 'unsold', 'other')", name="ck_waste_records_reason"),
        sa.CheckConstraint("quantity > 0", name="ck_waste_records_quantity"),
    )
    op.create_index("ix_waste_records_lot_time", "waste_records", ["lot_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_waste_records_lot_time", table_name="waste_records")
    op.drop_table("waste_records")
