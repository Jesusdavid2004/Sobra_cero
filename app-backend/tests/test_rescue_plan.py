from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Sequence

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.application.dto import (
    Actor,
    DailySales,
    LotAnalysis,
    LotAnalysisInput,
    LotSnapshot,
)
from app.application.use_cases.rescue_plan import (
    DecideRescuePlan,
    GenerateRescuePlan,
    ListRescuePlans,
)
from app.db import Base, SessionLocal, engine
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
from app.models import Lot, RescuePlanEventRecord

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
OWNER = Actor(user_id=1, role="business", is_admin=False)
OTHER_BUSINESS = Actor(user_id=2, role="business", is_admin=False)
CUSTOMER = Actor(user_id=3, role="customer", is_admin=False)
ADMIN = Actor(user_id=9, role="customer", is_admin=True)


# ---- domain rules ----


@pytest.mark.parametrize(
    ("available", "expected", "discount", "action", "proposed"),
    [
        (100, 50, 20, RescueAction.PREPARE_DONATION_OFFER, None),
        (100, 51, 20, RescueAction.APPLY_DISCOUNT_RULE, 30),
        (100, 80, 20, RescueAction.APPLY_DISCOUNT_RULE, 30),
        (100, 81, 20, RescueAction.KEEP_OFFER, None),
        (100, 500, 20, RescueAction.KEEP_OFFER, None),
        (100, 70, 85, RescueAction.APPLY_DISCOUNT_RULE, 90),
        (100, 70, 90, RescueAction.KEEP_OFFER, None),
    ],
)
def test_decide_rescue_follows_the_surplus_ladder(available, expected, discount, action, proposed):
    decision = decide_rescue(
        available_quantity=available,
        expected_sales=expected,
        current_discount_percent=discount,
        hours_left=48,
    )

    assert decision.action is action
    assert decision.proposed_discount_percent == proposed


def test_decide_rescue_explains_discount_limit_and_short_window():
    decision = decide_rescue(available_quantity=100, expected_sales=70, current_discount_percent=90, hours_left=5)

    assert RescueReason.DISCOUNT_ALREADY_AT_LIMIT in decision.reasons
    assert RescueReason.PICKUP_WINDOW_SHORT in decision.reasons


def test_decide_rescue_reports_zero_surplus_when_sales_cover_stock():
    decision = decide_rescue(available_quantity=10, expected_sales=25, current_discount_percent=0, hours_left=48)

    assert decision.surplus_units == 0
    assert decision.reasons == (RescueReason.STOCK_COVERED_BY_EXPECTED_SALES,)


def test_plan_status_only_moves_from_pending():
    plan = make_plan()
    approved = plan.approve(1, NOW)

    assert approved.status is RescuePlanStatus.APPROVED
    with pytest.raises(InvalidRescuePlanTransitionError):
        approved.reject(1, NOW)
    with pytest.raises(InvalidRescuePlanTransitionError):
        make_plan(status=RescuePlanStatus.NOT_ACTIONABLE).approve(1, NOW)


# ---- fakes ----


def make_plan(**overrides) -> RescuePlan:
    values = dict(
        id=1,
        lot_id=10,
        shop_id=5,
        status=RescuePlanStatus.PENDING_APPROVAL,
        action=RescueAction.APPLY_DISCOUNT_RULE,
        reasons=(RescueReason.STOCK_EXCEEDS_EXPECTED_SALES,),
        available_quantity=20,
        expected_sales=6.0,
        surplus_units=14.0,
        proposed_discount_percent=30,
        horizon_hours=48.0,
        data_points=30,
        rule_version="rescue-rules-v1",
        model_version="baseline-weighted-moving-average",
        inputs={},
        created_by=1,
        created_at=NOW,
    )
    values.update(overrides)
    return RescuePlan(**values)


