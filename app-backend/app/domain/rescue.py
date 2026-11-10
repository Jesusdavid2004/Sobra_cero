"""Rescue plan rules and lifecycle. Pure domain code: no I/O and no AI."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from app.domain.exceptions import InvalidRescuePlanTransitionError
from app.domain.rules import (
    MAX_DISCOUNT_PERCENT,
    RESCUE_DISCOUNT_STEP_PERCENT,
    RESCUE_DISCOUNT_SURPLUS_RATIO,
    RESCUE_DONATION_SURPLUS_RATIO,
    RESCUE_SHORT_WINDOW_HOURS,
)


class RescueAction(StrEnum):
    KEEP_OFFER = "keep_offer"
    APPLY_DISCOUNT_RULE = "apply_discount_rule"
    PREPARE_DONATION_OFFER = "prepare_donation_offer"
    INSUFFICIENT_HISTORY = "insufficient_history"


class RescuePlanStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    NOT_ACTIONABLE = "not_actionable"


class RescueReason(StrEnum):
    STOCK_EXCEEDS_EXPECTED_SALES = "stock_exceeds_expected_sales"
    SURPLUS_ABOVE_DONATION_THRESHOLD = "surplus_above_donation_threshold"
    SURPLUS_ABOVE_DISCOUNT_THRESHOLD = "surplus_above_discount_threshold"
    STOCK_COVERED_BY_EXPECTED_SALES = "stock_covered_by_expected_sales"
    DISCOUNT_ALREADY_AT_LIMIT = "discount_already_at_limit"
    PICKUP_WINDOW_SHORT = "pickup_window_short"
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass(frozen=True)
class RescueDecision:
    action: RescueAction
    surplus_units: float
    proposed_discount_percent: int | None
    reasons: tuple[RescueReason, ...]


def decide_rescue(
    *,
    available_quantity: int,
    expected_sales: float,
    current_discount_percent: int,
    hours_left: float,
) -> RescueDecision:
    """Heuristic ladder over the estimated surplus. It is not a trained price-response model."""
    surplus = max(0.0, available_quantity - expected_sales)
    ratio = surplus / available_quantity
    window_reasons = (RescueReason.PICKUP_WINDOW_SHORT,) if hours_left < RESCUE_SHORT_WINDOW_HOURS else ()

    if ratio >= RESCUE_DONATION_SURPLUS_RATIO:
        return RescueDecision(
            RescueAction.PREPARE_DONATION_OFFER,
            surplus,
            None,
            (
                RescueReason.STOCK_EXCEEDS_EXPECTED_SALES,
                RescueReason.SURPLUS_ABOVE_DONATION_THRESHOLD,
                *window_reasons,
            ),
        )
    if ratio >= RESCUE_DISCOUNT_SURPLUS_RATIO:
        proposed = min(MAX_DISCOUNT_PERCENT, current_discount_percent + RESCUE_DISCOUNT_STEP_PERCENT)
        if proposed == current_discount_percent:
            return RescueDecision(
                RescueAction.KEEP_OFFER,
                surplus,
                None,
                (
                    RescueReason.STOCK_EXCEEDS_EXPECTED_SALES,
                    RescueReason.DISCOUNT_ALREADY_AT_LIMIT,
                    *window_reasons,
                ),
            )
        return RescueDecision(
            RescueAction.APPLY_DISCOUNT_RULE,
            surplus,
            proposed,
            (
                RescueReason.STOCK_EXCEEDS_EXPECTED_SALES,
                RescueReason.SURPLUS_ABOVE_DISCOUNT_THRESHOLD,
                *window_reasons,
            ),
        )
    return RescueDecision(
        RescueAction.KEEP_OFFER,
        surplus,
        None,
        (RescueReason.STOCK_COVERED_BY_EXPECTED_SALES, *window_reasons),
    )


@dataclass(frozen=True)
class RescuePlan:
    id: int | None
    lot_id: int
    shop_id: int
    status: RescuePlanStatus
    action: RescueAction
    reasons: tuple[RescueReason, ...]
    available_quantity: int
    expected_sales: float | None
    surplus_units: float | None
    proposed_discount_percent: int | None
    horizon_hours: float
    data_points: int
    rule_version: str
    model_version: str
    inputs: Mapping[str, object]
    created_by: int
    created_at: datetime
    decided_by: int | None = None
    decided_at: datetime | None = None

    def approve(self, actor_id: int, now: datetime) -> "RescuePlan":
        return self._decide(RescuePlanStatus.APPROVED, actor_id, now)

    def reject(self, actor_id: int, now: datetime) -> "RescuePlan":
        return self._decide(RescuePlanStatus.REJECTED, actor_id, now)

    def _decide(self, status: RescuePlanStatus, actor_id: int, now: datetime) -> "RescuePlan":
        if self.status is not RescuePlanStatus.PENDING_APPROVAL:
            raise InvalidRescuePlanTransitionError(f"Rescue plan cannot move from {self.status} to {status}")
        return replace(self, status=status, decided_by=actor_id, decided_at=now)
