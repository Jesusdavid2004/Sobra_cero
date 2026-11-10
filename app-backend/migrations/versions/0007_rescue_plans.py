"""Add rescue plans, their audit events, and an optional lot pickup deadline."""

from alembic import op
import sqlalchemy as sa

revision = "0007_rescue_plans"
down_revision = "0006_expiry_scan_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("pickup_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "rescue_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("expected_sales", sa.Float(), nullable=True),
        sa.Column("surplus_units", sa.Float(), nullable=True),
        sa.Column("proposed_discount_percent", sa.Integer(), nullable=True),
        sa.Column("horizon_hours", sa.Float(), nullable=False),
        sa.Column("data_points", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.String(length=40), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'superseded', 'not_actionable')",
            name="ck_rescue_plans_status",
        ),
        sa.CheckConstraint(
            "action IN ('keep_offer', 'apply_discount_rule', 'prepare_donation_offer', 'insufficient_history')",
            name="ck_rescue_plans_action",
        ),
        sa.ForeignKeyConstraint(["lot_id"], ["lots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rescue_plans_lot_id", "rescue_plans", ["lot_id"])
    op.create_index("ix_rescue_plans_shop_id", "rescue_plans", ["shop_id"])
    op.create_index(
        "uq_rescue_plans_pending_lot",
        "rescue_plans",
        ["lot_id"],
        unique=True,
        sqlite_where=sa.text("status = 'pending_approval'"),
        postgresql_where=sa.text("status = 'pending_approval'"),
    )
    op.create_table(
        "rescue_plan_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["rescue_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rescue_plan_events_plan_id", "rescue_plan_events", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_rescue_plan_events_plan_id", table_name="rescue_plan_events")
    op.drop_table("rescue_plan_events")
    op.drop_index("uq_rescue_plans_pending_lot", table_name="rescue_plans")
    op.drop_index("ix_rescue_plans_shop_id", table_name="rescue_plans")
    op.drop_index("ix_rescue_plans_lot_id", table_name="rescue_plans")
    op.drop_table("rescue_plans")
    op.drop_column("lots", "pickup_ends_at")
