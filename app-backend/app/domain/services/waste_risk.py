from dataclasses import dataclass
from typing import Sequence

from app.domain.exceptions import InvalidBatchQuantityError
from app.domain.value_objects import RiskScore


@dataclass(frozen=True)
class WasteRiskAssessment:
    expected_sales: float
    units_at_risk: float
    risk_score: RiskScore


def calculate_waste_risk(quantity: int, daily_forecasts: Sequence[float]) -> WasteRiskAssessment:
    if quantity <= 0:
        raise InvalidBatchQuantityError("Batch quantity must be positive")
    expected_sales = sum(daily_forecasts)
    units_at_risk = max(0.0, quantity - expected_sales)
    risk_score = max(0, min(100, round(100 * units_at_risk / quantity)))
    return WasteRiskAssessment(expected_sales, units_at_risk, RiskScore(risk_score))
