"""Vocabulary of the data collection engine (the Scanner)."""

from enum import StrEnum


class SourceKind(StrEnum):
    OVERPASS = "overpass"
    JSONLD_CATALOG = "jsonld_catalog"
    DEMO = "demo"


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class Trigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class RecordKind(StrEnum):
    BUSINESS = "business"
    PRODUCT = "product"


class RecordStatus(StrEnum):
    REJECTED = "rejected"
    PENDING_VALIDATION = "pending_validation"


class UpsertOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DUPLICATE = "duplicate"


class ProductOutcome(StrEnum):
    CREATED = "created"
    PRICE_CHANGED = "price_changed"
    UNCHANGED = "unchanged"


class StopReason(StrEnum):
    ACCESS_DENIED = "access_denied"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    NOT_ALLOWED = "not_allowed"


MAX_ERROR_CHARS = 500
MAX_PAYLOAD_CHARS = 2000
EXECUTION_TIMEOUT_SECONDS = 300
