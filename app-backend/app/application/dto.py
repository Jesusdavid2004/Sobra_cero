from dataclasses import dataclass
from datetime import date

from app.domain.value_objects import RiskScore


@dataclass(frozen=True)
class DailySales:
    sales_date: date
    units_sold: int
    had_promotion: bool


@dataclass(frozen=True)
class PredictionEstimate:
    average_daily_sales: float
    expected_sales: float
    units_at_risk: float
    risk_score: RiskScore


@dataclass(frozen=True)
class WasteRiskResult:
    product_id: int
    product_name: str
    lot_id: int
    current_stock: int
    days_remaining: int
    data_points: int
    average_daily_sales: float
    expected_sales: float
    units_at_risk: float
    risk_score: RiskScore
    recommendation: str
