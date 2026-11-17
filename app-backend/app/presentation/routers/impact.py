from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.dto import Actor
from app.application.use_cases.shop_impact import GetShopImpact
from app.auth import current_user
from app.db import get_db
from app.dependencies import build_get_shop_impact_use_case
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["impact"])


class ShopImpactOut(BaseModel):
    picked_up_units: int
    donated_units: int
    pending_units: int
    cancelled_units: int
    expired_units: int
    estimated_revenue_cents: int
    estimated_savings_cents: int


@router.get("/shops/{shop_id}/impact", response_model=ShopImpactOut)
def get_shop_impact(shop_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> ShopImpactOut:
    use_case: GetShopImpact = build_get_shop_impact_use_case(db)
    actor = Actor(user_id=user.id, role=user.role, is_admin=user.is_admin)  # type: ignore[arg-type]
    impact = use_case.execute(shop_id, actor)
    return ShopImpactOut(**impact.__dict__)
