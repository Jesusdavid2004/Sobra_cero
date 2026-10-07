from collections import defaultdict
from datetime import date
from statistics import fmean
from typing import Sequence

from app.application.dto import DailySales, PredictionEstimate
from app.application.ports import PredictionModel
from app.domain.value_objects import RiskScore

RECENT_WINDOW_DAYS = 14
TREND_WINDOW_DAYS = 7
RECENT_WEIGHT = 0.65
WEEKDAY_WEIGHT = 0.35
MINIMUM_TREND_FACTOR = 0.5
MAXIMUM_TREND_FACTOR = 1.5
PROMOTION_NORMALIZATION = 0.85


class WeightedMovingAveragePredictionModel(PredictionModel):
    def predict(
        self,
        history: Sequence[DailySales],
        current_stock: int,
        days_remaining: int,
        today: date,
    ) -> PredictionEstimate:
        ordered_history = sorted(history, key=lambda entry: entry.sales_date)
        recent_history = ordered_history[-RECENT_WINDOW_DAYS:]
        recent_average = fmean(self._normalized_sales(entry) for entry in recent_history)

        previous_window = ordered_history[-2 * TREND_WINDOW_DAYS : -TREND_WINDOW_DAYS]
        latest_window = ordered_history[-TREND_WINDOW_DAYS:]
        previous_average = fmean(self._normalized_sales(entry) for entry in previous_window) if previous_window else 0
        latest_average = fmean(self._normalized_sales(entry) for entry in latest_window)
        if previous_average > 0:
            trend_factor = max(
                MINIMUM_TREND_FACTOR,
                min(MAXIMUM_TREND_FACTOR, latest_average / previous_average),
            )
        else:
            trend_factor = 1.0

        sales_by_weekday: dict[int, list[float]] = defaultdict(list)
        for entry in ordered_history:
            sales_by_weekday[entry.sales_date.weekday()].append(self._normalized_sales(entry))

        expected_sales = 0.0
        for day_offset in range(1, days_remaining + 1):
            weekday_sales = sales_by_weekday.get((today.weekday() + day_offset) % 7, [])
            weekday_average = fmean(weekday_sales) if weekday_sales else recent_average
            daily_estimate = (recent_average * RECENT_WEIGHT + weekday_average * WEEKDAY_WEIGHT) * trend_factor
            expected_sales += daily_estimate

        units_at_risk = max(0.0, current_stock - expected_sales)
        risk_percentage = round((units_at_risk / current_stock) * 100) if current_stock else 0
        return PredictionEstimate(
            average_daily_sales=round(recent_average * trend_factor, 2),
            expected_sales=round(expected_sales, 2),
            units_at_risk=round(units_at_risk, 2),
            risk_score=RiskScore(max(0, min(100, risk_percentage))),
        )

    @staticmethod
    def _normalized_sales(entry: DailySales) -> float:
        if entry.had_promotion:
            return entry.units_sold * PROMOTION_NORMALIZATION
        return float(entry.units_sold)
