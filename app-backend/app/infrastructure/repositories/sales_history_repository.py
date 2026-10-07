from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.dto import DailySales
from app.application.ports import SalesHistoryRepository
from app.models import SalesHistory, WastePrediction


class PostgresSalesHistoryRepository(SalesHistoryRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_product(self, product_id: int, since: date) -> list[DailySales]:
        entries = self._session.scalars(
            select(SalesHistory)
            .where(SalesHistory.product_id == product_id, SalesHistory.sales_date >= since)
            .order_by(SalesHistory.sales_date)
        )
        return [
            DailySales(
                sales_date=entry.sales_date,
                units_sold=entry.units_sold,
                had_promotion=entry.had_promotion,
            )
            for entry in entries
        ]

    def save_prediction(
        self,
        *,
        product_id: int,
        lot_id: int,
        risk_score: int,
        units_at_risk: float,
        expected_sales: float,
        recommendation: str,
    ) -> None:
        prediction = WastePrediction(
            product_id=product_id,
            lot_id=lot_id,
            risk_score=risk_score,
            units_at_risk=units_at_risk,
            expected_sales=expected_sales,
            recommendation=recommendation,
        )
        self._session.add(prediction)
        self._session.commit()