class FakeLots:
    def __init__(self, snapshot: LotSnapshot | None) -> None:
        self.snapshot = snapshot
        self.discount_calls = 0

    def get_snapshot(self, lot_id: int) -> LotSnapshot | None:
        return self.snapshot

    def get_shop_owner_id(self, shop_id: int) -> int | None:
        return self.snapshot.owner_id if self.snapshot else None

    def apply_discount_if_unchanged(self, lot_id: int, expected_quantity: int, discount_percent: int) -> bool:
        if self.snapshot is None or self.snapshot.quantity != expected_quantity:
            return False
        self.discount_calls += 1
        self.snapshot = replace(self.snapshot, discount_percent=discount_percent)
        return True


class FakePlans:
    def __init__(self) -> None:
        self.plans: dict[int, RescuePlan] = {}
        self.events: list[tuple[int, str]] = []

    def add(self, plan: RescuePlan) -> RescuePlan:
        saved = replace(plan, id=len(self.plans) + 1)
        self.plans[saved.id] = saved
        return saved

    def get(self, plan_id: int) -> RescuePlan | None:
        return self.plans.get(plan_id)

    def list_for_shop(self, shop_id: int, status: RescuePlanStatus | None) -> list[RescuePlan]:
        return [p for p in self.plans.values() if p.shop_id == shop_id and (status is None or p.status is status)]

    def supersede_pending_for_lot(self, lot_id: int) -> list[int]:
        ids = [
            p.id for p in self.plans.values() if p.lot_id == lot_id and p.status is RescuePlanStatus.PENDING_APPROVAL
        ]
        for plan_id in ids:
            self.plans[plan_id] = replace(self.plans[plan_id], status=RescuePlanStatus.SUPERSEDED)
        return ids

    def mark_decided(self, plan_id: int, status: RescuePlanStatus, actor_id: int, now: datetime) -> bool:
        plan = self.plans[plan_id]
        if plan.status is not RescuePlanStatus.PENDING_APPROVAL:
            return False
        self.plans[plan_id] = replace(plan, status=status, decided_by=actor_id, decided_at=now)
        return True

    def record_event(self, plan_id: int, event_type: str, actor_id: int | None, payload: Mapping[str, object]) -> None:
        self.events.append((plan_id, event_type))


class FakeHistory:
    def __init__(self, days: int) -> None:
        self.days = days

    def list_for_product(self, product_id: int, since: date) -> list[DailySales]:
        return [DailySales(NOW.date() - timedelta(days=i), 3, False) for i in range(self.days)]

    def upsert_many(self, product_id: int, entries: Sequence[DailySales]) -> tuple[int, int]:
        raise NotImplementedError

    def save_prediction(self, **kwargs: object) -> None:
        raise NotImplementedError


class FakeAnalyzer:
    def __init__(self, expected_sales: float) -> None:
        self.expected_sales = expected_sales
        self.calls: list[LotAnalysisInput] = []

    def analyze_lot(self, request_id: str, lot: LotAnalysisInput) -> LotAnalysis:
        self.calls.append(lot)
        decision = decide_rescue(
            available_quantity=lot.available_quantity,
            expected_sales=self.expected_sales,
            current_discount_percent=lot.current_discount_percent,
            hours_left=lot.horizon_hours,
        )
        return LotAnalysis(
            lot_ref=lot.lot_ref,
            expected_sales=self.expected_sales,
            surplus_units=decision.surplus_units,
            action=decision.action,
            proposed_discount_percent=decision.proposed_discount_percent,
            reasons=decision.reasons,
            model_version="fixed-model-v1",
            rule_version="rescue-rules-v1",
            horizon_days_used=1,
            source="local",
        )

    def analyze_shop(self, request_id: str, lots: Sequence[LotAnalysisInput]) -> list[LotAnalysis]:
        return [self.analyze_lot(request_id, lot) for lot in lots]


class FakeModels:
    def get_active_model(self) -> None:
        return None


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def make_snapshot(**overrides) -> LotSnapshot:
    values = dict(
        lot_id=10,
        shop_id=5,
        owner_id=1,
        product_id=7,
        quantity=20,
        discount_percent=20,
        status="active",
        expires_at=NOW + timedelta(hours=48),
        pickup_ends_at=None,
    )
    values.update(overrides)
    return LotSnapshot(**values)


