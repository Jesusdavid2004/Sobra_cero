from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.application.dto import DailySales
from app.application.use_cases.calculate_waste_risk import CalculateWasteRiskUseCase
from app.db import Base, engine
from app.domain.exceptions import (
    InsufficientSalesHistoryError,
    RiskScoreValidationError,
)
from app.domain.value_objects import RiskScore
from app.infrastructure.prediction.weighted_moving_average import (
    WeightedMovingAveragePredictionModel,
)


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_business(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_product_and_lot(client: TestClient, headers: dict[str, str]) -> tuple[int, int, int]:
    shop_response = client.post(
        "/api/v1/shops",
        json={"name": "Market", "description": "", "latitude": 4.7, "longitude": -74.0},
        headers=headers,
    )
    assert shop_response.status_code == 201
    shop_id = shop_response.json()["id"]
    product_response = client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Fresh bread", "description": ""},
        headers=headers,
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]
    lot_response = client.post(
        "/api/v1/lots",
        json={
            "shop_id": shop_id,
            "product_id": product_id,
            "title": "Bread rescue bag",
            "description": "Fresh bread for today",
            "quantity": 50,
            "original_price_cents": 1000,
            "discount_percent": 20,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
        headers=headers,
    )
    assert lot_response.status_code == 201
    return shop_id, product_id, lot_response.json()["id"]


def test_risk_score_rejects_values_outside_range():
    with pytest.raises(RiskScoreValidationError):
        RiskScore(101)


def test_weighted_moving_average_accounts_for_weekdays_and_risk():
    today = date(2026, 10, 6)
    history = [
        DailySales(sales_date=today - timedelta(days=offset), units_sold=3, had_promotion=False)
        for offset in range(30, 0, -1)
    ]

    result = WeightedMovingAveragePredictionModel().predict(history, 20, 2, today)

    assert result.average_daily_sales == 3
    assert result.expected_sales == 6
    assert result.units_at_risk == 14
    assert result.risk_score == RiskScore(70)


def test_calculate_use_case_requires_history_before_model_call():
    class EmptyRepository:
        def list_for_product(self, product_id, since):
            return []

        def save_prediction(self, **kwargs):
            raise AssertionError("A prediction must not be persisted without enough history")

    class UnusedModel:
        def predict(self, *args):
            raise AssertionError("A model must not run without enough history")

    class UnusedAI:
        def complete(self, prompt):
            raise AssertionError("AI must not run without enough history")

    use_case = CalculateWasteRiskUseCase(EmptyRepository(), UnusedModel(), UnusedAI())
    with pytest.raises(InsufficientSalesHistoryError):
        use_case.execute(
            product_id=1,
            product_name="Bread",
            business_type="restaurant",
            lot_id=1,
            current_stock=10,
            expires_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
            language="en",
            today=date(2026, 10, 6),
        )


def test_business_can_generate_sample_data_and_calculate_spanish_risk():
    reset_db()
    client = TestClient(main.app)
    headers = create_business(client, "risk@example.com")
    shop_id, product_id, lot_id = create_product_and_lot(client, headers)

    generated = client.post(f"/api/v1/shops/{shop_id}/sales-history/sample", headers=headers)
    assert generated.status_code == 201
    assert generated.json()["created"] == 60

    prediction_response = client.get(f"/api/v1/shops/{shop_id}/waste-risk?language=es", headers=headers)
    assert prediction_response.status_code == 200
    prediction = next(item for item in prediction_response.json() if item["lot_id"] == lot_id)
    assert prediction["data_points"] == 60
    assert 0 <= prediction["risk_score"] <= 100
    assert prediction["risk_level"] in {"low", "medium", "high"}
    assert "descuento" in prediction["recommendation"].lower()
    assert prediction["calculated_at"]
    public_lot = client.get(f"/api/v1/lots/{lot_id}").json()
    assert "sales_history" not in public_lot
    assert "recommendation" not in public_lot
    assert client.post(f"/api/v1/products/{product_id}/sales-history", json={"entries": []}).status_code == 401


def test_sample_history_is_idempotent_and_private_to_shop_owner():
    reset_db()
    client = TestClient(main.app)
    owner_headers = create_business(client, "owner-risk@example.com")
    other_headers = create_business(client, "other-risk@example.com")
    shop_id, _, _ = create_product_and_lot(client, owner_headers)

    first_load = client.post(f"/api/v1/shops/{shop_id}/sales-history/sample", headers=owner_headers)
    second_load = client.post(f"/api/v1/shops/{shop_id}/sales-history/sample", headers=owner_headers)

    assert first_load.json() == {"created": 60, "existing": 0}
    assert second_load.json() == {"created": 0, "existing": 60}
    assert client.post(f"/api/v1/shops/{shop_id}/sales-history/sample", headers=other_headers).status_code == 404


def test_manual_sales_history_is_validated_and_owner_only():
    reset_db()
    client = TestClient(main.app)
    owner_headers = create_business(client, "manual-sales@example.com")
    other_headers = create_business(client, "other-manual-sales@example.com")
    _, product_id, _ = create_product_and_lot(client, owner_headers)
    sales_date = date.today().isoformat()
    payload = {
        "entries": [
            {"sales_date": sales_date, "units_sold": 5, "had_promotion": False},
            {
                "sales_date": (date.today() - timedelta(days=1)).isoformat(),
                "units_sold": 3,
                "had_promotion": True,
            },
        ]
    }

    response = client.post(
        f"/api/v1/products/{product_id}/sales-history",
        json=payload,
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert response.json() == {"created": 2, "existing": 0}

    duplicate_date_payload = {
        "entries": [
            {"sales_date": sales_date, "units_sold": 5},
            {"sales_date": sales_date, "units_sold": 6},
        ]
    }
    duplicate_date_response = client.post(
        f"/api/v1/products/{product_id}/sales-history",
        json=duplicate_date_payload,
        headers=owner_headers,
    )
    assert duplicate_date_response.status_code == 422
    assert (
        client.post(
            f"/api/v1/products/{product_id}/sales-history",
            json=payload,
            headers=other_headers,
        ).status_code
        == 404
    )


def test_waste_risk_returns_typed_insufficient_history_error():
    reset_db()
    client = TestClient(main.app)
    headers = create_business(client, "short-history@example.com")
    shop_id, _, _ = create_product_and_lot(client, headers)

    response = client.get(f"/api/v1/shops/{shop_id}/waste-risk", headers=headers)

    assert response.status_code == 422
    assert "daily sales records" in response.json()["detail"]
