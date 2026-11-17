import pytest
from fastapi.testclient import TestClient
from test_rescue_plan import (
    ADMIN,
    CUSTOMER,
    OTHER_BUSINESS,
    OWNER,
    FakeLots,
    FakePlans,
    auth_headers,
    make_plan,
    make_snapshot,
    reset_db,
    seed_lot,
)

from app import main
from app.application.use_cases.simulate_rescue_plan import SimulateRescuePlan
from app.domain.exceptions import (
    RescuePermissionError,
    RescuePlanNotFoundError,
    SimulationInvalidError,
    SimulationUnavailableError,
)
from app.domain.rescue import RescuePlanStatus
from app.domain.simulation import ScenarioKind, simulate_scenarios

PRICE = 1000


def simulate(**overrides):
    values = dict(
        available_quantity=20,
        expected_sales=6.0,
        current_discount_percent=20,
        original_price_cents=PRICE,
        demand_uplift_percent=50,
        donation_units=8,
    )
    return {scenario.kind: scenario for scenario in simulate_scenarios(**{**values, **overrides})}


# ---- domain ----


def test_keeping_the_offer_sells_what_is_expected_at_the_current_price():
    keep = simulate()[ScenarioKind.KEEP_OFFER]

    assert (keep.expected_sales, keep.surplus_units, keep.discount_percent) == (6.0, 14.0, 20)
    assert keep.estimated_revenue_cents == 6 * 800


def test_a_discount_step_sells_more_only_by_the_uplift_the_owner_assumes():
    discount = simulate(demand_uplift_percent=50)[ScenarioKind.APPLY_DISCOUNT]

    assert discount.discount_percent == 30
    assert discount.expected_sales == 9.0
    assert discount.surplus_units == 11.0
    assert discount.estimated_revenue_cents == 9 * 700


def test_with_no_assumed_uplift_a_discount_only_lowers_revenue():
    scenarios = simulate(demand_uplift_percent=0)

    assert scenarios[ScenarioKind.APPLY_DISCOUNT].surplus_units == scenarios[ScenarioKind.KEEP_OFFER].surplus_units
    assert (
        scenarios[ScenarioKind.APPLY_DISCOUNT].estimated_revenue_cents
        < scenarios[ScenarioKind.KEEP_OFFER].estimated_revenue_cents
    )


def test_separating_units_for_donation_removes_them_from_the_sellable_stock():
    donation = simulate(donation_units=8)[ScenarioKind.SEPARATE_DONATION]

    assert donation.donated_units == 8
    assert donation.surplus_units == 6.0
    assert donation.estimated_revenue_cents == 6 * 800


def test_sales_never_exceed_the_stock():
    keep = simulate(expected_sales=30.0)[ScenarioKind.KEEP_OFFER]

    assert (keep.expected_sales, keep.surplus_units) == (20, 0)


def test_the_discount_step_stops_at_the_maximum_discount():
    assert simulate(current_discount_percent=85)[ScenarioKind.APPLY_DISCOUNT].discount_percent == 90


@pytest.mark.parametrize(
    "overrides",
    [{"demand_uplift_percent": 301}, {"demand_uplift_percent": -1}, {"donation_units": 21}, {"donation_units": -1}],
)
def test_parameters_outside_the_allowed_range_are_rejected(overrides):
    with pytest.raises(SimulationInvalidError):
        simulate(**overrides)


# ---- use case ----


def build_use_case(plan=None, snapshot=None):
    plans = FakePlans()
    saved = plans.add(plan or make_plan())
    lots = FakeLots(snapshot or make_snapshot(original_price_cents=PRICE))
    return SimulateRescuePlan(lots, plans), saved


def test_the_donation_defaults_to_the_whole_units_of_estimated_surplus():
    use_case, plan = build_use_case(make_plan(available_quantity=20, expected_sales=6.0, surplus_units=14.0))

    result = use_case.execute(plan.id, OWNER, 0, None)

    assert result.donation_units == 14
    assert not result.stale


def test_a_plan_without_numbers_cannot_be_simulated():
    use_case, plan = build_use_case(
        make_plan(status=RescuePlanStatus.NOT_ACTIONABLE, expected_sales=None, surplus_units=None)
    )

    with pytest.raises(SimulationUnavailableError):
        use_case.execute(plan.id, OWNER, 0, None)


def test_the_result_is_marked_stale_when_the_stock_changed_after_the_plan():
    use_case, plan = build_use_case(
        make_plan(available_quantity=20), make_snapshot(quantity=15, original_price_cents=PRICE)
    )

    assert use_case.execute(plan.id, OWNER, 0, None).stale


def test_other_shops_are_hidden_customers_blocked_and_admins_allowed():
    use_case, plan = build_use_case()

    with pytest.raises(RescuePlanNotFoundError):
        use_case.execute(plan.id, OTHER_BUSINESS, 0, None)
    with pytest.raises(RescuePlanNotFoundError):
        use_case.execute(999, OWNER, 0, None)
    with pytest.raises(RescuePermissionError):
        use_case.execute(plan.id, CUSTOMER, 0, None)
    assert use_case.execute(plan.id, ADMIN, 0, None).scenarios


# ---- HTTP, real database ----


def test_http_simulation_returns_three_scenarios_labelled_hypothetical():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=30)
    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=owner).json()

    response = client.post(
        f"/api/v1/rescue-plans/{plan['id']}/simulation", json={"demand_uplift_percent": 40}, headers=owner
    )

    body = response.json()
    assert response.status_code == 200
    assert body["hypothetical"] is True and body["stale"] is False
    assert [scenario["kind"] for scenario in body["scenarios"]] == ["keep_offer", "apply_discount", "separate_donation"]
    assert body["scenarios"][1]["discount_percent"] == 30


def test_http_simulation_errors_use_the_error_contract():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    other = auth_headers(client, "other@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=30)
    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=owner).json()
    url = f"/api/v1/rescue-plans/{plan['id']}/simulation"

    too_many = client.post(url, json={"donation_units": 999}, headers=owner)
    out_of_range = client.post(url, json={"demand_uplift_percent": 1000}, headers=owner)
    hidden = client.post(url, json={}, headers=other)

    assert too_many.status_code == 422
    assert too_many.json() == {"code": "simulation_invalid", "message_key": "errors.simulation_invalid"}
    assert out_of_range.status_code == 422
    assert hidden.status_code == 404


def test_http_a_plan_without_history_cannot_be_simulated():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=5)
    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=owner).json()

    response = client.post(f"/api/v1/rescue-plans/{plan['id']}/simulation", json={}, headers=owner)

    assert response.status_code == 409
    assert response.json()["code"] == "simulation_unavailable"
