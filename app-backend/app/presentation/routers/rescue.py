from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.application.dto import Actor
from app.application.use_cases.explain_rescue_plan import ExplainRescuePlan
from app.application.use_cases.lot_timeline import GetLotTimeline
from app.application.use_cases.rescue_plan import (
    DecideRescuePlan,
    GenerateRescuePlan,
    ListRescuePlans,
)
from app.application.use_cases.simulate_rescue_plan import SimulateRescuePlan
from app.auth import current_user
from app.db import get_db
from app.dependencies import (
    build_decide_rescue_plan_use_case,
    build_explain_rescue_plan_use_case,
    build_generate_rescue_plan_use_case,
    build_get_lot_timeline_use_case,
    build_list_rescue_plans_use_case,
    build_simulate_rescue_plan_use_case,
)
from app.domain.rescue import RescuePlanStatus
from app.infrastructure.realtime.notifier import notify_lot_changed
from app.models import User
from app.presentation.rescue_schemas import (
    RescueExplanationOut,
    RescuePlanOut,
    ScenarioOut,
    SimulationOut,
    SimulationRequest,
    TimelineEventOut,
)

router = APIRouter(prefix="/api/v1", tags=["rescue-plans"])
REQUEST_ID_HEADER = "x-request-id"


def _actor(user: User) -> Actor:
    return Actor(user_id=user.id, role=user.role, is_admin=user.is_admin)  # type: ignore[arg-type]


@router.post("/lots/{lot_id}/rescue-plan", response_model=RescuePlanOut, status_code=201)
def generate_rescue_plan(
    lot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RescuePlanOut:
    use_case: GenerateRescuePlan = build_generate_rescue_plan_use_case(db)
    request_id = request.headers.get(REQUEST_ID_HEADER)
    return RescuePlanOut.from_entity(use_case.execute(lot_id, _actor(user), request_id=request_id))


@router.get("/shops/{shop_id}/rescue-plans", response_model=list[RescuePlanOut])
def list_rescue_plans(
    shop_id: int,
    status: RescuePlanStatus | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[RescuePlanOut]:
    use_case: ListRescuePlans = build_list_rescue_plans_use_case(db)
    return [RescuePlanOut.from_entity(plan) for plan in use_case.execute(shop_id, _actor(user), status)]


def _decide(plan_id: int, decision: Literal["approve", "reject"], db: Session, user: User) -> RescuePlanOut:
    use_case: DecideRescuePlan = build_decide_rescue_plan_use_case(db)
    plan = use_case.execute(plan_id, _actor(user), decision)
    notify_lot_changed(db, plan.lot_id)
    return RescuePlanOut.from_entity(plan)


@router.post("/rescue-plans/{plan_id}/approve", response_model=RescuePlanOut)
def approve_rescue_plan(
    plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> RescuePlanOut:
    return _decide(plan_id, "approve", db, user)


@router.post("/rescue-plans/{plan_id}/reject", response_model=RescuePlanOut)
def reject_rescue_plan(
    plan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> RescuePlanOut:
    return _decide(plan_id, "reject", db, user)


@router.post("/rescue-plans/{plan_id}/explanation", response_model=RescueExplanationOut)
def explain_rescue_plan(
    plan_id: int,
    language: Literal["en", "es"] = Query("en"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RescueExplanationOut:
    use_case: ExplainRescuePlan = build_explain_rescue_plan_use_case(db)
    return RescueExplanationOut(text=use_case.execute(plan_id, _actor(user), language))


@router.post("/rescue-plans/{plan_id}/simulation", response_model=SimulationOut)
def simulate_rescue_plan(
    plan_id: int,
    body: SimulationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SimulationOut:
    use_case: SimulateRescuePlan = build_simulate_rescue_plan_use_case(db)
    result = use_case.execute(plan_id, _actor(user), body.demand_uplift_percent, body.donation_units)
    return SimulationOut(
        stale=result.stale,
        demand_uplift_percent=result.demand_uplift_percent,
        donation_units=result.donation_units,
        scenarios=[ScenarioOut(**{**scenario.__dict__, "kind": scenario.kind.value}) for scenario in result.scenarios],
    )


@router.get("/lots/{lot_id}/timeline", response_model=list[TimelineEventOut])
def get_lot_timeline(
    lot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[TimelineEventOut]:
    use_case: GetLotTimeline = build_get_lot_timeline_use_case(db)
    events = use_case.execute(lot_id, _actor(user))
    return [TimelineEventOut(**{**event.__dict__, "kind": event.kind.value}) for event in events]
