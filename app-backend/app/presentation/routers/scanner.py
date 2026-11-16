from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.dto import Actor
from app.application.scanner_dto import (
    BusinessView,
    ExecutionView,
    PricePoint,
    ProductView,
    RecordView,
    RunResult,
    ScannerSummary,
    SourceView,
)
from app.auth import current_user
from app.db import get_db
from app.dependencies import (
    build_get_price_history_use_case,
    build_get_scanner_summary_use_case,
    build_list_businesses_use_case,
    build_list_execution_records_use_case,
    build_list_executions_use_case,
    build_list_products_use_case,
    build_list_sources_use_case,
    build_record_terms_review_use_case,
    build_register_source_use_case,
    build_run_source_now_use_case,
    build_set_source_enabled_use_case,
    build_set_source_schedule_use_case,
    build_verify_business_use_case,
)
from app.models import User

router = APIRouter(prefix="/api/v1/admin/scanner", tags=["scanner"])
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class SourceOut(BaseModel):
    key: str
    name: str
    kind: str
    base_url: str
    enabled: bool
    terms_reviewed: bool
    terms_note: str
    license_note: str
    schedule_minutes: int | None
    last_run_at: datetime | None
    last_status: str
    last_stop_reason: str


class SourceIn(BaseModel):
    key: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    kind: Literal["overpass", "jsonld_catalog"]
    base_url: str = Field(min_length=8, max_length=500)
    license_note: str = Field(default="", max_length=1000)


class TermsReviewIn(BaseModel):
    note: str = Field(min_length=10, max_length=1000)
    license_note: str = Field(default="", max_length=1000)


class EnabledIn(BaseModel):
    enabled: bool


class ScheduleIn(BaseModel):
    minutes: int | None = Field(default=None, ge=15, le=10080)


class VerificationIn(BaseModel):
    status: Literal["unverified", "verified", "rejected"]


class ExecutionOut(BaseModel):
    id: int
    source_key: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    accepted: int
    rejected: int
    pending: int
    stop_reason: str
    error: str


class RunOut(BaseModel):
    execution_id: int
    status: str
    accepted: int
    rejected: int
    pending: int
    duplicates: int
    stop_reason: str
    error: str


class RecordOut(BaseModel):
    id: int
    kind: str
    status: str
    reason: str
    source_url: str
    payload: str
    created_at: datetime


class ProductOut(BaseModel):
    id: int
    source_key: str
    name: str
    category: str
    url: str
    shop_name: str
    price_cop: int
    original_price_cop: int | None
    discount_percent: int
    availability: str
    last_seen_at: datetime
    freshness: str


class PricePointOut(BaseModel):
    observed_at: datetime
    price_cop: int
    original_price_cop: int | None
    discount_percent: int


class BusinessOut(BaseModel):
    id: int
    source_key: str
    name: str
    category: str
    address: str
    latitude: float
    longitude: float
    affiliation: str
    verification_status: str
    is_demo: bool
    last_seen_at: datetime
    freshness: str


class SummaryOut(BaseModel):
    total_sources: int
    active_sources: int
    disabled_sources: int
    sources_with_errors: int
    products_found: int
    promotions_detected: int
    businesses_discovered: int
    rejected_records: int
    pending_validation: int
    stale_products: int
    last_runs: list[ExecutionOut]


def _actor(user: User) -> Actor:
    return Actor(user_id=user.id, role=user.role, is_admin=user.is_admin)  # type: ignore[arg-type]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source(view: SourceView) -> SourceOut:
    return SourceOut(**view.__dict__)


def _execution(view: ExecutionView) -> ExecutionOut:
    return ExecutionOut(**view.__dict__)


@router.get("/summary", response_model=SummaryOut)
def summary(db: Session = Depends(get_db), user: User = Depends(current_user)) -> SummaryOut:
    result: ScannerSummary = build_get_scanner_summary_use_case(db).execute(_actor(user), _now())
    values = {**result.__dict__, "last_runs": [_execution(run) for run in result.last_runs]}
    return SummaryOut(**values)


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[SourceOut]:
    return [_source(view) for view in build_list_sources_use_case(db).execute(_actor(user))]


@router.post("/sources", response_model=SourceOut, status_code=201)
def register_source(body: SourceIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> SourceOut:
    use_case = build_register_source_use_case(db)
    return _source(use_case.execute(_actor(user), body.key, body.name, body.kind, body.base_url, body.license_note))


@router.post("/sources/{key}/terms-review", response_model=SourceOut)
def review_terms(
    key: str, body: TermsReviewIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> SourceOut:
    use_case = build_record_terms_review_use_case(db)
    return _source(use_case.execute(_actor(user), key, body.note, body.license_note, _now()))


@router.post("/sources/{key}/enabled", response_model=SourceOut)
def set_enabled(
    key: str, body: EnabledIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> SourceOut:
    return _source(build_set_source_enabled_use_case(db).execute(_actor(user), key, body.enabled))


@router.put("/sources/{key}/schedule", response_model=SourceOut)
def set_schedule(
    key: str, body: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> SourceOut:
    return _source(build_set_source_schedule_use_case(db).execute(_actor(user), key, body.minutes))


@router.post("/sources/{key}/run", response_model=RunOut)
def run_now(key: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> RunOut:
    result: RunResult = build_run_source_now_use_case(db).execute(_actor(user), key, _now())
    return RunOut(**result.__dict__)


@router.get("/executions", response_model=list[ExecutionOut])
def list_executions(
    source: str | None = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ExecutionOut]:
    return [_execution(v) for v in build_list_executions_use_case(db).execute(_actor(user), source, limit)]


@router.get("/executions/{execution_id}/records", response_model=list[RecordOut])
def list_records(
    execution_id: int,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[RecordOut]:
    views: list[RecordView] = build_list_execution_records_use_case(db).execute(_actor(user), execution_id, limit)
    return [RecordOut(**view.__dict__) for view in views]


@router.get("/products", response_model=list[ProductOut])
def list_products(
    source: str | None = Query(None),
    promotions_only: bool = Query(False),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ProductOut]:
    use_case = build_list_products_use_case(db)
    views: list[ProductView] = use_case.execute(_actor(user), source, promotions_only, limit, _now())
    return [ProductOut(**view.__dict__) for view in views]


@router.get("/products/{product_id}/history", response_model=list[PricePointOut])
def price_history(
    product_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[PricePointOut]:
    points: list[PricePoint] = build_get_price_history_use_case(db).execute(_actor(user), product_id)
    return [PricePointOut(**point.__dict__) for point in points]


@router.get("/businesses", response_model=list[BusinessOut])
def list_businesses(
    verification: Literal["unverified", "verified", "rejected"] | None = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[BusinessOut]:
    views: list[BusinessView] = build_list_businesses_use_case(db).execute(_actor(user), verification, limit, _now())
    return [BusinessOut(**view.__dict__) for view in views]


@router.post("/businesses/{business_id}/verification", status_code=204)
def verify_business(
    business_id: int, body: VerificationIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    build_verify_business_use_case(db).execute(_actor(user), business_id, body.status)
