from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from app.application.dto import Actor
from app.auth import current_user
from app.db import get_db
from app.dependencies import (
    build_confirm_donation_delivery_use_case,
    build_create_donation_offer_use_case,
    build_draft_donation_message_use_case,
    build_find_donation_receivers_use_case,
    build_get_my_receiver_use_case,
    build_list_lot_donation_offers_use_case,
    build_list_receiver_offers_use_case,
    build_register_receiver_use_case,
    build_respond_to_donation_offer_use_case,
)
from app.domain.receivers import (
    NEW_RECEIVER_ID,
    OfferView,
    Receiver,
    ReceiverAssessment,
)
from app.domain.rules import (
    MAX_DONATION_MESSAGE_CHARS,
    MAX_RECEIVER_CAPACITY,
    MAX_UTC_OFFSET_MINUTES,
    MINUTES_PER_HOUR,
)
from app.infrastructure.realtime.notifier import notify_lot_changed
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["donations"])
CLOCK = r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$"
CategorySlug = Annotated[str, StringConstraints(pattern=r"^[a-z_]{2,40}$")]
MAX_ACCEPTED_CATEGORIES = 10
MAX_RECEIVER_NAME_CHARS = 160


class ReceiverIn(BaseModel):
    name: str = Field(min_length=2, max_length=MAX_RECEIVER_NAME_CHARS)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accepted_categories: list[CategorySlug] = Field(min_length=1, max_length=MAX_ACCEPTED_CATEGORIES)
    max_quantity: int = Field(ge=1, le=MAX_RECEIVER_CAPACITY)
    can_store_refrigerated: bool = False
    open_from: str = Field(pattern=CLOCK)
    open_until: str = Field(pattern=CLOCK)
    utc_offset_minutes: int = Field(default=0, ge=-MAX_UTC_OFFSET_MINUTES, le=MAX_UTC_OFFSET_MINUTES)


class ReceiverOut(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    accepted_categories: list[str]
    max_quantity: int
    can_store_refrigerated: bool
    open_from: str
    open_until: str
    utc_offset_minutes: int


class ReceiverAssessmentOut(BaseModel):
    receiver: ReceiverOut
    distance_km: float
    travel_minutes: int
    recent_accepted: int
    reasons: list[str]


class CandidatesOut(BaseModel):
    approximate: Literal[True] = True
    compatible: list[ReceiverAssessmentOut]
    excluded: list[ReceiverAssessmentOut]


class OfferIn(BaseModel):
    receiver_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=MAX_RECEIVER_CAPACITY)
    message: str = Field(default="", max_length=MAX_DONATION_MESSAGE_CHARS)


class DraftIn(BaseModel):
    receiver_id: int = Field(gt=0)


class DraftOut(BaseModel):
    text: str


class OfferOut(BaseModel):
    id: int
    lot_id: int
    lot_title: str
    category: str
    shop_name: str
    receiver_name: str
    quantity: int
    status: str
    message: str
    closes_at: datetime
    created_at: datetime
    decided_at: datetime | None
    delivered_at: datetime | None


def _actor(user: User) -> Actor:
    return Actor(user_id=user.id, role=user.role, is_admin=user.is_admin)  # type: ignore[arg-type]


def _clock(minute: int) -> str:
    return f"{minute // MINUTES_PER_HOUR:02d}:{minute % MINUTES_PER_HOUR:02d}"


