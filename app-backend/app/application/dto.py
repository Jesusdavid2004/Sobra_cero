from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.value_objects import RiskScore

UserRole = Literal["business", "customer"]


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
    model_version: str = "baseline-weighted-moving-average"


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
    model_version: str = "baseline-weighted-moving-average"


@dataclass(frozen=True)
class SalesForecastModelArtifact:
    version: str
    weekday_factors: tuple[float, ...]
    trained_until: date


@dataclass(frozen=True)
class SalesForecastEvaluation:
    artifact: SalesForecastModelArtifact
    training_samples: int
    evaluation_samples: int
    baseline_mae: float
    model_mae: float


@dataclass(frozen=True)
class SalesForecastTrainingResult:
    version: str
    training_samples: int
    evaluation_samples: int
    baseline_mae: float
    model_mae: float
    activated: bool


@dataclass(frozen=True)
class AuthUser:
    id: int
    email: str
    password_hash: str
    role: UserRole
    is_admin: bool


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
