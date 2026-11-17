"""Add account roles, catalog filters, and reservation pickup codes."""

from secrets import token_hex

from alembic import op
from sqlalchemy import Column, Integer, String, inspect, select, table, update

revision = "0003_roles_categories_and_pickup_codes"
down_revision = "0002_sales_history_and_waste_predictions"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "users" in tables and "role" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column("users", Column("role", String(20), nullable=False, server_default="business"))
    if "shops" in tables and "business_type" not in {
        column["name"] for column in inspector.get_columns("shops")
    }:
        op.add_column("shops", Column("business_type", String(20), nullable=False, server_default="restaurant"))
    if "products" in tables and "category" not in {column["name"] for column in inspector.get_columns("products")}:
        op.add_column("products", Column("category", String(80), nullable=False, server_default="other"))

    if "reservations" in tables:
        reservation_columns = {column["name"] for column in inspector.get_columns("reservations")}
        if "pickup_code" not in reservation_columns:
            op.add_column("reservations", Column("pickup_code", String(8), nullable=True))
            reservation_table = table("reservations", Column("id", Integer), Column("pickup_code", String(8)))
            connection = op.get_bind()
            missing_codes = connection.execute(
                select(reservation_table.c.id).where(reservation_table.c.pickup_code.is_(None))
            )
            for row in missing_codes:
                connection.execute(
                    update(reservation_table)
                    .where(reservation_table.c.id == row.id)
                    .values(pickup_code=token_hex(4).upper())
                )
            with op.batch_alter_table("reservations") as batch_op:
                batch_op.alter_column("pickup_code", existing_type=String(8), nullable=False)
        indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("reservations")}
        if "ix_reservations_pickup_code" not in indexes:
            op.create_index("ix_reservations_pickup_code", "reservations", ["pickup_code"], unique=True)


def downgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "reservations" in tables:
        indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("reservations")}
        if "ix_reservations_pickup_code" in indexes:
            op.drop_index("ix_reservations_pickup_code", table_name="reservations")
        if "pickup_code" in {column["name"] for column in inspect(op.get_bind()).get_columns("reservations")}:
            with op.batch_alter_table("reservations") as batch_op:
                batch_op.drop_column("pickup_code")
    for table_name, column_name in (
        ("products", "category"),
        ("shops", "business_type"),
        ("users", "role"),
    ):
        if table_name in tables and column_name in {
            column["name"] for column in inspect(op.get_bind()).get_columns(table_name)
        }:
            op.drop_column(table_name, column_name)
