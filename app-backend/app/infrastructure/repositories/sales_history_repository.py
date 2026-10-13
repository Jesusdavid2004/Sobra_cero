from datetime import date
from typing import Sequence

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

    def upsert_many(self, product_id: int, entries: Sequence[DailySales]) -> tuple[int, int]:
        if not entries:
            return 0, 0
        dates = [entry.sales_date for entry in entries]
        existing_by_date = {
            entry.sales_date: entry
            for entry in self._session.scalars(
                select(SalesHistory).where(
                    SalesHistory.product_id == product_id,
                    SalesHistory.sales_date.in_(dates),
                )
            )
        }
        created = 0
        for entry in entries:
            existing = existing_by_date.get(entry.sales_date)
            if existing:
                existing.units_sold = entry.units_sold
                existing.had_promotion = entry.had_promotion
            else:
                self._session.add(
                    SalesHistory(
                        product_id=product_id,
                        sales_date=entry.sales_date,
                        units_sold=entry.units_sold,
                        had_promotion=entry.had_promotion,
                    )
                )
                created += 1
        self._session.commit()
        return created, len(entries) - created

    def save_prediction(
        self,
        *,
        product_id: int,
        lot_id: int,
        risk_score: int,
        units_at_risk: float,
        expected_sales: float,
        recommendation: str,
        model_version: str,
    ) -> None:
        prediction = WastePrediction(
            product_id=product_id,
            lot_id=lot_id,
            risk_score=risk_score,
            units_at_risk=units_at_risk,
            expected_sales=expected_sales,
            recommendation=recommendation,
            model_version=model_version,
        )
        self._session.add(prediction)
        self._session.commit()
