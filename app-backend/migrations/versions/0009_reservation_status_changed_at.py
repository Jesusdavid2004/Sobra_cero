"""Record when a reservation left the reserved state, so pickups and cancellations can be traced."""

from alembic import op
import sqlalchemy as sa

revision = "0009_reservation_status_changed_at"
down_revision = "0008_lot_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reservations", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("reservations", "status_changed_at")
