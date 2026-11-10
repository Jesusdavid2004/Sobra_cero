from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Literal

from app.application.dto import Actor, DailySales, LotSnapshot
from app.application.ports import (
    PredictionModel,
    RescueLotGateway,
    RescuePlanRepository,
    SalesHistoryRepository,
    UnitOfWork,
)
from app.domain.entities import BatchStatus
from app.domain.exceptions import (
    InvalidRescuePlanTransitionError,
    LotNotRescuableError,
    RescueLotNotFoundError,
    RescuePermissionError,
    RescuePlanNotFoundError,
    RescuePlanStaleError,
)
from app.domain.rescue import (
    RescueAction,
    RescuePlan,
    RescuePlanStatus,
    RescueReason,
    decide_rescue,
)
from app.domain.rules import (
    HOURS_PER_DAY,
    MIN_HISTORY_DAYS,
    RESCUE_HISTORY_LOOKBACK_DAYS,
    RESCUE_RULE_VERSION,
)

NO_MODEL_VERSION = "none"
SECONDS_PER_HOUR = 3600
EVENT_GENERATED = "generated"
EVENT_SUPERSEDED = "superseded"
EVENT_APPROVED = "approved"
EVENT_REJECTED = "rejected"
EVENT_DISCOUNT_APPLIED = "discount_applied"

Decision = Literal["approve", "reject"]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _require_shop_actor(actor: Actor) -> None:
    if not actor.can_manage_shops:
        raise RescuePermissionError("Business account required")


def _operating_deadline(snapshot: LotSnapshot) -> datetime:
    deadlines = [_as_utc(snapshot.expires_at)]
    if snapshot.pickup_ends_at is not None:
        deadlines.append(_as_utc(snapshot.pickup_ends_at))
    return min(deadlines)


def _hours_until(deadline: datetime, moment: datetime) -> float:
    return (deadline - moment).total_seconds() / SECONDS_PER_HOUR


def _is_rescuable(snapshot: LotSnapshot, moment: datetime) -> bool:
    return (
        snapshot.status == BatchStatus.ACTIVE.value
        and snapshot.quantity > 0
        and _hours_until(_operating_deadline(snapshot), moment) > 0
    )


