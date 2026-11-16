import re
from collections.abc import Collection
from datetime import datetime
from urllib.parse import urlsplit

from app.application.dto import Actor
from app.application.ports import ScannerRepository, SourceRunner, UnitOfWork
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
from app.domain.collection import EXECUTION_TIMEOUT_SECONDS, Trigger
from app.domain.exceptions import (
    ScannerBusinessNotFoundError,
    ScannerPermissionError,
    ScannerSourceNotFoundError,
    SourceInvalidError,
    SourceNotRunnableError,
)
from app.domain.source_policy import RUNNABLE_KINDS
from app.domain.url_policy import Resolver, validate_source_url

SOURCE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}$")
MAX_NAME_CHARS = 160
MIN_REVIEW_NOTE_CHARS = 10
MAX_NOTE_CHARS = 1000
MIN_SCHEDULE_MINUTES = 15
MAX_SCHEDULE_MINUTES = 10080
MAX_LIST_ROWS = 200
VERIFICATION_STATUSES = ("unverified", "verified", "rejected")


def _require_admin(actor: Actor) -> None:
    if not actor.is_admin:
        raise ScannerPermissionError("Administrator account required")


def _existing(repository: ScannerRepository, key: str) -> SourceView:
    source = repository.get_source(key)
    if source is None:
        raise ScannerSourceNotFoundError("Source not found")
    return source


class ListScannerSources:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(self, actor: Actor) -> list[SourceView]:
        _require_admin(actor)
        return self._repository.list_sources()


class RegisterSource:
    """New sources start disabled and unreviewed; their URL must pass the safety policy."""

    def __init__(
        self,
        repository: ScannerRepository,
        unit_of_work: UnitOfWork,
        allowed_domains: Collection[str],
        resolve: Resolver,
        enforce_url_policy: bool = True,
    ) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work
        self._allowed_domains = allowed_domains
        self._resolve = resolve
        self._enforce_url_policy = enforce_url_policy

    def execute(self, actor: Actor, key: str, name: str, kind: str, base_url: str, license_note: str) -> SourceView:
        _require_admin(actor)
        if not SOURCE_KEY.match(key):
            raise SourceInvalidError("invalid_key")
        if not name.strip() or len(name) > MAX_NAME_CHARS:
            raise SourceInvalidError("invalid_name")
        if kind not in RUNNABLE_KINDS:
            raise SourceInvalidError("invalid_kind")
        if self._enforce_url_policy:
            validate_source_url(base_url, self._allowed_domains, self._resolve)
        source = self._repository.add_source(
            key, name.strip(), kind, base_url.strip(), urlsplit(base_url).hostname or "", license_note.strip()
        )
        self._unit_of_work.commit()
        return source


class RecordTermsReview:
    """A person states that they read the source's terms and licence. Nothing runs before this."""

    def __init__(self, repository: ScannerRepository, unit_of_work: UnitOfWork) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work

    def execute(self, actor: Actor, key: str, note: str, license_note: str, now: datetime) -> SourceView:
        _require_admin(actor)
        _existing(self._repository, key)
        if not MIN_REVIEW_NOTE_CHARS <= len(note.strip()) <= MAX_NOTE_CHARS:
            raise SourceInvalidError("invalid_review_note")
        self._repository.record_terms_review(key, actor.user_id, note.strip(), license_note.strip(), now)
        self._unit_of_work.commit()
        return _existing(self._repository, key)


class SetSourceEnabled:
    def __init__(self, repository: ScannerRepository, unit_of_work: UnitOfWork) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work

    def execute(self, actor: Actor, key: str, enabled: bool) -> SourceView:
        _require_admin(actor)
        source = _existing(self._repository, key)
        if enabled and not source.terms_reviewed:
            raise SourceNotRunnableError("terms_not_reviewed")
        self._repository.set_enabled(key, enabled)
        self._unit_of_work.commit()
        return _existing(self._repository, key)


class SetSourceSchedule:
    def __init__(self, repository: ScannerRepository, unit_of_work: UnitOfWork) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work

    def execute(self, actor: Actor, key: str, minutes: int | None) -> SourceView:
        _require_admin(actor)
        _existing(self._repository, key)
        if minutes is not None and not MIN_SCHEDULE_MINUTES <= minutes <= MAX_SCHEDULE_MINUTES:
            raise SourceInvalidError("invalid_schedule")
        self._repository.set_schedule(key, minutes)
        self._unit_of_work.commit()
        return _existing(self._repository, key)


class RunSourceNow:
    """Start a run in its own process. The runner applies the policy gate and records the refusal."""

    def __init__(self, repository: ScannerRepository, unit_of_work: UnitOfWork, runner: SourceRunner) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work
        self._runner = runner

    def execute(self, actor: Actor, key: str, now: datetime) -> RunResult:
        _require_admin(actor)
        _existing(self._repository, key)
        self._repository.fail_stale_runs(now, EXECUTION_TIMEOUT_SECONDS * 2)
        self._unit_of_work.commit()
        return self._runner.run(key, Trigger.MANUAL.value, actor.user_id)


class RunDueSources:
    """Run every enabled, reviewed source whose schedule says it is due. Used by the scheduler."""

    def __init__(self, repository: ScannerRepository, unit_of_work: UnitOfWork, runner: SourceRunner) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work
        self._runner = runner

    def execute(self, now: datetime) -> list[RunResult]:
        self._repository.fail_stale_runs(now, EXECUTION_TIMEOUT_SECONDS * 2)
        self._unit_of_work.commit()
        return [self._runner.run(key, Trigger.SCHEDULED.value, None) for key in self._repository.due_sources(now)]


class GetScannerSummary:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(self, actor: Actor, now: datetime) -> ScannerSummary:
        _require_admin(actor)
        return self._repository.summary(now)


class ListExecutions:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(self, actor: Actor, source_key: str | None, limit: int) -> list[ExecutionView]:
        _require_admin(actor)
        return self._repository.list_executions(source_key, min(limit, MAX_LIST_ROWS))


class ListExecutionRecords:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(self, actor: Actor, execution_id: int, limit: int) -> list[RecordView]:
        _require_admin(actor)
        return self._repository.list_records(execution_id, min(limit, MAX_LIST_ROWS))


class ListCollectedProducts:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(
        self, actor: Actor, source_key: str | None, promotions_only: bool, limit: int, now: datetime
    ) -> list[ProductView]:
        _require_admin(actor)
        return self._repository.list_products(source_key, promotions_only, min(limit, MAX_LIST_ROWS), now)


class GetPriceHistory:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(self, actor: Actor, product_id: int) -> list[PricePoint]:
        _require_admin(actor)
        return self._repository.price_history(product_id)


class ListDiscoveredBusinesses:
    def __init__(self, repository: ScannerRepository) -> None:
        self._repository = repository

    def execute(self, actor: Actor, verification: str | None, limit: int, now: datetime) -> list[BusinessView]:
        _require_admin(actor)
        return self._repository.list_businesses(verification, min(limit, MAX_LIST_ROWS), now)


class VerifyBusiness:
    """A person confirms or rejects a discovered business. It never makes it an affiliate."""

    def __init__(self, repository: ScannerRepository, unit_of_work: UnitOfWork) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work

    def execute(self, actor: Actor, business_id: int, status: str) -> None:
        _require_admin(actor)
        if status not in VERIFICATION_STATUSES:
            raise SourceInvalidError("invalid_verification")
        if not self._repository.set_business_verification(business_id, status):
            raise ScannerBusinessNotFoundError("Business not found")
        self._unit_of_work.commit()
