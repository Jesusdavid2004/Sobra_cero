from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.collection import (
    MAX_ERROR_CHARS,
    MAX_PAYLOAD_CHARS,
    ExecutionStatus,
    ProductOutcome,
    RecordKind,
    RecordStatus,
    Trigger,
    UpsertOutcome,
)
from app.domain.external_data import ExternalBusinessRecord, ExternalProductRecord
from app.domain.places import (
    Affiliation,
    Place,
    PlaceCategory,
    are_duplicates,
    normalize_name,
)
from app.models_external import (
    ExternalBusinessRow,
    ExternalProductRow,
    ExternalSourceRow,
    PriceObservationRow,
    ScrapingExecutionRow,
    ScrapingRecordRow,
)

DUPLICATE_SEARCH_DEGREES = 0.001


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def business_as_place(row: ExternalBusinessRow, source_key: str) -> Place:
    return Place(
        place_id=f"ext:{row.id}",
        name=row.name,
        category=PlaceCategory(row.category),
        affiliation=Affiliation(row.affiliation),
        latitude=row.latitude,
        longitude=row.longitude,
        address=row.address,
        city=row.city,
        website=row.website,
        opening_hours=row.opening_hours,
        source=source_key,
        source_url=row.source_url,
        last_seen_at=_aware(row.last_seen_at),
        verified=row.verification_status == "verified",
    )


class SqlAlchemyExternalDataRepository:
    """Stores what collectors found. Nothing written here is ever an affiliated shop or a lot."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_source(self, key: str) -> ExternalSourceRow | None:
        return self._session.scalar(select(ExternalSourceRow).where(ExternalSourceRow.key == key))

    def upsert_business(self, source: ExternalSourceRow, record: ExternalBusinessRecord) -> UpsertOutcome:
        existing = self._session.scalar(
            select(ExternalBusinessRow).where(
                ExternalBusinessRow.source_id == source.id,
                ExternalBusinessRow.external_id == record.external_id,
            )
        )
        if existing is not None:
            existing.last_seen_at = record.observed_at
            existing.opening_hours = record.opening_hours or existing.opening_hours
            existing.website = record.website or existing.website
            existing.phone = record.phone or existing.phone
            existing.address = record.address or existing.address
            return UpsertOutcome.UPDATED
        twin = self._find_twin(record)
        if twin is not None:
            twin.last_seen_at = max(_aware(twin.last_seen_at), record.observed_at)
            return UpsertOutcome.DUPLICATE
        self._session.add(
            ExternalBusinessRow(
                source_id=source.id,
                external_id=record.external_id,
                name=record.name,
                normalized_name=normalize_name(record.name),
                category=record.category.value,
                latitude=record.latitude,
                longitude=record.longitude,
                address=record.address,
                city=record.city,
                website=record.website,
                phone=record.phone,
                opening_hours=record.opening_hours,
                source_url=record.source_url,
                is_demo=source.kind == "demo",
                first_seen_at=record.observed_at,
                last_seen_at=record.observed_at,
            )
        )
        self._session.flush()
        return UpsertOutcome.CREATED

    def _find_twin(self, record: ExternalBusinessRecord) -> ExternalBusinessRow | None:
        candidate = Place(
            "new", record.name, record.category, Affiliation.DISCOVERED, record.latitude, record.longitude,
            "", "", "", "", "", "", None, False,
        )  # fmt: skip
        nearby = self._session.scalars(
            select(ExternalBusinessRow).where(
                ExternalBusinessRow.latitude.between(
                    record.latitude - DUPLICATE_SEARCH_DEGREES, record.latitude + DUPLICATE_SEARCH_DEGREES
                ),
                ExternalBusinessRow.longitude.between(
                    record.longitude - DUPLICATE_SEARCH_DEGREES, record.longitude + DUPLICATE_SEARCH_DEGREES
                ),
            )
        )
        return next((row for row in nearby if are_duplicates(business_as_place(row, ""), candidate)), None)

    def upsert_product(self, source: ExternalSourceRow, record: ExternalProductRecord) -> ProductOutcome:
        row = self._session.scalar(
            select(ExternalProductRow).where(
                ExternalProductRow.source_id == source.id, ExternalProductRow.url == record.url
            )
        )
        if row is None:
            row = ExternalProductRow(
                source_id=source.id,
                name=record.name,
                category=record.category,
                url=record.url,
                shop_name=record.shop_name,
                current_price_cop=record.price_cop,
                original_price_cop=record.original_price_cop,
                discount_percent=record.discount_percent,
                availability=record.availability,
                first_seen_at=record.observed_at,
                last_seen_at=record.observed_at,
            )
            self._session.add(row)
            self._session.flush()
            self._observe(row.id, record)
            return ProductOutcome.CREATED
        row.last_seen_at = record.observed_at
        row.availability = record.availability
        changed = (row.current_price_cop, row.original_price_cop) != (record.price_cop, record.original_price_cop)
        if not changed:
            return ProductOutcome.UNCHANGED
        row.current_price_cop = record.price_cop
        row.original_price_cop = record.original_price_cop
        row.discount_percent = record.discount_percent
        self._observe(row.id, record)
        return ProductOutcome.PRICE_CHANGED

    def _observe(self, product_id: int, record: ExternalProductRecord) -> None:
        self._session.add(
            PriceObservationRow(
                product_id=product_id,
                price_cop=record.price_cop,
                original_price_cop=record.original_price_cop,
                discount_percent=record.discount_percent,
                observed_at=record.observed_at,
            )
        )
        self._session.flush()

    def start_execution(self, source_id: int, trigger: Trigger, user_id: int | None, now: datetime) -> int:
        execution = ScrapingExecutionRow(
            source_id=source_id, trigger=trigger.value, requested_by=user_id, started_at=now
        )
        self._session.add(execution)
        self._session.flush()
        return execution.id

    def finish_execution(
        self,
        execution_id: int,
        status: ExecutionStatus,
        now: datetime,
        accepted: int,
        rejected: int,
        pending: int,
        stop_reason: str = "",
        error: str = "",
    ) -> None:
        execution = self._session.get(ScrapingExecutionRow, execution_id)
        if execution is None:
            return
        execution.status = status.value
        execution.finished_at = now
        execution.items_accepted = accepted
        execution.items_rejected = rejected
        execution.items_pending = pending
        execution.stop_reason = stop_reason
        execution.error_message = error[:MAX_ERROR_CHARS]
        source = self._session.get(ExternalSourceRow, execution.source_id)
        if source is not None:
            source.last_run_at = now

    def add_record(
        self,
        execution_id: int,
        kind: RecordKind,
        status: RecordStatus,
        reason: str,
        source_url: str,
        payload: str,
        now: datetime,
    ) -> None:
        self._session.add(
            ScrapingRecordRow(
                execution_id=execution_id,
                kind=kind.value,
                status=status.value,
                reason=reason,
                source_url=source_url[:500],
                payload=payload[:MAX_PAYLOAD_CHARS],
                created_at=now,
            )
        )
        self._session.flush()
