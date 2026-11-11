from math import ceil
from typing import Sequence

from app.application.dto import ANALYSIS_SOURCE_LOCAL, LotAnalysis, LotAnalysisInput
from app.application.ports import PredictionModel, RescueAnalyzer
from app.domain.exceptions import InvalidAnalysisRequestError
from app.domain.rescue import decide_rescue
from app.domain.rules import (
    HOURS_PER_DAY,
    MAX_ANALYSIS_HISTORY_ROWS,
    MAX_ANALYSIS_HORIZON_HOURS,
    MAX_ANALYSIS_SHOP_LOTS,
    MAX_DISCOUNT_PERCENT,
    MIN_HISTORY_DAYS,
    RESCUE_RULE_VERSION,
)
from app.infrastructure.prediction.weekday_sales_forecast import (
    WeekdaySalesForecastModel,
)
from app.infrastructure.prediction.weighted_moving_average import (
    WeightedMovingAveragePredictionModel,
)


def validate_lot_input(lot: LotAnalysisInput) -> None:
    if lot.available_quantity <= 0:
        raise InvalidAnalysisRequestError("Available quantity must be positive")
    if not 0 <= lot.current_discount_percent <= MAX_DISCOUNT_PERCENT:
        raise InvalidAnalysisRequestError("Discount percent is out of range")
    if not 0 < lot.horizon_hours <= MAX_ANALYSIS_HORIZON_HOURS:
        raise InvalidAnalysisRequestError("Horizon is out of range")
    if not MIN_HISTORY_DAYS <= len(lot.history) <= MAX_ANALYSIS_HISTORY_ROWS:
        raise InvalidAnalysisRequestError("Sales history size is out of range")


class LocalRescueAnalyzer(RescueAnalyzer):
    """In-process analysis. It is also the source of truth the gRPC service executes."""

    def __init__(self, source: str = ANALYSIS_SOURCE_LOCAL) -> None:
        self._source = source

    def analyze_lot(self, request_id: str, lot: LotAnalysisInput) -> LotAnalysis:
        validate_lot_input(lot)
        horizon_days = max(1, ceil(lot.horizon_hours / HOURS_PER_DAY))
        estimate = self._prediction_model(lot).predict(
            lot.history, lot.available_quantity, horizon_days, lot.as_of_date
        )
        decision = decide_rescue(
            available_quantity=lot.available_quantity,
            expected_sales=estimate.expected_sales,
            current_discount_percent=lot.current_discount_percent,
            hours_left=lot.horizon_hours,
        )
        return LotAnalysis(
            lot_ref=lot.lot_ref,
            expected_sales=estimate.expected_sales,
            surplus_units=decision.surplus_units,
            action=decision.action,
            proposed_discount_percent=decision.proposed_discount_percent,
            reasons=decision.reasons,
            model_version=estimate.model_version,
            rule_version=RESCUE_RULE_VERSION,
            horizon_days_used=horizon_days,
            source=self._source,
        )

    def analyze_shop(self, request_id: str, lots: Sequence[LotAnalysisInput]) -> list[LotAnalysis]:
        if not 0 < len(lots) <= MAX_ANALYSIS_SHOP_LOTS:
            raise InvalidAnalysisRequestError("Lot count is out of range")
        ranked = sorted(
            ((lot, self.analyze_lot(request_id, lot)) for lot in lots),
            key=lambda pair: (-pair[1].surplus_units / pair[0].available_quantity, pair[0].horizon_hours),
        )
        return [analysis for _lot, analysis in ranked]

    @staticmethod
    def _prediction_model(lot: LotAnalysisInput) -> PredictionModel:
        if lot.model is None:
            return WeightedMovingAveragePredictionModel()
        try:
            return WeekdaySalesForecastModel(lot.model)
        except ValueError as exc:
            raise InvalidAnalysisRequestError("Weekday model factors are invalid") from exc
