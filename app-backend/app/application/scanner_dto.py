from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceView:
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


@dataclass(frozen=True)
class ExecutionView:
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


@dataclass(frozen=True)
class RecordView:
    id: int
    kind: str
    status: str
    reason: str
    source_url: str
    payload: str
    created_at: datetime


@dataclass(frozen=True)
class ProductView:
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


@dataclass(frozen=True)
class PricePoint:
    observed_at: datetime
    price_cop: int
    original_price_cop: int | None
    discount_percent: int


@dataclass(frozen=True)
class BusinessView:
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


@dataclass(frozen=True)
class ScannerSummary:
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
    last_runs: tuple[ExecutionView, ...]


@dataclass(frozen=True)
class RunResult:
    execution_id: int
    status: str
    accepted: int
    rejected: int
    pending: int
    duplicates: int
    stop_reason: str
    error: str
