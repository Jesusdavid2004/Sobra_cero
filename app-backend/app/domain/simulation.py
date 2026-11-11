"""What-if comparison of three ways to handle a likely surplus.

Everything here is hypothetical. The only validated input is the plan's expected sales; the effect
of a discount on demand is a number the owner types in (`demand_uplift_percent`), because the
system has no trained price-response model. Callers must present results as scenarios, not
predictions.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.exceptions import SimulationInvalidError
from app.domain.rules import (
    MAX_DISCOUNT_PERCENT,
    MAX_SIMULATION_DEMAND_UPLIFT_PERCENT,
    RESCUE_DISCOUNT_STEP_PERCENT,
)

PERCENT = 100


class ScenarioKind(StrEnum):
    KEEP_OFFER = "keep_offer"
    APPLY_DISCOUNT = "apply_discount"
    SEPARATE_DONATION = "separate_donation"


@dataclass(frozen=True)
class Scenario:
    kind: ScenarioKind
    discount_percent: int
    donated_units: int
    expected_sales: float
    surplus_units: float
    estimated_revenue_cents: int


def _price_cents(original_price_cents: int, discount_percent: int) -> int:
    return original_price_cents * (PERCENT - discount_percent) // PERCENT


def _scenario(
    kind: ScenarioKind,
    *,
    stock: int,
    expected_sales: float,
    discount_percent: int,
    donated_units: int,
    original_price_cents: int,
) -> Scenario:
    sales = min(expected_sales, stock)
    return Scenario(
        kind=kind,
        discount_percent=discount_percent,
        donated_units=donated_units,
        expected_sales=sales,
        surplus_units=stock - sales,
        estimated_revenue_cents=round(sales * _price_cents(original_price_cents, discount_percent)),
    )


def simulate_scenarios(
    *,
    available_quantity: int,
    expected_sales: float,
    current_discount_percent: int,
    original_price_cents: int,
    demand_uplift_percent: int,
    donation_units: int,
) -> tuple[Scenario, ...]:
    if not 0 <= demand_uplift_percent <= MAX_SIMULATION_DEMAND_UPLIFT_PERCENT:
        raise SimulationInvalidError("Demand uplift is outside the allowed range")
    if not 0 <= donation_units <= available_quantity:
        raise SimulationInvalidError("Donation units must be between zero and the available quantity")

    discounted = min(MAX_DISCOUNT_PERCENT, current_discount_percent + RESCUE_DISCOUNT_STEP_PERCENT)
    return (
        _scenario(
            ScenarioKind.KEEP_OFFER,
            stock=available_quantity,
            expected_sales=expected_sales,
            discount_percent=current_discount_percent,
            donated_units=0,
            original_price_cents=original_price_cents,
        ),
        _scenario(
            ScenarioKind.APPLY_DISCOUNT,
            stock=available_quantity,
            expected_sales=expected_sales * (1 + demand_uplift_percent / PERCENT),
            discount_percent=discounted,
            donated_units=0,
            original_price_cents=original_price_cents,
        ),
        _scenario(
            ScenarioKind.SEPARATE_DONATION,
            stock=available_quantity - donation_units,
            expected_sales=expected_sales,
            discount_percent=current_discount_percent,
            donated_units=donation_units,
            original_price_cents=original_price_cents,
        ),
    )
