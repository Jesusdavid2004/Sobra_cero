from datetime import date

from app.application.dto import SalesForecastEvaluation, SalesForecastModelArtifact
from app.application.use_cases.train_sales_forecast_model import TrainSalesForecastModel


class RecordingRepository:
    def __init__(self) -> None:
        self.activated: bool | None = None

    def list_training_history(self):
        return []

    def get_active_model(self):
        return None

    def save_evaluation(self, evaluation: SalesForecastEvaluation, *, activate: bool) -> None:
        self.activated = activate


class FixedTrainer:
    def __init__(self, *, model_mae: float, baseline_mae: float) -> None:
        self._evaluation = SalesForecastEvaluation(
            artifact=SalesForecastModelArtifact(
                version="test-model",
                weekday_factors=(1.0,) * 7,
                trained_until=date(2026, 9, 1),
            ),
            training_samples=20,
            evaluation_samples=8,
            baseline_mae=baseline_mae,
            model_mae=model_mae,
        )

    def train(self, histories):
        return self._evaluation


def test_training_use_case_activates_only_a_model_that_beats_the_baseline() -> None:
    repository = RecordingRepository()

    result = TrainSalesForecastModel(
        repository,
        FixedTrainer(model_mae=2.0, baseline_mae=3.0),
    ).execute()

    assert result.activated is True
    assert repository.activated is True
    assert result.version == "test-model"


def test_training_use_case_records_non_improving_model_without_activating_it() -> None:
    repository = RecordingRepository()

    result = TrainSalesForecastModel(
        repository,
        FixedTrainer(model_mae=3.0, baseline_mae=3.0),
    ).execute()

    assert result.activated is False
    assert repository.activated is False
