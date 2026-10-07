from datetime import date, datetime, timedelta, timezone

from app.application.dto import WasteRiskResult
from app.application.ports import AIProvider, PredictionModel, SalesHistoryRepository
from app.domain.exceptions import InsufficientSalesHistoryError

MINIMUM_HISTORY_DAYS = 14
HISTORY_LOOKBACK_DAYS = 90
RECOMMENDATION_PROMPT = (
    "You are a waste-reduction advisor for a {business_type}. The product "
    "'{product_name}' has a waste risk score of {score}/100, with an estimated "
    "{units_at_risk} units unsold before it expires in {days_remaining} days. "
    "Recent average sales: {average_sales}. Respond in {language}. Suggest, in "
    "max 3 lines: (1) recommended discount percentage, (2) whether to publish "
    "it now or wait, (3) whether it's better offered as a donation instead of a sale. "
    "Be concrete and brief."
)


class CalculateWasteRiskUseCase:
    def __init__(
        self,
        repository: SalesHistoryRepository,
        prediction_model: PredictionModel,
        ai_provider: AIProvider,
    ) -> None:
        self._repository = repository
        self._prediction_model = prediction_model
        self._ai_provider = ai_provider

    def execute(
        self,
        *,
        product_id: int,
        product_name: str,
        business_type: str,
        lot_id: int,
        current_stock: int,
        expires_at: datetime,
        language: str,
        today: date | None = None,
    ) -> WasteRiskResult:
        calculation_date = today or datetime.now(timezone.utc).date()
        days_remaining = max(0, (expires_at.date() - calculation_date).days)
        history = self._repository.list_for_product(
            product_id, calculation_date - timedelta(days=HISTORY_LOOKBACK_DAYS - 1)
        )
        if len(history) < MINIMUM_HISTORY_DAYS:
            raise InsufficientSalesHistoryError(
                f"At least {MINIMUM_HISTORY_DAYS} daily sales records are required for this product"
            )

        estimate = self._prediction_model.predict(history, current_stock, days_remaining, calculation_date)
        recommendation_prompt = RECOMMENDATION_PROMPT.format(
            business_type=business_type,
            product_name=product_name,
            score=estimate.risk_score.value,
            units_at_risk=f"{estimate.units_at_risk:.1f}",
            days_remaining=days_remaining,
            average_sales=f"{estimate.average_daily_sales:.1f} units/day",
            language="Spanish" if language == "es" else "English",
        )
        recommendation = self._ai_provider.complete(recommendation_prompt)
        self._repository.save_prediction(
            product_id=product_id,
            lot_id=lot_id,
            risk_score=estimate.risk_score.value,
            units_at_risk=estimate.units_at_risk,
            expected_sales=estimate.expected_sales,
            recommendation=recommendation,
        )
        return WasteRiskResult(
            product_id=product_id,
            product_name=product_name,
            lot_id=lot_id,
            current_stock=current_stock,
            days_remaining=days_remaining,
            data_points=len(history),
            average_daily_sales=estimate.average_daily_sales,
            expected_sales=estimate.expected_sales,
            units_at_risk=estimate.units_at_risk,
            risk_score=estimate.risk_score,
            recommendation=recommendation,
        )
