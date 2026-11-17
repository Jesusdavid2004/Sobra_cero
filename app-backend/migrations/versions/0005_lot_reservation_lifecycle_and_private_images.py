"""Add lot/reservation lifecycle state and private image keys."""

from alembic import op
import sqlalchemy as sa

revision = "0005_lot_reservation_lifecycle_and_private_images"
down_revision = "0004_sales_forecast_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lots",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("lots", sa.Column("image_key", sa.String(length=512), nullable=True))
    op.add_column(
        "reservations",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="reserved"),
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute("UPDATE lots SET status = 'expired' WHERE julianday(expires_at) <= julianday(CURRENT_TIMESTAMP)")
    else:
        op.execute("UPDATE lots SET status = 'expired' WHERE expires_at <= CURRENT_TIMESTAMP")
    op.execute("UPDATE lots SET status = 'sold_out' WHERE quantity = 0 AND status = 'active'")
    op.execute(
        "UPDATE reservations SET status = 'expired' WHERE lot_id IN "
        "(SELECT id FROM lots WHERE status = 'expired')"
    )
    op.execute(
        "UPDATE reservations SET status = 'cancelled' WHERE id NOT IN "
        "(SELECT MIN(id) FROM reservations WHERE status = 'reserved' GROUP BY lot_id, user_id) "
        "AND status = 'reserved'"
    )
    with op.batch_alter_table("lots") as batch_op:
        batch_op.create_check_constraint(
            "ck_lots_status",
            "status IN ('draft', 'active', 'sold_out', 'expired', 'donated', 'cancelled')",
        )
    with op.batch_alter_table("reservations") as batch_op:
        batch_op.create_check_constraint(
            "ck_reservations_status",
            "status IN ('reserved', 'cancelled', 'picked_up', 'expired')",
        )
    op.create_index("ix_lots_status", "lots", ["status"])
    op.create_index(
        "uq_reservations_active_lot_user",
        "reservations",
        ["lot_id", "user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'reserved'"),
        postgresql_where=sa.text("status = 'reserved'"),
    )


def downgrade() -> None:
    op.drop_index("uq_reservations_active_lot_user", table_name="reservations")
    op.drop_index("ix_lots_status", table_name="lots")
    with op.batch_alter_table("reservations") as batch_op:
        batch_op.drop_constraint("ck_reservations_status", type_="check")
    with op.batch_alter_table("lots") as batch_op:
        batch_op.drop_constraint("ck_lots_status", type_="check")
    op.drop_column("reservations", "status")
    op.drop_column("lots", "image_key")
    op.drop_column("lots", "status")
