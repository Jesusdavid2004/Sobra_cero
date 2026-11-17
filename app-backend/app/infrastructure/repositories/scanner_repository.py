from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.scanner_dto import (
    BusinessView,
    ExecutionView,
    PricePoint,
    ProductView,
    RecordView,
    ScannerSummary,
    SourceView,
)
from app.domain.exceptions import SourceInvalidError
from app.domain.external_data import DEFAULT_MAX_AGE_HOURS, freshness
from app.models_external import (
    ExternalBusinessRow,
    ExternalProductRow,
    ExternalSourceRow,
    PriceObservationRow,
    ScrapingExecutionRow,
    ScrapingRecordRow,
)

LAST_RUNS_SHOWN = 5
PROBLEM_STATUSES = ("failed", "stopped")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SqlAlchemyScannerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- sources ----

    def _row(self, key: str) -> ExternalSourceRow | None:
        return self._session.scalar(select(ExternalSourceRow).where(ExternalSourceRow.key == key))

    def _last_execution(self, source_id: int) -> ScrapingExecutionRow | None:
        return self._session.scalar(
            select(ScrapingExecutionRow)
            .where(ScrapingExecutionRow.source_id == source_id)
            .order_by(ScrapingExecutionRow.started_at.desc(), ScrapingExecutionRow.id.desc())
        )

    def _source_view(self, row: ExternalSourceRow) -> SourceView:
        last = self._last_execution(row.id)
        return SourceView(
            key=row.key,
            name=row.name,
            kind=row.kind,
            base_url=row.base_url,
            enabled=row.enabled,
            terms_reviewed=row.terms_reviewed,
            terms_note=row.terms_note,
            license_note=row.license_note,
            schedule_minutes=row.schedule_minutes,
            last_run_at=_aware(row.last_run_at) if row.last_run_at else None,
            last_status=last.status if last else "",
            last_stop_reason=last.stop_reason if last else "",
        )

    def list_sources(self) -> list[SourceView]:
        rows = self._session.scalars(select(ExternalSourceRow).order_by(ExternalSourceRow.name))
        return [self._source_view(row) for row in rows]

    def get_source(self, key: str) -> SourceView | None:
        row = self._row(key)
        return self._source_view(row) if row else None

    def add_source(self, key: str, name: str, kind: str, base_url: str, domain: str, license_note: str) -> SourceView:
        row = ExternalSourceRow(
            key=key, name=name, kind=kind, base_url=base_url, domain=domain, license_note=license_note
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise SourceInvalidError("key_taken") from exc
        return self._source_view(row)

    def record_terms_review(self, key: str, user_id: int, note: str, license_note: str, now: datetime) -> bool:
        row = self._row(key)
        if row is None:
            return False
        row.terms_reviewed, row.terms_reviewed_by, row.terms_reviewed_at = True, user_id, now
        row.terms_note, row.license_note = note, license_note or row.license_note
        return True

    def set_enabled(self, key: str, enabled: bool) -> bool:
        row = self._row(key)
        if row is None:
            return False
        row.enabled = enabled
        return True

    def set_schedule(self, key: str, minutes: int | None) -> bool:
        row = self._row(key)
        if row is None:
            return False
        row.schedule_minutes = minutes
        return True

    def due_sources(self, now: datetime) -> list[str]:
        due = []
        rows = self._session.scalars(
            select(ExternalSourceRow).where(
                ExternalSourceRow.enabled.is_(True),
                ExternalSourceRow.terms_reviewed.is_(True),
                ExternalSourceRow.schedule_minutes.is_not(None),
            )
        )
        for row in rows:
            last = _aware(row.last_run_at) if row.last_run_at else None
            if last is None or now - last >= timedelta(minutes=row.schedule_minutes or 0):
                due.append(row.key)
        return due

    def fail_stale_runs(self, now: datetime, max_age_seconds: int) -> int:
        """Close runs left in `running` by a process that died, so history never lies."""
        limit = now - timedelta(seconds=max_age_seconds)
        stale = [
            row
            for row in self._session.scalars(
                select(ScrapingExecutionRow).where(ScrapingExecutionRow.status == "running")
            )
            if _aware(row.started_at) < limit
        ]
        for row in stale:
            row.status, row.finished_at, row.stop_reason = "failed", now, "crashed"
            row.error_message = "The run did not finish and was closed automatically"
        return len(stale)

    # ---- executions and records ----

    def _execution_view(self, row: ScrapingExecutionRow, source_key: str) -> ExecutionView:
        return ExecutionView(
            id=row.id,
            source_key=source_key,
            status=row.status,
            trigger=row.trigger,
            started_at=_aware(row.started_at),
            finished_at=_aware(row.finished_at) if row.finished_at else None,
            accepted=row.items_accepted,
            rejected=row.items_rejected,
            pending=row.items_pending,
            stop_reason=row.stop_reason,
            error=row.error_message,
        )

    def list_executions(self, source_key: str | None, limit: int) -> list[ExecutionView]:
        query = select(ScrapingExecutionRow, ExternalSourceRow.key).join(
            ExternalSourceRow, ScrapingExecutionRow.source_id == ExternalSourceRow.id
        )
        if source_key:
            query = query.where(ExternalSourceRow.key == source_key)
        rows = self._session.execute(
            query.order_by(ScrapingExecutionRow.started_at.desc(), ScrapingExecutionRow.id.desc()).limit(limit)
        )
        return [self._execution_view(execution, key) for execution, key in rows]

    def list_records(self, execution_id: int, limit: int) -> list[RecordView]:
        rows = self._session.scalars(
            select(ScrapingRecordRow)
            .where(ScrapingRecordRow.execution_id == execution_id)
            .order_by(ScrapingRecordRow.id)
            .limit(limit)
        )
        return [
            RecordView(r.id, r.kind, r.status, r.reason, r.source_url, r.payload, _aware(r.created_at)) for r in rows
        ]

    # ---- collected data ----

    def list_products(
        self, source_key: str | None, promotions_only: bool, limit: int, now: datetime
    ) -> list[ProductView]:
        query = select(ExternalProductRow, ExternalSourceRow.key).join(
            ExternalSourceRow, ExternalProductRow.source_id == ExternalSourceRow.id
        )
        if source_key:
            query = query.where(ExternalSourceRow.key == source_key)
        if promotions_only:
            query = query.where(ExternalProductRow.discount_percent > 0)
        rows = self._session.execute(query.order_by(ExternalProductRow.last_seen_at.desc()).limit(limit))
        return [
            ProductView(
                id=p.id,
                source_key=key,
                name=p.name,
                category=p.category,
                url=p.url,
                shop_name=p.shop_name,
                price_cop=p.current_price_cop,
                original_price_cop=p.original_price_cop,
                discount_percent=p.discount_percent,
                availability=p.availability,
                last_seen_at=_aware(p.last_seen_at),
                freshness=freshness(_aware(p.last_seen_at), now).value,
            )
            for p, key in rows
        ]

    def price_history(self, product_id: int) -> list[PricePoint]:
        rows = self._session.scalars(
            select(PriceObservationRow)
            .where(PriceObservationRow.product_id == product_id)
            .order_by(PriceObservationRow.observed_at, PriceObservationRow.id)
        )
        return [PricePoint(_aware(r.observed_at), r.price_cop, r.original_price_cop, r.discount_percent) for r in rows]

    def list_businesses(self, verification: str | None, limit: int, now: datetime) -> list[BusinessView]:
        query = select(ExternalBusinessRow, ExternalSourceRow.key).join(
            ExternalSourceRow, ExternalBusinessRow.source_id == ExternalSourceRow.id
        )
        if verification:
            query = query.where(ExternalBusinessRow.verification_status == verification)
        rows = self._session.execute(query.order_by(ExternalBusinessRow.last_seen_at.desc()).limit(limit))
        return [
            BusinessView(
                id=b.id,
                source_key=key,
                name=b.name,
                category=b.category,
                address=b.address,
                latitude=b.latitude,
                longitude=b.longitude,
                affiliation=b.affiliation,
                verification_status=b.verification_status,
                is_demo=b.is_demo,
                last_seen_at=_aware(b.last_seen_at),
                freshness=freshness(_aware(b.last_seen_at), now).value,
            )
            for b, key in rows
        ]

    def set_business_verification(self, business_id: int, status: str) -> bool:
        row = self._session.get(ExternalBusinessRow, business_id)
        if row is None:
            return False
        row.verification_status = status
        return True

    # ---- summary ----

    def _count(self, query) -> int:  # type: ignore[no-untyped-def]
        return self._session.scalar(query) or 0

    def summary(self, now: datetime) -> ScannerSummary:
        sources = list(self._session.scalars(select(ExternalSourceRow)))
        problems = 0
        for source in sources:
            last = self._last_execution(source.id)
            problems += int(last is not None and last.status in PROBLEM_STATUSES)
        stale_before = now - timedelta(hours=DEFAULT_MAX_AGE_HOURS)
        return ScannerSummary(
            total_sources=len(sources),
            active_sources=sum(1 for s in sources if s.enabled),
            disabled_sources=sum(1 for s in sources if not s.enabled),
            sources_with_errors=problems,
            products_found=self._count(select(func.count()).select_from(ExternalProductRow)),
            promotions_detected=self._count(
                select(func.count()).select_from(ExternalProductRow).where(ExternalProductRow.discount_percent > 0)
            ),
            businesses_discovered=self._count(select(func.count()).select_from(ExternalBusinessRow)),
            rejected_records=self._count(
                select(func.count()).select_from(ScrapingRecordRow).where(ScrapingRecordRow.status == "rejected")
            ),
            pending_validation=self._count(
                select(func.count())
                .select_from(ExternalBusinessRow)
                .where(ExternalBusinessRow.verification_status == "unverified")
            ),
            stale_products=self._count(
                select(func.count())
                .select_from(ExternalProductRow)
                .where(ExternalProductRow.last_seen_at < stale_before)
            ),
            last_runs=tuple(self.list_executions(None, LAST_RUNS_SHOWN)),
        )
