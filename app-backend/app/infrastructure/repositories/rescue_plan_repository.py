import json
from datetime import datetime
from typing import Mapping

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.dto import LotSnapshot
from app.application.ports import RescueLotGateway, RescuePlanRepository, UnitOfWork
from app.domain.entities import BatchStatus
from app.domain.exceptions import RescuePlanConflictError
from app.domain.rescue import RescueAction, RescuePlan, RescuePlanStatus, RescueReason
from app.models import Lot, RescuePlanEventRecord, RescuePlanRecord, Shop


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class SqlAlchemyRescueLotGateway(RescueLotGateway):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_snapshot(self, lot_id: int) -> LotSnapshot | None:
        row = self._session.execute(
            select(Lot, Shop.owner_id).join(Shop, Shop.id == Lot.shop_id).where(Lot.id == lot_id)
        ).first()
        if row is None:
            return None
        lot, owner_id = row
        return LotSnapshot(
            lot_id=lot.id,
            shop_id=lot.shop_id,
            owner_id=owner_id,
            product_id=lot.product_id,
            quantity=lot.quantity,
            discount_percent=lot.discount_percent,
            status=lot.status,
            expires_at=lot.expires_at,
            pickup_ends_at=lot.pickup_ends_at,
        )

    def get_shop_owner_id(self, shop_id: int) -> int | None:
        return self._session.scalar(select(Shop.owner_id).where(Shop.id == shop_id))

    def apply_discount_if_unchanged(self, lot_id: int, expected_quantity: int, discount_percent: int) -> bool:
        result = self._session.execute(
            update(Lot)
            .where(
                Lot.id == lot_id,
                Lot.quantity == expected_quantity,
                Lot.status == BatchStatus.ACTIVE.value,
            )
            .values(discount_percent=discount_percent)
        )
        return result.rowcount == 1


class SqlAlchemyRescuePlanRepository(RescuePlanRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, plan: RescuePlan) -> RescuePlan:
        record = RescuePlanRecord(
            lot_id=plan.lot_id,
            shop_id=plan.shop_id,
            status=plan.status.value,
            action=plan.action.value,
            reasons_json=json.dumps([reason.value for reason in plan.reasons]),
            available_quantity=plan.available_quantity,
            expected_sales=plan.expected_sales,
            surplus_units=plan.surplus_units,
            proposed_discount_percent=plan.proposed_discount_percent,
            horizon_hours=plan.horizon_hours,
            data_points=plan.data_points,
            rule_version=plan.rule_version,
            model_version=plan.model_version,
            inputs_json=json.dumps(plan.inputs),
            created_by=plan.created_by,
            created_at=plan.created_at,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise RescuePlanConflictError("A rescue plan is already being generated for this lot") from exc
        return _to_entity(record)

    def get(self, plan_id: int) -> RescuePlan | None:
        record = self._session.get(RescuePlanRecord, plan_id)
        return _to_entity(record) if record else None

    def list_for_shop(self, shop_id: int, status: RescuePlanStatus | None) -> list[RescuePlan]:
        query = select(RescuePlanRecord).where(RescuePlanRecord.shop_id == shop_id)
        if status is not None:
            query = query.where(RescuePlanRecord.status == status.value)
        records = self._session.scalars(query.order_by(RescuePlanRecord.created_at.desc(), RescuePlanRecord.id.desc()))
        return [_to_entity(record) for record in records]

    def supersede_pending_for_lot(self, lot_id: int) -> list[int]:
        pending_ids = list(
            self._session.scalars(
                select(RescuePlanRecord.id).where(
                    RescuePlanRecord.lot_id == lot_id,
                    RescuePlanRecord.status == RescuePlanStatus.PENDING_APPROVAL.value,
                )
            )
        )
        if pending_ids:
            self._session.execute(
                update(RescuePlanRecord)
                .where(RescuePlanRecord.id.in_(pending_ids))
                .values(status=RescuePlanStatus.SUPERSEDED.value)
            )
        return pending_ids

    def mark_decided(self, plan_id: int, status: RescuePlanStatus, actor_id: int, now: datetime) -> bool:
        result = self._session.execute(
            update(RescuePlanRecord)
            .where(
                RescuePlanRecord.id == plan_id,
                RescuePlanRecord.status == RescuePlanStatus.PENDING_APPROVAL.value,
            )
            .values(status=status.value, decided_by=actor_id, decided_at=now)
        )
        return result.rowcount == 1

    def record_event(self, plan_id: int, event_type: str, actor_id: int | None, payload: Mapping[str, object]) -> None:
        self._session.add(
            RescuePlanEventRecord(
                plan_id=plan_id,
                event_type=event_type,
                actor_id=actor_id,
                payload_json=json.dumps(payload),
            )
        )


def _to_entity(record: RescuePlanRecord) -> RescuePlan:
    return RescuePlan(
        id=record.id,
        lot_id=record.lot_id,
        shop_id=record.shop_id,
        status=RescuePlanStatus(record.status),
        action=RescueAction(record.action),
        reasons=tuple(RescueReason(reason) for reason in json.loads(record.reasons_json)),
        available_quantity=record.available_quantity,
        expected_sales=record.expected_sales,
        surplus_units=record.surplus_units,
        proposed_discount_percent=record.proposed_discount_percent,
        horizon_hours=record.horizon_hours,
        data_points=record.data_points,
        rule_version=record.rule_version,
        model_version=record.model_version,
        inputs=json.loads(record.inputs_json),
        created_by=record.created_by,
        created_at=record.created_at,
        decided_by=record.decided_by,
        decided_at=record.decided_at,
    )