class GenerateRescuePlan:
    def __init__(
        self,
        lots: RescueLotGateway,
        plans: RescuePlanRepository,
        history: SalesHistoryRepository,
        prediction_model: PredictionModel,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._lots = lots
        self._plans = plans
        self._history = history
        self._prediction_model = prediction_model
        self._unit_of_work = unit_of_work

    def execute(self, lot_id: int, actor: Actor, now: datetime | None = None) -> RescuePlan:
        _require_shop_actor(actor)
        moment = now or datetime.now(timezone.utc)
        snapshot = self._lots.get_snapshot(lot_id)
        if snapshot is None or (snapshot.owner_id != actor.user_id and not actor.is_admin):
            raise RescueLotNotFoundError("Lot not found")
        if not _is_rescuable(snapshot, moment):
            raise LotNotRescuableError("Lot is not active, has no stock, or is past its operating deadline")

        history = self._history.list_for_product(
            snapshot.product_id, moment.date() - timedelta(days=RESCUE_HISTORY_LOOKBACK_DAYS - 1)
        )
        plan = self._build_plan(snapshot, actor, moment, history)
        superseded = self._plans.supersede_pending_for_lot(lot_id)
        saved = self._plans.add(plan)
        assert saved.id is not None
        for plan_id in superseded:
            self._plans.record_event(plan_id, EVENT_SUPERSEDED, actor.user_id, {"superseded_by": saved.id})
        self._plans.record_event(saved.id, EVENT_GENERATED, actor.user_id, {"action": saved.action.value})
        self._unit_of_work.commit()
        return saved

    def _build_plan(
        self,
        snapshot: LotSnapshot,
        actor: Actor,
        moment: datetime,
        history: list[DailySales],
    ) -> RescuePlan:
        deadline = _operating_deadline(snapshot)
        hours_left = _hours_until(deadline, moment)
        inputs: dict[str, object] = {
            "quantity": snapshot.quantity,
            "discount_percent": snapshot.discount_percent,
            "expires_at": _as_utc(snapshot.expires_at).isoformat(),
            "pickup_ends_at": snapshot.pickup_ends_at.isoformat() if snapshot.pickup_ends_at else None,
            "operating_deadline": deadline.isoformat(),
            "history_days": len(history),
        }
        horizon_days = max(1, ceil(hours_left / HOURS_PER_DAY))
        if len(history) < MIN_HISTORY_DAYS:
            status = RescuePlanStatus.NOT_ACTIONABLE
            action = RescueAction.INSUFFICIENT_HISTORY
            reasons: tuple[RescueReason, ...] = (RescueReason.INSUFFICIENT_HISTORY,)
            expected_sales: float | None = None
            surplus_units: float | None = None
            proposed_discount: int | None = None
            model_version = NO_MODEL_VERSION
        else:
            estimate = self._prediction_model.predict(history, snapshot.quantity, horizon_days, moment.date())
            decision = decide_rescue(
                available_quantity=snapshot.quantity,
                expected_sales=estimate.expected_sales,
                current_discount_percent=snapshot.discount_percent,
                hours_left=hours_left,
            )
            inputs["horizon_days_used"] = horizon_days
            status = RescuePlanStatus.PENDING_APPROVAL
            action = decision.action
            reasons = decision.reasons
            expected_sales = estimate.expected_sales
            surplus_units = round(decision.surplus_units, 2)
            proposed_discount = decision.proposed_discount_percent
            model_version = estimate.model_version

        return RescuePlan(
            id=None,
            lot_id=snapshot.lot_id,
            shop_id=snapshot.shop_id,
            status=status,
            action=action,
            reasons=reasons,
            available_quantity=snapshot.quantity,
            expected_sales=expected_sales,
            surplus_units=surplus_units,
            proposed_discount_percent=proposed_discount,
            horizon_hours=round(hours_left, 2),
            data_points=len(history),
            rule_version=RESCUE_RULE_VERSION,
            model_version=model_version,
            inputs=inputs,
            created_by=actor.user_id,
            created_at=moment,
        )


class DecideRescuePlan:
    def __init__(
        self,
        lots: RescueLotGateway,
        plans: RescuePlanRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._lots = lots
        self._plans = plans
        self._unit_of_work = unit_of_work

    def execute(self, plan_id: int, actor: Actor, decision: Decision, now: datetime | None = None) -> RescuePlan:
        _require_shop_actor(actor)
        moment = now or datetime.now(timezone.utc)
        plan = self._plans.get(plan_id)
        snapshot = self._lots.get_snapshot(plan.lot_id) if plan else None
        if plan is None or snapshot is None or (snapshot.owner_id != actor.user_id and not actor.is_admin):
            raise RescuePlanNotFoundError("Rescue plan not found")

        target = RescuePlanStatus.APPROVED if decision == "approve" else RescuePlanStatus.REJECTED
        if plan.status is target:
            return plan
        decided = plan.approve(actor.user_id, moment) if decision == "approve" else plan.reject(actor.user_id, moment)
        if decision == "approve" and (
            snapshot.quantity != plan.available_quantity or not _is_rescuable(snapshot, moment)
        ):
            raise RescuePlanStaleError("Lot changed after this rescue plan was generated")

        if not self._plans.mark_decided(plan_id, target, actor.user_id, moment):
            return self._resolve_lost_race(plan_id, target)
        event_type = EVENT_APPROVED if decision == "approve" else EVENT_REJECTED
        self._plans.record_event(plan_id, event_type, actor.user_id, {"action": plan.action.value})
        if decision == "approve":
            self._execute_action(plan, actor)
        self._unit_of_work.commit()
        return decided

    def _execute_action(self, plan: RescuePlan, actor: Actor) -> None:
        if plan.action is not RescueAction.APPLY_DISCOUNT_RULE or plan.proposed_discount_percent is None:
            return
        assert plan.id is not None
        applied = self._lots.apply_discount_if_unchanged(
            plan.lot_id, plan.available_quantity, plan.proposed_discount_percent
        )
        if not applied:
            self._unit_of_work.rollback()
            raise RescuePlanStaleError("Lot changed while the rescue plan was being approved")
        self._plans.record_event(
            plan.id, EVENT_DISCOUNT_APPLIED, actor.user_id, {"discount_percent": plan.proposed_discount_percent}
        )

    def _resolve_lost_race(self, plan_id: int, target: RescuePlanStatus) -> RescuePlan:
        self._unit_of_work.rollback()
        current = self._plans.get(plan_id)
        if current is not None and current.status is target:
            return current
        raise InvalidRescuePlanTransitionError("Rescue plan was already decided differently")


class ListRescuePlans:
    def __init__(self, lots: RescueLotGateway, plans: RescuePlanRepository) -> None:
        self._lots = lots
        self._plans = plans

    def execute(self, shop_id: int, actor: Actor, status: RescuePlanStatus | None = None) -> list[RescuePlan]:
        _require_shop_actor(actor)
        owner_id = self._lots.get_shop_owner_id(shop_id)
        if owner_id is None or (owner_id != actor.user_id and not actor.is_admin):
            raise RescueLotNotFoundError("Shop not found")
        return self._plans.list_for_shop(shop_id, status)
