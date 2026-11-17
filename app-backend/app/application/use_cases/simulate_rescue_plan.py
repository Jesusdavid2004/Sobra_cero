from dataclasses import dataclass

from app.application.dto import Actor
from app.application.ports import RescueLotGateway, RescuePlanRepository
from app.domain.exceptions import (
    RescueLotNotFoundError,
    RescuePermissionError,
    RescuePlanNotFoundError,
    SimulationUnavailableError,
)
from app.domain.simulation import Scenario, simulate_scenarios


@dataclass(frozen=True)
class SimulationResult:
    scenarios: tuple[Scenario, ...]
    demand_uplift_percent: int
    donation_units: int
    stale: bool


class SimulateRescuePlan:
    """Compare keeping, discounting and donating, from the numbers of an existing plan."""

    def __init__(self, lots: RescueLotGateway, plans: RescuePlanRepository) -> None:
        self._lots = lots
        self._plans = plans

    def execute(
        self, plan_id: int, actor: Actor, demand_uplift_percent: int, donation_units: int | None
    ) -> SimulationResult:
        if not actor.can_manage_shops:
            raise RescuePermissionError("Business account required")
        plan = self._plans.get(plan_id)
        owner_id = self._lots.get_shop_owner_id(plan.shop_id) if plan is not None else None
        if plan is None or (owner_id != actor.user_id and not actor.is_admin):
            raise RescuePlanNotFoundError("Rescue plan not found")
        snapshot = self._lots.get_snapshot(plan.lot_id)
        if snapshot is None:
            raise RescueLotNotFoundError("Lot not found")
        if plan.expected_sales is None or plan.surplus_units is None:
            raise SimulationUnavailableError("This plan has no numbers to simulate")
        units = int(plan.surplus_units) if donation_units is None else donation_units
        scenarios = simulate_scenarios(
            available_quantity=plan.available_quantity,
            expected_sales=plan.expected_sales,
            current_discount_percent=snapshot.discount_percent,
            original_price_cents=snapshot.original_price_cents,
            demand_uplift_percent=demand_uplift_percent,
            donation_units=units,
        )
        return SimulationResult(
            scenarios=scenarios,
            demand_uplift_percent=demand_uplift_percent,
            donation_units=units,
            stale=snapshot.quantity != plan.available_quantity,
        )
