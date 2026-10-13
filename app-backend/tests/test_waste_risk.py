from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main
from app.application.dto import DailySales, PredictionEstimate
from app.application.use_cases.calculate_waste_risk import CalculateWasteRiskUseCase
from app.db import Base, SessionLocal, engine
from app.domain.exceptions import (
    InsufficientSalesHistoryError,
    InsufficientSalesTrainingDataError,
    RiskScoreValidationError,
)
from app.domain.value_objects import RiskScore
from app.infrastructure.prediction.weekday_sales_forecast import (
    WeekdaySalesForecastModel,
    WeekdaySalesForecastTrainer,
)
from app.infrastructure.prediction.weighted_moving_average import (
    WeightedMovingAveragePredictionModel,
)
from app.models import SalesForecastModel, SalesHistory, User, WastePrediction


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
    assert result.model_version == "baseline-weighted-moving-average"


def test_weekday_model_is_trained_and_evaluated_on_a_later_time_window():
    start = date(2026, 7, 1)
    weekday_units = (4, 6, 8, 10, 12, 20, 24)
    history = [
        DailySales(start + timedelta(days=offset), weekday_units[(start + timedelta(days=offset)).weekday()], False)
        for offset in range(70)
    ]

    evaluation = WeekdaySalesForecastTrainer().train([history])
    prediction = WeekdaySalesForecastModel(evaluation.artifact).predict(
        history,
        current_stock=100,
        days_remaining=7,
        today=history[-1].sales_date,
    )

    assert evaluation.training_samples >= 14
    assert evaluation.evaluation_samples >= 7
    assert evaluation.artifact.trained_until < history[-1].sales_date
    assert evaluation.model_mae < evaluation.baseline_mae
    assert prediction.model_version == evaluation.artifact.version
    assert prediction.expected_sales == 84


def test_weekday_model_requires_a_chronological_holdout():
    with pytest.raises(InsufficientSalesTrainingDataError):
        WeekdaySalesForecastTrainer().train([[]])


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


def test_calculate_use_case_persists_prediction_and_returns_result():
    today = date(2026, 10, 6)
    history = [
        DailySales(sales_date=today - timedelta(days=offset), units_sold=3, had_promotion=False)
        for offset in range(14, 0, -1)
    ]

    class RecordingRepository:
        saved_prediction = None

        def list_for_product(self, product_id, since):
            return history

        def save_prediction(self, **kwargs):
            self.saved_prediction = kwargs

    class PredictingModel:
        def predict(self, history, current_stock, days_remaining, calculation_date):
            return PredictionEstimate(3.0, 6.0, 4.0, RiskScore(40))

    class RecordingAI:
        def complete(self, prompt):
            assert "40/100" in prompt
            assert "Respond in English" in prompt
            return "Publish with a 30% discount."

    repository = RecordingRepository()
    use_case = CalculateWasteRiskUseCase(repository, PredictingModel(), RecordingAI())
    result = use_case.execute(
        product_id=1,
        product_name="Bread",
        business_type="restaurant",
        lot_id=2,
        current_stock=10,
        expires_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        language="en",
        today=today,
    )

    assert result.risk_score == RiskScore(40)
    assert result.expected_sales == 6.0
    assert result.units_at_risk == 4.0
    assert repository.saved_prediction == {
        "product_id": 1,
        "lot_id": 2,
        "risk_score": 40,
        "units_at_risk": 4.0,
        "expected_sales": 6.0,
        "recommendation": "Publish with a 30% discount.",
        "model_version": "baseline-weighted-moving-average",
    }


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
    assert prediction["prediction_model"] == "baseline-weighted-moving-average"
    assert "descuento" in prediction["recommendation"].lower()
    assert prediction["calculated_at"]
    public_lot = client.get(f"/api/v1/lots/{lot_id}").json()
    assert "sales_history" not in public_lot
    assert "recommendation" not in public_lot


def test_admin_trains_and_activates_model_only_after_baseline_improvement():
    reset_db()
    client = TestClient(main.app)
    headers = create_business(client, "model-admin@example.com")
    shop_id, product_id, _ = create_product_and_lot(client, headers)
    assert client.post("/api/v1/admin/models/sales-forecast/train", headers=headers).status_code == 403
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "model-admin@example.com"))
        assert user is not None
        user.is_admin = True
        start = date.today() - timedelta(days=70)
        weekday_units = (4, 6, 8, 10, 12, 20, 24)
        db.add_all(
            [
                SalesHistory(
                    product_id=product_id,
                    sales_date=start + timedelta(days=offset),
                    units_sold=weekday_units[(start + timedelta(days=offset)).weekday()],
                    had_promotion=False,
                )
                for offset in range(70)
            ]
        )
        db.commit()

    training = client.post("/api/v1/admin/models/sales-forecast/train", headers=headers)
    risk_response = client.get(f"/api/v1/shops/{shop_id}/waste-risk", headers=headers)

    assert training.status_code == 200
    assert training.json()["activated"] is True
    assert training.json()["model_mae"] < training.json()["baseline_mae"]
    assert risk_response.status_code == 200
    assert risk_response.json()[0]["prediction_model"] == training.json()["model_version"]
    with SessionLocal() as db:
        model = db.scalar(select(SalesForecastModel).where(SalesForecastModel.status == "active"))
        assert model is not None
        assert model.version == training.json()["model_version"]
        prediction = db.scalar(
            select(WastePrediction).where(WastePrediction.lot_id == risk_response.json()[0]["lot_id"])
        )
        assert prediction is not None
        assert prediction.model_version == training.json()["model_version"]
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