def build_generate(snapshot=None, history_days=30, expected_sales=6.0):
    lots = FakeLots(snapshot if snapshot is not None else make_snapshot())
    plans, uow, analyzer = FakePlans(), FakeUnitOfWork(), FakeAnalyzer(expected_sales)
    return (
        GenerateRescuePlan(lots, plans, FakeHistory(history_days), FakeModels(), analyzer, uow),
        lots,
        plans,
        uow,
        analyzer,
    )


# ---- generate use case ----


def test_generate_creates_pending_plan_with_reasons_and_audit_event():
    use_case, _lots, plans, uow, _model = build_generate()

    plan = use_case.execute(10, OWNER, NOW)

    assert plan.status is RescuePlanStatus.PENDING_APPROVAL
    assert plan.action is RescueAction.PREPARE_DONATION_OFFER
    assert plan.surplus_units == 14
    assert plan.model_version == "fixed-model-v1"
    assert plan.inputs["quantity"] == 20
    assert (plan.id, "generated") in plans.events
    assert uow.commits == 1


def test_generate_without_enough_history_is_not_actionable_and_has_no_numbers():
    use_case, _lots, _plans, _uow, analyzer = build_generate(history_days=13)

    plan = use_case.execute(10, OWNER, NOW)

    assert plan.status is RescuePlanStatus.NOT_ACTIONABLE
    assert plan.action is RescueAction.INSUFFICIENT_HISTORY
    assert plan.expected_sales is None and plan.surplus_units is None
    assert analyzer.calls == []


def test_generate_uses_the_earlier_of_expiry_and_pickup_deadline():
    snapshot = make_snapshot(expires_at=NOW + timedelta(hours=72), pickup_ends_at=NOW + timedelta(hours=10))
    use_case, _lots, _plans, _uow, analyzer = build_generate(snapshot)

    plan = use_case.execute(10, OWNER, NOW)

    assert plan.horizon_hours == 10
    assert analyzer.calls[0].horizon_hours == 10
    assert RescueReason.PICKUP_WINDOW_SHORT in plan.reasons


def test_generate_supersedes_the_previous_pending_plan():
    use_case, _lots, plans, _uow, _model = build_generate()

    first = use_case.execute(10, OWNER, NOW)
    second = use_case.execute(10, OWNER, NOW)

    assert plans.plans[first.id].status is RescuePlanStatus.SUPERSEDED
    assert plans.plans[second.id].status is RescuePlanStatus.PENDING_APPROVAL
    assert (first.id, "superseded") in plans.events


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "sold_out"},
        {"quantity": 0},
        {"expires_at": NOW - timedelta(hours=1)},
        {"pickup_ends_at": NOW - timedelta(minutes=1)},
    ],
)
def test_generate_rejects_lots_that_cannot_be_rescued(overrides):
    use_case, *_ = build_generate(make_snapshot(**overrides))

    with pytest.raises(LotNotRescuableError):
        use_case.execute(10, OWNER, NOW)


def test_generate_hides_other_shops_lots_and_blocks_customers():
    use_case, *_ = build_generate()

    with pytest.raises(RescueLotNotFoundError):
        use_case.execute(10, OTHER_BUSINESS, NOW)
    with pytest.raises(RescuePermissionError):
        use_case.execute(10, CUSTOMER, NOW)
    assert use_case.execute(10, ADMIN, NOW).status is RescuePlanStatus.PENDING_APPROVAL


# ---- decide use case ----


def build_decide(plan: RescuePlan | None = None, snapshot: LotSnapshot | None = None):
    lots = FakeLots(snapshot or make_snapshot())
    plans, uow = FakePlans(), FakeUnitOfWork()
    saved = plans.add(plan or make_plan())
    return DecideRescuePlan(lots, plans, uow), lots, plans, uow, saved


