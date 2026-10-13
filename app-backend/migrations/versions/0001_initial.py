"""Create the initial catalog, account, and reservation schema."""

from alembic import op
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    inspect,
)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing_tables = set(inspect(op.get_bind()).get_table_names())

    if "users" not in existing_tables:
        op.create_table(
            "users",
            Column("id", Integer, primary_key=True),
            Column("email", String(255), nullable=False),
            Column("password_hash", String(255), nullable=False),
            Column("is_admin", Boolean, nullable=False),
        )
    if "shops" not in existing_tables:
        op.create_table(
            "shops",
            Column("id", Integer, primary_key=True),
            Column("owner_id", Integer, ForeignKey("users.id"), nullable=False),
            Column("name", String(160), nullable=False),
            Column("description", Text, nullable=False),
            Column("latitude", Float, nullable=False),
            Column("longitude", Float, nullable=False),
        )
    if "products" not in existing_tables:
        op.create_table(
            "products",
            Column("id", Integer, primary_key=True),
            Column("shop_id", Integer, ForeignKey("shops.id"), nullable=False),
            Column("name", String(160), nullable=False),
            Column("description", Text, nullable=False),
        )
    if "lots" not in existing_tables:
        op.create_table(
            "lots",
            Column("id", Integer, primary_key=True),
            Column("shop_id", Integer, ForeignKey("shops.id"), nullable=False),
            Column("product_id", Integer, ForeignKey("products.id"), nullable=False),
            Column("title", String(160), nullable=False),
            Column("description", Text, nullable=False),
            Column("quantity", Integer, nullable=False),
            Column("original_price_cents", Integer, nullable=False),
            Column("discount_percent", Integer, nullable=False),
            Column("expires_at", DateTime(timezone=True), nullable=False),
            Column("image_url", String(500), nullable=True),
        )
    if "reservations" not in existing_tables:
        op.create_table(
            "reservations",
            Column("id", Integer, primary_key=True),
            Column("lot_id", Integer, ForeignKey("lots.id"), nullable=False),
            Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
            Column("quantity", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
    if "donations" not in existing_tables:
        op.create_table(
            "donations",
            Column("id", Integer, primary_key=True),
            Column("lot_id", Integer, ForeignKey("lots.id"), nullable=False),
            Column("quantity", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
    if "promotions" not in existing_tables:
        op.create_table(
            "promotions",
            Column("id", Integer, primary_key=True),
            Column("lot_id", Integer, ForeignKey("lots.id"), nullable=False),
            Column("language", String(5), nullable=False),
            Column("variant", String(30), nullable=False),
            Column("text", Text, nullable=False),
            Column("prompt", Text, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )

    existing_indexes = {
        (index["name"], tuple(index["column_names"]))
        for table_name in ("users", "lots")
        for index in inspect(op.get_bind()).get_indexes(table_name)
    }
    if ("ix_users_email", ("email",)) not in existing_indexes:
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if ("ix_lots_expires_at", ("expires_at",)) not in existing_indexes:
        op.create_index("ix_lots_expires_at", "lots", ["expires_at"])


def downgrade():
    raise RuntimeError("The initial migration cannot be downgraded safely after adopting an existing schema")
