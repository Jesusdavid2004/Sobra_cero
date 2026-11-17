import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.collection import (
    ProductOutcome,
    RecordKind,
    RecordStatus,
    UpsertOutcome,
)
from app.domain.external_data import ExternalBusinessRecord, ExternalProductRecord
from app.domain.places import BoundingBox
from app.infrastructure.repositories.external_data_repository import (
    SqlAlchemyExternalDataRepository,
)
from app.models_external import ExternalSourceRow

ACCEPTED = "accepted"
REJECTED = "rejected"
PENDING = "pending"
DUPLICATES = "duplicates"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CollectionContext:
    """What one run shares between the spider and its pipelines.

    `pending` counts businesses that were new in this run: they are stored as unverified and wait
    for a person to verify them. `accepted` counts every valid record stored or refreshed.
    """

    session: Session
    source: ExternalSourceRow
    execution_id: int
    area: BoundingBox | None = None
    clock: Callable[[], datetime] = utc_now
    counters: Counter[str] = field(default_factory=Counter)
    stop_reason: str = ""

    @property
    def repository(self) -> SqlAlchemyExternalDataRepository:
        return SqlAlchemyExternalDataRepository(self.session)

    def reject(self, kind: RecordKind, reason: str, source_url: str, raw: Mapping[str, object]) -> None:
        self.counters[REJECTED] += 1
        payload = json.dumps(dict(raw), ensure_ascii=False, default=str)
        self.repository.add_record(
            self.execution_id, kind, RecordStatus.REJECTED, reason, source_url, payload, self.clock()
        )

    def store_business(self, record: ExternalBusinessRecord) -> UpsertOutcome:
        outcome = self.repository.upsert_business(self.source, record)
        if outcome is UpsertOutcome.DUPLICATE:
            self.counters[DUPLICATES] += 1
            return outcome
        self.counters[ACCEPTED] += 1
        if outcome is UpsertOutcome.CREATED:
            self.counters[PENDING] += 1
        return outcome

    def store_product(self, record: ExternalProductRecord) -> ProductOutcome:
        outcome = self.repository.upsert_product(self.source, record)
        self.counters[ACCEPTED] += 1
        return outcome

    def commit(self) -> None:
        self.session.commit()