def _minute(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * MINUTES_PER_HOUR + int(minutes)


def _receiver_out(receiver: Receiver) -> ReceiverOut:
    return ReceiverOut(
        id=receiver.id,
        name=receiver.name,
        latitude=receiver.latitude,
        longitude=receiver.longitude,
        accepted_categories=sorted(receiver.accepted_categories),
        max_quantity=receiver.max_quantity,
        can_store_refrigerated=receiver.can_store_refrigerated,
        open_from=_clock(receiver.open_from_minute),
        open_until=_clock(receiver.open_until_minute),
        utc_offset_minutes=receiver.utc_offset_minutes,
    )


def _assessment_out(item: ReceiverAssessment) -> ReceiverAssessmentOut:
    return ReceiverAssessmentOut(
        receiver=_receiver_out(item.receiver),
        distance_km=item.distance_km,
        travel_minutes=item.travel_minutes,
        recent_accepted=item.recent_accepted,
        reasons=[reason.value for reason in item.reasons],
    )


def _offer_out(view: OfferView) -> OfferOut:
    offer = view.offer
    return OfferOut(
        id=offer.id,
        lot_id=offer.lot_id,
        lot_title=view.lot_title,
        category=view.category,
        shop_name=view.shop_name,
        receiver_name=view.receiver_name,
        quantity=offer.quantity,
        status=offer.status.value,
        message=offer.message,
        closes_at=view.closes_at,
        created_at=offer.created_at,
        decided_at=offer.decided_at,
        delivered_at=offer.delivered_at,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/receivers", response_model=ReceiverOut, status_code=201)
def register_receiver(
    body: ReceiverIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> ReceiverOut:
    receiver = Receiver(
        NEW_RECEIVER_ID,
        user.id,
        body.name,
        body.latitude,
        body.longitude,
        frozenset(body.accepted_categories),
        body.max_quantity,
        body.can_store_refrigerated,
        _minute(body.open_from),
        _minute(body.open_until),
        body.utc_offset_minutes,
    )
    return _receiver_out(build_register_receiver_use_case(db).execute(receiver))


@router.get("/receivers/me", response_model=ReceiverOut)
def my_receiver(db: Session = Depends(get_db), user: User = Depends(current_user)) -> ReceiverOut:
    return _receiver_out(build_get_my_receiver_use_case(db).execute(_actor(user)))


@router.get("/receivers/me/offers", response_model=list[OfferOut])
def my_offers(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[OfferOut]:
    return [_offer_out(view) for view in build_list_receiver_offers_use_case(db).execute(_actor(user))]


@router.get("/lots/{lot_id}/donation-candidates", response_model=CandidatesOut)
def donation_candidates(
    lot_id: int,
    quantity: int = Query(gt=0, le=MAX_RECEIVER_CAPACITY),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CandidatesOut:
    matches = build_find_donation_receivers_use_case(db).execute(_actor(user), lot_id, quantity, _now())
    return CandidatesOut(
        compatible=[_assessment_out(item) for item in matches.compatible],
        excluded=[_assessment_out(item) for item in matches.excluded],
    )


@router.post("/lots/{lot_id}/donation-offers/draft", response_model=DraftOut)
def draft_offer_message(
    lot_id: int,
    body: DraftIn,
    language: Literal["en", "es"] = Query("en"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> DraftOut:
    use_case = build_draft_donation_message_use_case(db)
    return DraftOut(text=use_case.execute(_actor(user), lot_id, body.receiver_id, language, _now()))


@router.post("/lots/{lot_id}/donation-offers", response_model=OfferOut, status_code=201)
def create_offer(
    lot_id: int, body: OfferIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> OfferOut:
    use_case = build_create_donation_offer_use_case(db)
    offer = use_case.execute(_actor(user), lot_id, body.receiver_id, body.quantity, body.message, _now())
    return _offer_out(_find_view(db, user, lot_id, offer.id))


@router.get("/lots/{lot_id}/donation-offers", response_model=list[OfferOut])
def lot_offers(lot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[OfferOut]:
    return [_offer_out(view) for view in build_list_lot_donation_offers_use_case(db).execute(_actor(user), lot_id)]


def _find_view(db: Session, user: User, lot_id: int, offer_id: int) -> OfferView:
    views = build_list_lot_donation_offers_use_case(db).execute(_actor(user), lot_id)
    return next(view for view in views if view.offer.id == offer_id)


@router.post("/donation-offers/{offer_id}/accept", response_model=OfferOut)
def accept_offer(offer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> OfferOut:
    offer = build_respond_to_donation_offer_use_case(db).execute(_actor(user), offer_id, True, _now())
    notify_lot_changed(db, offer.lot_id)
    return _receiver_offer(db, user, offer.id)


@router.post("/donation-offers/{offer_id}/decline", response_model=OfferOut)
def decline_offer(offer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> OfferOut:
    offer = build_respond_to_donation_offer_use_case(db).execute(_actor(user), offer_id, False, _now())
    return _receiver_offer(db, user, offer.id)


@router.post("/donation-offers/{offer_id}/delivered", response_model=OfferOut)
def confirm_delivery(offer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> OfferOut:
    offer = build_confirm_donation_delivery_use_case(db).execute(_actor(user), offer_id, _now())
    return _offer_out(_find_view(db, user, offer.lot_id, offer.id))


def _receiver_offer(db: Session, user: User, offer_id: int) -> OfferOut:
    views = build_list_receiver_offers_use_case(db).execute(_actor(user))
    return _offer_out(next(view for view in views if view.offer.id == offer_id))
