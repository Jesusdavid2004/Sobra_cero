from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.dto import Actor
from app.application.use_cases.inventory import DiagnosisResult
from app.auth import current_user
from app.db import get_db
from app.dependencies import (
    build_diagnose_shop_use_case,
    build_list_shop_waste_use_case,
    build_record_waste_use_case,
)
from app.domain.waste import MAX_WASTE_NOTE_CHARS, WasteReason
from app.infrastructure.realtime.notifier import notify_lot_changed
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["inventory"])
MAX_WASTE_UNITS = 10000


class WasteIn(BaseModel):
    quantity: int = Field(gt=0, le=MAX_WASTE_UNITS)
    reason: WasteReason
    note: str = Field(default="", max_length=MAX_WASTE_NOTE_CHARS * 2)


class WasteRecordedOut(BaseModel):
    lot_id: int
    remaining_quantity: int


class WasteEntryOut(BaseModel):
    id: int
    lot_id: int
    lot_title: str
    quantity: int
    reason: str
    note: str
    created_at: datetime


class FactsOut(BaseModel):
    active_lots: int
    units_available: int
    lots_expiring_soon: int
    units_expiring_soon: int
    units_closing_soon: int
    picked_up_units: int
    delivered_donation_units: int
    cancelled_units: int
    wasted_units: int
    pending_pickup_units: int


class DiagnosisOut(BaseModel):
    facts: FactsOut
    alerts: list[str]
    limitations: list[str]
    data_used: list[str]
    narrative: str | None
    narrative_status: str


def _actor(user: User) -> Actor:
    return Actor(user_id=user.id, role=user.role, is_admin=user.is_admin)  # type: ignore[arg-type]


def _diagnosis_out(result: DiagnosisResult) -> DiagnosisOut:
    diagnosis = result.diagnosis
    return DiagnosisOut(
        facts=FactsOut(**diagnosis.facts.__dict__),
        alerts=[code.value for code in diagnosis.alerts],
        limitations=[code.value for code in diagnosis.limitations],
        data_used=[source.value for source in diagnosis.data_used],
        narrative=result.narrative,
        narrative_status=result.narrative_status,
    )


@router.post("/lots/{lot_id}/waste", response_model=WasteRecordedOut, status_code=201)
def record_waste(
    lot_id: int, body: WasteIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> WasteRecordedOut:
    use_case = build_record_waste_use_case(db)
    result = use_case.execute(_actor(user), lot_id, body.quantity, body.reason, body.note, datetime.now(timezone.utc))
    notify_lot_changed(db, lot_id)
    return WasteRecordedOut(lot_id=result.lot_id, remaining_quantity=result.remaining_quantity)


@router.get("/shops/{shop_id}/waste", response_model=list[WasteEntryOut])
def shop_waste(shop_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[WasteEntryOut]:
    entries = build_list_shop_waste_use_case(db).execute(_actor(user), shop_id)
    return [WasteEntryOut(**entry.__dict__) for entry in entries]


@router.get("/shops/{shop_id}/diagnosis", response_model=DiagnosisOut)
def shop_diagnosis(
    shop_id: int,
    language: Literal["en", "es"] = Query("en"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> DiagnosisOut:
    use_case = build_diagnose_shop_use_case(db)
    return _diagnosis_out(use_case.execute(_actor(user), shop_id, language, datetime.now(timezone.utc)))
