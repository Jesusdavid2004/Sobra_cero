from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.rescue import RescuePlan


class RescueExplanationOut(BaseModel):
    text: str
    source: Literal["ai"] = "ai"


class RescuePlanOut(BaseModel):
    id: int
    lot_id: int
    shop_id: int
    status: Literal["pending_approval", "approved", "rejected", "superseded", "not_actionable"]
    action: Literal["keep_offer", "apply_discount_rule", "prepare_donation_offer", "insufficient_history"]
    reasons: list[str]
    available_quantity: int
    expected_sales: float | None
    surplus_units: float | None
    proposed_discount_percent: int | None
    horizon_hours: float
    data_points: int
    rule_version: str
    model_version: str
    created_at: datetime
    decided_at: datetime | None

    @classmethod
    def from_entity(cls, plan: RescuePlan) -> "RescuePlanOut":
        assert plan.id is not None
        return cls(
            id=plan.id,
            lot_id=plan.lot_id,
            shop_id=plan.shop_id,
            status=plan.status.value,
            action=plan.action.value,
            reasons=[reason.value for reason in plan.reasons],
            available_quantity=plan.available_quantity,
            expected_sales=plan.expected_sales,
            surplus_units=plan.surplus_units,
            proposed_discount_percent=plan.proposed_discount_percent,
            horizon_hours=plan.horizon_hours,
            data_points=plan.data_points,
            rule_version=plan.rule_version,
            model_version=plan.model_version,
            created_at=plan.created_at,
            decided_at=plan.decided_at,
        )