def test_approving_a_discount_plan_applies_it_once_and_is_idempotent():
    use_case, lots, plans, uow, plan = build_decide()

    first = use_case.execute(plan.id, OWNER, "approve", NOW)
    second = use_case.execute(plan.id, OWNER, "approve", NOW)

    assert first.status is second.status is RescuePlanStatus.APPROVED
    assert lots.discount_calls == 1
    assert lots.snapshot.discount_percent == 30
    assert [e for e in plans.events if e[1] == "approved"] == [(plan.id, "approved")]
    assert (plan.id, "discount_applied") in plans.events
    assert uow.commits == 1


def test_approving_a_donation_plan_does_not_touch_stock_or_price():
    donation = make_plan(action=RescueAction.PREPARE_DONATION_OFFER, proposed_discount_percent=None)
    use_case, lots, _plans, _uow, plan = build_decide(donation)

    use_case.execute(plan.id, OWNER, "approve", NOW)

    assert lots.discount_calls == 0
    assert lots.snapshot.quantity == 20


def test_rejecting_records_the_decision_without_changing_the_lot():
    use_case, lots, plans, _uow, plan = build_decide()

    result = use_case.execute(plan.id, OWNER, "reject", NOW)

    assert result.status is RescuePlanStatus.REJECTED
    assert lots.discount_calls == 0
    assert (plan.id, "rejected") in plans.events
    with pytest.raises(InvalidRescuePlanTransitionError):
        use_case.execute(plan.id, OWNER, "approve", NOW)


def test_approving_after_stock_changed_is_rejected_as_stale():
    use_case, lots, _plans, _uow, plan = build_decide(snapshot=make_snapshot(quantity=12))

    with pytest.raises(RescuePlanStaleError):
        use_case.execute(plan.id, OWNER, "approve", NOW)
    assert lots.discount_calls == 0


def test_approving_a_not_actionable_plan_is_invalid():
    use_case, _lots, _plans, _uow, plan = build_decide(make_plan(status=RescuePlanStatus.NOT_ACTIONABLE))

    with pytest.raises(InvalidRescuePlanTransitionError):
        use_case.execute(plan.id, OWNER, "approve", NOW)


def test_decide_hides_plans_of_other_shops_and_blocks_customers():
    use_case, _lots, _plans, _uow, plan = build_decide()

    with pytest.raises(RescuePlanNotFoundError):
        use_case.execute(plan.id, OTHER_BUSINESS, "approve", NOW)
    with pytest.raises(RescuePlanNotFoundError):
        use_case.execute(999, OWNER, "approve", NOW)
    with pytest.raises(RescuePermissionError):
        use_case.execute(plan.id, CUSTOMER, "approve", NOW)


def test_list_is_scoped_to_the_shop_owner():
    lots = FakeLots(make_snapshot())
    plans = FakePlans()
    plans.add(make_plan())
    use_case = ListRescuePlans(lots, plans)

    assert len(use_case.execute(5, OWNER)) == 1
    with pytest.raises(RescueLotNotFoundError):
        use_case.execute(5, OTHER_BUSINESS)


# ---- HTTP integration (real routes, SQLite) ----


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def auth_headers(client: TestClient, email: str, role: str = "business") -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "password123", "role": role})
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def seed_lot(client: TestClient, headers: dict[str, str], history_days: int, **lot_fields) -> tuple[int, int, int]:
    shop_id = client.post(
        "/api/v1/shops",
        json={"name": "Bakery", "description": "", "latitude": 4.7, "longitude": -74.0},
        headers=headers,
    ).json()["id"]
    product_id = client.post(
        f"/api/v1/shops/{shop_id}/products", json={"name": "Bread", "description": ""}, headers=headers
    ).json()["id"]
    if history_days:
        today = datetime.now(timezone.utc).date()
        entries = [
            {"sales_date": (today - timedelta(days=i + 1)).isoformat(), "units_sold": 3, "had_promotion": False}
            for i in range(history_days)
        ]
        response = client.post(
            f"/api/v1/products/{product_id}/sales-history", json={"entries": entries}, headers=headers
        )
        assert response.status_code == 201
    payload = {
        "shop_id": shop_id,
        "product_id": product_id,
        "title": "Bread bag",
        "quantity": 20,
        "original_price_cents": 1000,
        "discount_percent": 20,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        **lot_fields,
    }
    response = client.post("/api/v1/lots", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return shop_id, product_id, response.json()["id"]


def test_http_rescue_flow_generates_approves_and_audits():
    reset_db()
    client = TestClient(main.app)
    headers = auth_headers(client, "owner@example.com")
    shop_id, _product_id, lot_id = seed_lot(client, headers, history_days=30)

    created = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=headers)
    assert created.status_code == 201
    plan = created.json()
    assert plan["status"] == "pending_approval"
    assert plan["action"] == "prepare_donation_offer"
    assert plan["reasons"][0] == "stock_exceeds_expected_sales"

    listed = client.get(f"/api/v1/shops/{shop_id}/rescue-plans", headers=headers)
    assert [item["id"] for item in listed.json()] == [plan["id"]]

    approved = client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=headers)
    again = client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=headers)
    assert approved.status_code == again.status_code == 200
    assert approved.json()["status"] == again.json()["status"] == "approved"

    with SessionLocal() as session:
        event_types = [e.event_type for e in session.query(RescuePlanEventRecord).order_by(RescuePlanEventRecord.id)]
    assert event_types == ["generated", "approved"]


