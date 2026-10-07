"""Application composition root for request-scoped dependencies."""

from sqlalchemy.orm import Session

from app.application.use_cases.calculate_waste_risk import CalculateWasteRiskUseCase
from app.infrastructure.prediction.weighted_moving_average import (
    WeightedMovingAveragePredictionModel,
)
from app.infrastructure.repositories.sales_history_repository import (
    PostgresSalesHistoryRepository,
)
from app.llm import build_client


def build_calculate_waste_risk_use_case(db: Session) -> CalculateWasteRiskUseCase:
    return CalculateWasteRiskUseCase(
        repository=PostgresSalesHistoryRepository(db),
        prediction_model=WeightedMovingAveragePredictionModel(),
        ai_provider=build_client(),
    )
