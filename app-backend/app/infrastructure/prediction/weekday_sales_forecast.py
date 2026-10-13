"""Train and apply a weekday-seasonal sales model using a chronological holdout."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from statistics import fmean
from typing import Sequence
from uuid import uuid4

from app.application.dto import (
    DailySales,
    PredictionEstimate,
    SalesForecastEvaluation,
    SalesForecastModelArtifact,
)
from app.application.ports import PredictionModel, SalesForecastTrainer
from app.domain.exceptions import InsufficientSalesTrainingDataError
from app.domain.services.waste_risk import calculate_waste_risk

TRAINING_FRACTION = 0.8
MINIMUM_TRAINING_SAMPLES = 14
MINIMUM_EVALUATION_SAMPLES = 7
SALES_WINDOW_DAYS = 7
PROMOTION_NORMALIZATION = 0.85


@dataclass(frozen=True)
class _TrainingSample:
    sales_date: date
    units_sold: float
    baseline: float


class WeekdaySalesForecastTrainer(SalesForecastTrainer):
    def train(self, histories: Sequence[Sequence[DailySales]]) -> SalesForecastEvaluation:
        samples = [sample for history in histories for sample in self._samples_for_history(history)]
        sample_dates = sorted({sample.sales_date for sample in samples})
        split_index = int(len(sample_dates) * TRAINING_FRACTION)
        if split_index == 0 or split_index >= len(sample_dates):
            raise InsufficientSalesTrainingDataError(
                "At least 28 distinct daily sales dates are required for time-based evaluation"
            )

        evaluation_start = sample_dates[split_index]
        training_samples = [sample for sample in samples if sample.sales_date < evaluation_start]
        evaluation_samples = [sample for sample in samples if sample.sales_date >= evaluation_start]
        if len(training_samples) < MINIMUM_TRAINING_SAMPLES or len(evaluation_samples) < MINIMUM_EVALUATION_SAMPLES:
            raise InsufficientSalesTrainingDataError(
                "Sales history must provide at least 14 training and 7 evaluation samples"
            )

        weekday_factors = self._fit_weekday_factors(training_samples)
        baseline_mae = self._mean_absolute_error(
            evaluation_samples,
            [sample.baseline for sample in evaluation_samples],
        )
        model_mae = self._mean_absolute_error(
            evaluation_samples,
            [sample.baseline * weekday_factors[sample.sales_date.weekday()] for sample in evaluation_samples],
        )
        artifact = SalesForecastModelArtifact(
            version=f"weekday-ratio-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}",
            weekday_factors=weekday_factors,
            trained_until=max(sample.sales_date for sample in training_samples),
        )
        return SalesForecastEvaluation(
            artifact=artifact,
            training_samples=len(training_samples),
            evaluation_samples=len(evaluation_samples),
            baseline_mae=round(baseline_mae, 4),
            model_mae=round(model_mae, 4),
        )

    @staticmethod
    def _samples_for_history(history: Sequence[DailySales]) -> list[_TrainingSample]:
        ordered = sorted(history, key=lambda entry: entry.sales_date)
        samples: list[_TrainingSample] = []
        for target_index in range(SALES_WINDOW_DAYS, len(ordered)):
            window = ordered[target_index - SALES_WINDOW_DAYS : target_index]
            if any(
                window[index].sales_date + timedelta(days=1) != window[index + 1].sales_date
                for index in range(len(window) - 1)
            ):
                continue
            if window[-1].sales_date + timedelta(days=1) != ordered[target_index].sales_date:
                continue
            baseline = fmean(WeekdaySalesForecastModel.normalize(entry) for entry in window)
            if baseline <= 0:
                continue
            samples.append(
                _TrainingSample(
                    sales_date=ordered[target_index].sales_date,
                    units_sold=WeekdaySalesForecastModel.normalize(ordered[target_index]),
                    baseline=baseline,
                )
            )
        return samples

    @staticmethod
    def _fit_weekday_factors(samples: Sequence[_TrainingSample]) -> tuple[float, ...]:
        actual_by_weekday = [0.0] * 7
        baseline_by_weekday = [0.0] * 7
        for sample in samples:
            weekday = sample.sales_date.weekday()
            actual_by_weekday[weekday] += sample.units_sold
            baseline_by_weekday[weekday] += sample.baseline
        overall_actual = sum(actual_by_weekday)
        overall_baseline = sum(baseline_by_weekday)
        overall_factor = overall_actual / overall_baseline if overall_baseline else 1.0
        return tuple(
            (
                actual_by_weekday[weekday] / baseline_by_weekday[weekday]
                if baseline_by_weekday[weekday] > 0
                else overall_factor
            )
            for weekday in range(7)
        )

    @staticmethod
    def _mean_absolute_error(samples: Sequence[_TrainingSample], predictions: Sequence[float]) -> float:
        return fmean(abs(sample.units_sold - prediction) for sample, prediction in zip(samples, predictions))


class WeekdaySalesForecastModel(PredictionModel):
    def __init__(self, artifact: SalesForecastModelArtifact) -> None:
        if len(artifact.weekday_factors) != 7 or any(
            not isfinite(factor) or factor < 0 for factor in artifact.weekday_factors
        ):
            raise ValueError("Sales forecast artifact must contain seven finite, non-negative weekday factors")
        self._artifact = artifact

    @staticmethod
    def normalize(entry: DailySales) -> float:
        return entry.units_sold * PROMOTION_NORMALIZATION if entry.had_promotion else float(entry.units_sold)

    def predict(
        self,
        history: Sequence[DailySales],
        current_stock: int,
        days_remaining: int,
        today: date,
    ) -> PredictionEstimate:
        recent_average = fmean(self.normalize(entry) for entry in sorted(history, key=lambda row: row.sales_date)[-7:])
        daily_forecasts = [
            recent_average * self._artifact.weekday_factors[(today.weekday() + offset) % 7]
            for offset in range(1, days_remaining + 1)
        ]
        assessment = calculate_waste_risk(current_stock, daily_forecasts)
        return PredictionEstimate(
            average_daily_sales=round(fmean(daily_forecasts), 2) if daily_forecasts else round(recent_average, 2),
            expected_sales=round(assessment.expected_sales, 2),
            units_at_risk=round(assessment.units_at_risk, 2),
            risk_score=assessment.risk_score,
            model_version=self._artifact.version,
        )
