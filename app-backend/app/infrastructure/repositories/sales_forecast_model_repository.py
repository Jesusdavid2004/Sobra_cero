"""Persist sales forecast training data, artifacts, and active-model state."""

import json
from datetime import date, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.application.dto import (
    DailySales,
    SalesForecastEvaluation,
    SalesForecastModelArtifact,
)
from app.application.ports import SalesForecastModelRepository
from app.models import SalesForecastModel, SalesHistory

ACTIVE_STATUS = "active"
CANDIDATE_STATUS = "candidate"
ACTIVE_SLOT = "active"
TRAINING_HISTORY_LOOKBACK_DAYS = 365


class SqlAlchemySalesForecastModelRepository(SalesForecastModelRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_training_history(self) -> list[list[DailySales]]:
        latest_date = self._session.scalar(select(func.max(SalesHistory.sales_date)))
        if latest_date is None:
            return []
        earliest_date = latest_date - timedelta(days=TRAINING_HISTORY_LOOKBACK_DAYS - 1)
        rows = self._session.scalars(
            select(SalesHistory)
            .where(SalesHistory.sales_date >= earliest_date)
            .order_by(SalesHistory.product_id, SalesHistory.sales_date)
        )
        histories: dict[int, list[DailySales]] = {}
        for row in rows:
            histories.setdefault(row.product_id, []).append(
                DailySales(
                    sales_date=row.sales_date,
                    units_sold=row.units_sold,
                    had_promotion=row.had_promotion,
                )
            )
        return list(histories.values())

    def get_active_model(self) -> SalesForecastModelArtifact | None:
        model = self._session.scalar(select(SalesForecastModel).where(SalesForecastModel.status == ACTIVE_STATUS))
        if model is None:
            return None
        try:
            raw_artifact = json.loads(model.artifact_json)
            factors = raw_artifact["weekday_factors"]
            artifact = SalesForecastModelArtifact(
                version=raw_artifact["version"],
                weekday_factors=tuple(float(factor) for factor in factors),
                trained_until=date.fromisoformat(raw_artifact["trained_until"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Stored sales model artifact {model.version} is invalid") from exc
        if artifact.version != model.version:
            raise ValueError(f"Stored sales model artifact {model.version} has a mismatched version")
        return artifact

    def save_evaluation(self, evaluation: SalesForecastEvaluation, *, activate: bool) -> None:
        artifact = evaluation.artifact
        if activate:
            self._session.execute(
                update(SalesForecastModel)
                .where(SalesForecastModel.status == ACTIVE_STATUS)
                .values(status=CANDIDATE_STATUS, active_slot=None)
            )
        self._session.add(
            SalesForecastModel(
                version=artifact.version,
                artifact_json=json.dumps(
                    {
                        "version": artifact.version,
                        "weekday_factors": artifact.weekday_factors,
                        "trained_until": artifact.trained_until.isoformat(),
                    },
                    allow_nan=False,
                    sort_keys=True,
                ),
                training_samples=evaluation.training_samples,
                evaluation_samples=evaluation.evaluation_samples,
                baseline_mae=evaluation.baseline_mae,
                model_mae=evaluation.model_mae,
                status=ACTIVE_STATUS if activate else CANDIDATE_STATUS,
                active_slot=ACTIVE_SLOT if activate else None,
            )
        )
        self._session.commit()