def test_http_discount_approval_updates_the_lot_discount():
    reset_db()
    client = TestClient(main.app)
    headers = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, headers, history_days=30, quantity=8)

    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=headers).json()
    assert plan["action"] == "apply_discount_rule"
    assert plan["proposed_discount_percent"] == 30

    assert client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=headers).status_code == 200
    assert client.get(f"/api/v1/lots/{lot_id}").json()["discount_percent"] == 30


def test_http_insufficient_history_returns_a_not_actionable_plan():
    reset_db()
    client = TestClient(main.app)
    headers = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, headers, history_days=5)

    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=headers).json()

    assert plan["status"] == "not_actionable"
    assert plan["action"] == "insufficient_history"
    assert plan["expected_sales"] is None
    response = client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=headers)
    assert response.status_code == 409
    assert response.json() == {
        "code": "rescue_plan_invalid_transition",
        "message_key": "errors.rescue_plan_invalid_transition",
    }


def test_http_other_business_and_customers_cannot_use_a_plan():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    other = auth_headers(client, "other@example.com")
    customer = auth_headers(client, "customer@example.com", role="customer")
    shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=30)
    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=owner).json()

    assert client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=other).status_code == 404
    assert client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=other).status_code == 404
    assert client.get(f"/api/v1/shops/{shop_id}/rescue-plans", headers=other).status_code == 404
    assert client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=customer).status_code == 403
    assert client.post(f"/api/v1/lots/{lot_id}/rescue-plan").status_code == 401


def test_http_stale_plan_cannot_be_approved_after_a_reservation():
    reset_db()
    client = TestClient(main.app)
    owner = auth_headers(client, "owner@example.com")
    customer = auth_headers(client, "customer@example.com", role="customer")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=30, quantity=8)
    plan = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers=owner).json()

    assert client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": 2}, headers=customer).status_code == 201

    response = client.post(f"/api/v1/rescue-plans/{plan['id']}/approve", headers=owner)
    assert response.status_code == 409
    assert response.json()["code"] == "rescue_plan_stale"
    with SessionLocal() as session:
        assert session.get(Lot, lot_id).discount_percent == 20


def test_http_lot_rejects_pickup_deadline_after_expiry():
    reset_db()
    client = TestClient(main.app)
    headers = auth_headers(client, "owner@example.com")
    shop_id = client.post(
        "/api/v1/shops", json={"name": "Bakery", "latitude": 4.7, "longitude": -74.0}, headers=headers
    ).json()["id"]
    product_id = client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Bread"}, headers=headers).json()["id"]
    expires = datetime.now(timezone.utc) + timedelta(days=1)

    response = client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop_id,
            "product_id": product_id,
            "title": "Bread bag",
            "quantity": 5,
            "original_price_cents": 1000,
            "discount_percent": 20,
            "expires_at": expires.isoformat(),
            "pickup_ends_at": (expires + timedelta(hours=1)).isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 422
