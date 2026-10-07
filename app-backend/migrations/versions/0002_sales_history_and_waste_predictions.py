"""Add private sales history and persisted waste-risk predictions."""

from alembic import op
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    inspect,
)

revision = "0002_sales_history_and_waste_predictions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "sales_history" not in existing_tables:
        op.create_table(
            "sales_history",
            Column("id", Integer, primary_key=True),
            Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            Column("sales_date", Date, nullable=False),
            Column("units_sold", Integer, nullable=False),
            Column("had_promotion", Boolean, nullable=False, server_default="false"),
            CheckConstraint("units_sold >= 0", name="ck_sales_history_nonnegative_units"),
            UniqueConstraint("product_id", "sales_date", name="uq_sales_history_product_date"),
        )
    if "waste_predictions" not in existing_tables:
        op.create_table(
            "waste_predictions",
            Column("id", Integer, primary_key=True),
            Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            Column("lot_id", Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False),
            Column("risk_score", Integer, nullable=False),
            Column("units_at_risk", Float, nullable=False),
            Column("expected_sales", Float, nullable=False),
            Column("recommendation", Text, nullable=False),
            Column("calculated_at", DateTime(timezone=True), nullable=False),
        )
    existing_indexes = (
        {(index["name"], index["column_names"][0]) for index in inspect(op.get_bind()).get_indexes("sales_history")}
        if "sales_history" in set(inspect(op.get_bind()).get_table_names())
        else set()
    )
    if ("ix_sales_history_product_id", "product_id") not in existing_indexes:
        op.create_index("ix_sales_history_product_id", "sales_history", ["product_id"])
    if ("ix_sales_history_sales_date", "sales_date") not in existing_indexes:
        op.create_index("ix_sales_history_sales_date", "sales_history", ["sales_date"])
    for table_name, column in (("waste_predictions", "product_id"), ("waste_predictions", "lot_id")):
        indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}
        index_name = f"ix_waste_predictions_{column}"
        if index_name not in indexes:
            op.create_index(index_name, table_name, [column])


def downgrade():
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "waste_predictions" in existing_tables:
        op.drop_table("waste_predictions")
    if "sales_history" in existing_tables:
        op.drop_table("sales_history")
