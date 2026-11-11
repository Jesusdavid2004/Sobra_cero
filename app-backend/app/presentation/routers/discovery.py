from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.orm import Session

from app.application.ai_dto import DiscoveryIntent
from app.application.use_cases.discover_lots import DiscoverLots, DiscoveryResult
from app.application.use_cases.parse_discovery_intent import ParseDiscoveryIntent
from app.auth import current_user
from app.db import get_db
from app.dependencies import (
    build_discover_lots_use_case,
    build_parse_discovery_intent_use_case,
)
from app.domain.discovery import DiscoveryQuery, LotAssessment
from app.domain.rules import (
    DEFAULT_DISCOVERY_RADIUS_KM,
    MAX_DISCOVERY_QUANTITY,
    MAX_DISCOVERY_RADIUS_KM,
    MAX_DISCOVERY_TEXT_CHARS,
)
from app.models import User

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


class AssessmentOut(BaseModel):
    lot_id: int
    shop_id: int
    title: str
    category: str
    available_quantity: int
    unit_price_cents: int
    closes_at: datetime
    distance_km: float
    travel_minutes: int
    slack_minutes: int
    reasons: list[str]


class DiscoveryOut(BaseModel):
    approximate: Literal[True] = True
    feasible: list[AssessmentOut]
    excluded: list[AssessmentOut]
    nearest_unreachable: AssessmentOut | None


class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=MAX_DISCOVERY_TEXT_CHARS)


def _assessment_out(item: LotAssessment) -> AssessmentOut:
    candidate = item.candidate
    return AssessmentOut(
        lot_id=candidate.lot_id,
        shop_id=candidate.shop_id,
        title=candidate.title,
        category=candidate.category,
        available_quantity=candidate.available_quantity,
        unit_price_cents=candidate.unit_price_cents,
        closes_at=candidate.closes_at,
        distance_km=item.distance_km,
        travel_minutes=item.travel_minutes,
        slack_minutes=item.slack_minutes,
        reasons=[reason.value for reason in item.reasons],
    )


def _discovery_out(result: DiscoveryResult) -> DiscoveryOut:
    nearest = result.nearest_unreachable
    return DiscoveryOut(
        feasible=[_assessment_out(item) for item in result.feasible],
        excluded=[_assessment_out(item) for item in result.excluded],
        nearest_unreachable=_assessment_out(nearest) if nearest else None,
    )


@router.get("/lots", response_model=DiscoveryOut)
def discover_lots(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    window_start: AwareDatetime = Query(),
    window_end: AwareDatetime = Query(),
    radius_km: float = Query(DEFAULT_DISCOVERY_RADIUS_KM, gt=0, le=MAX_DISCOVERY_RADIUS_KM),
    quantity: int = Query(1, ge=1, le=MAX_DISCOVERY_QUANTITY),
    budget_cents: int | None = Query(None, ge=0),
    category: str | None = Query(None, min_length=2, max_length=40),
    db: Session = Depends(get_db),
) -> DiscoveryOut:
    query = DiscoveryQuery(latitude, longitude, window_start, window_end, radius_km, quantity, budget_cents, category)
    use_case: DiscoverLots = build_discover_lots_use_case(db)
    return _discovery_out(use_case.execute(query, datetime.now(timezone.utc)))


@router.post("/parse", response_model=DiscoveryIntent)
def parse_discovery_request(
    body: ParseRequest,
    language: Literal["en", "es"] = Query("en"),
    user: User = Depends(current_user),
) -> DiscoveryIntent:
    use_case: ParseDiscoveryIntent = build_parse_discovery_intent_use_case()
    return use_case.execute(body.text, user.id, language)