def test_shop_and_product_catalog_reads_are_limited_to_owner_or_admin():
    reset_db()
    client = TestClient(main.app)
    owner_headers = create_business(client, "catalog-owner@example.com")
    other_headers = create_business(client, "catalog-other@example.com")
    shop_id, _, _ = create_product_and_lot(client, owner_headers)

    assert client.get("/api/v1/shops").status_code == 401
    assert [shop["id"] for shop in client.get("/api/v1/shops", headers=owner_headers).json()] == [shop_id]
    assert client.get("/api/v1/shops", headers=other_headers).json() == []
    assert client.get(f"/api/v1/shops/{shop_id}/products", headers=owner_headers).status_code == 200
    assert client.get(f"/api/v1/shops/{shop_id}/products", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/shops/{shop_id}/products").status_code == 401


def test_sales_csv_import_creates_and_updates_history_for_owner():
    reset_db()
    client = TestClient(main.app)
    owner_headers = create_business(client, "csv-owner@example.com")
    other_headers = create_business(client, "csv-other@example.com")
    _, product_id, _ = create_product_and_lot(client, owner_headers)
    csv_bytes = b"sales_date,units_sold,had_promotion\n2026-10-01,5,false\n2026-10-02,3,true\n"

    anonymous = client.post(
        f"/api/v1/products/{product_id}/sales-history/csv",
        files={"file": ("history.csv", csv_bytes, "text/csv")},
    )
    first = client.post(
        f"/api/v1/products/{product_id}/sales-history/csv",
        files={"file": ("history.csv", csv_bytes, "text/csv")},
        headers=owner_headers,
    )
    second = client.post(
        f"/api/v1/products/{product_id}/sales-history/csv",
        files={
            "file": (
                "history.csv",
                b"sales_date,units_sold,had_promotion\n2026-10-01,9,true\n2026-10-03,7,false\n",
                "text/csv",
            )
        },
        headers=owner_headers,
    )
    forbidden = client.post(
        f"/api/v1/products/{product_id}/sales-history/csv",
        files={"file": ("history.csv", csv_bytes, "text/csv")},
        headers=other_headers,
    )

    assert anonymous.status_code == 401
    assert first.status_code == 201
    assert first.json() == {"created": 2, "existing": 0}
    assert second.status_code == 201
    assert second.json() == {"created": 1, "existing": 1}
    assert forbidden.status_code == 404
    with SessionLocal() as db:
        rows = db.scalars(
            select(SalesHistory).where(SalesHistory.product_id == product_id).order_by(SalesHistory.sales_date)
        ).all()
        assert [(row.units_sold, row.had_promotion) for row in rows] == [(9, True), (3, True), (7, False)]


def test_sales_csv_import_rejects_invalid_rows_and_oversized_files():
    reset_db()
    client = TestClient(main.app)
    owner_headers = create_business(client, "csv-invalid@example.com")
    _, product_id, _ = create_product_and_lot(client, owner_headers)

    malformed = client.post(
        f"/api/v1/products/{product_id}/sales-history/csv",
        files={
            "file": (
                "history.csv",
                b"sales_date,units_sold,had_promotion\n2026-10-01,5,false\n2026-10-02,-1,true\n",
                "text/csv",
            )
        },
        headers=owner_headers,
    )
    oversized = client.post(
        f"/api/v1/products/{product_id}/sales-history/csv",
        files={"file": ("history.csv", b"x" * (main.MAX_SALES_HISTORY_IMPORT_BYTES + 1), "text/csv")},
        headers=owner_headers,
    )

    assert malformed.status_code == 422
    assert malformed.json()["code"] == "invalid_sales_history_csv"
    assert oversized.status_code == 413
    with SessionLocal() as db:
        assert db.scalar(select(SalesHistory.id).where(SalesHistory.product_id == product_id)) is None


def test_waste_risk_returns_typed_insufficient_history_error():
    reset_db()
    client = TestClient(main.app)
    headers = create_business(client, "short-history@example.com")
    shop_id, _, _ = create_product_and_lot(client, headers)

    response = client.get(f"/api/v1/shops/{shop_id}/waste-risk", headers=headers)

    assert response.status_code == 422
    assert "daily sales records" in response.json()["detail"]
