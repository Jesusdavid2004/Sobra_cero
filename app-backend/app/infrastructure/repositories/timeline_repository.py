from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.timeline import DonationRow, PlanEventRow, ReservationRow
from app.models import Donation, RescuePlanEventRecord, RescuePlanRecord, Reservation


class SqlAlchemyLotTimelineSource:
    def __init__(self, session: Session) -> None:
        self._session = session

    def plan_events(self, lot_id: int) -> list[PlanEventRow]:
        rows = self._session.execute(
            select(
                RescuePlanEventRecord.plan_id,
                RescuePlanEventRecord.event_type,
                RescuePlanEventRecord.created_at,
                RescuePlanEventRecord.payload_json,
            )
            .join(RescuePlanRecord, RescuePlanRecord.id == RescuePlanEventRecord.plan_id)
            .where(RescuePlanRecord.lot_id == lot_id)
        ).all()
        return [PlanEventRow(row[0], row[1], row[2], row[3]) for row in rows]

    def reservations(self, lot_id: int) -> list[ReservationRow]:
        rows = self._session.execute(
            select(
                Reservation.quantity,
                Reservation.status,
                Reservation.created_at,
                Reservation.status_changed_at,
            ).where(Reservation.lot_id == lot_id)
        ).all()
        return [ReservationRow(row[0], row[1], row[2], row[3]) for row in rows]

    def donations(self, lot_id: int) -> list[DonationRow]:
        rows = self._session.execute(
            select(Donation.quantity, Donation.created_at).where(Donation.lot_id == lot_id)
        ).all()
        return [DonationRow(row[0], row[1]) for row in rows]
