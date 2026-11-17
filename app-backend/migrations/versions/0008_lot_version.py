"""Add a per-lot version that increases on every stock or price change."""

from alembic import op
import sqlalchemy as sa

revision = "0008_lot_version"
down_revision = "0007_rescue_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("lots", "version")
