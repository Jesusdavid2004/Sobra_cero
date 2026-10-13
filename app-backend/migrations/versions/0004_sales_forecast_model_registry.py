"""Add persisted sales forecast artifacts and prediction provenance."""

from alembic import op
import sqlalchemy as sa

revision = "0004_sales_forecast_model_registry"
down_revision = "0003_roles_categories_and_pickup_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "waste_predictions",
        sa.Column("model_version", sa.String(length=100), nullable=False, server_default="legacy"),
    )
    op.create_table(
        "sales_forecast_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(length=100), nullable=False, unique=True),
        sa.Column("artifact_json", sa.Text(), nullable=False),
        sa.Column("training_samples", sa.Integer(), nullable=False),
        sa.Column("evaluation_samples", sa.Integer(), nullable=False),
        sa.Column("baseline_mae", sa.Float(), nullable=False),
        sa.Column("model_mae", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("active_slot", sa.String(length=10), nullable=True, unique=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_forecast_models_status", "sales_forecast_models", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sales_forecast_models_status", table_name="sales_forecast_models")
    op.drop_table("sales_forecast_models")
    op.drop_column("waste_predictions", "model_version")
