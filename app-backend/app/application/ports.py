from datetime import date
from typing import Protocol, Sequence

from app.application.dto import DailySales, PredictionEstimate


class SalesHistoryRepository(Protocol):
    def list_for_product(self, product_id: int, since: date) -> list[DailySales]: ...

    def save_prediction(
        self,
        *,
        product_id: int,
        lot_id: int,
        risk_score: int,
        units_at_risk: float,
        expected_sales: float,
        recommendation: str,
    ) -> None: ...


class PredictionModel(Protocol):
    def predict(
        self,
        history: Sequence[DailySales],
        current_stock: int,
        days_remaining: int,
        today: date,
    ) -> PredictionEstimate: ...


class AIProvider(Protocol):
    def complete(self, prompt: str) -> str: ...
