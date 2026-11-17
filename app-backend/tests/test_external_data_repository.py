from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.domain.collection import (
    ExecutionStatus,
    ProductOutcome,
    RecordKind,
    RecordStatus,
    Trigger,
    UpsertOutcome,
)
from app.domain.external_data import ExternalBusinessRecord, ExternalProductRecord
from app.domain.places import PlaceCategory
from app.infrastructure.repositories.external_data_repository import (
    SqlAlchemyExternalDataRepository,
)
from app.models_external import (
    ExternalBusinessRow,
    ExternalSourceRow,
    PriceObservationRow,
    ScrapingExecutionRow,
    ScrapingRecordRow,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        yield db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def source(session, key: str = "osm", kind: str = "overpass") -> ExternalSourceRow:
    row = ExternalSourceRow(key=key, name=key.upper(), kind=kind)
    session.add(row)
    session.flush()
    return row


def business(name: str = "Panadería El Trigo", external_id: str = "node/1", latitude: float = 1.2136):
    return ExternalBusinessRecord(
        source_key="osm",
        external_id=external_id,
        name=name,
        category=PlaceCategory.BAKERY,
        latitude=latitude,
        longitude=-77.2811,
        address="Calle 18",
        city="Pasto",
        website="",
        phone="",
        opening_hours="",
        source_url="https://www.openstreetmap.org/node/1",
        observed_at=NOW,
    )


def product(price: int = 5990, original: int | None = 7990, observed_at: datetime = NOW):
    return ExternalProductRecord(
        source_key="shop",
        name="Pan tajado",
        category="Panadería",
        url="https://tienda.example/pan",
        price_cop=price,
        original_price_cop=original,
        discount_percent=25 if original else 0,
        availability="InStock",
        shop_name="Tienda",
        observed_at=observed_at,
    )


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_a_business_seen_again_is_updated_not_duplicated(session):
    repository = SqlAlchemyExternalDataRepository(session)
    osm = source(session)

    first = repository.upsert_business(osm, business())
    again = repository.upsert_business(osm, business())

    assert (first, again) == (UpsertOutcome.CREATED, UpsertOutcome.UPDATED)
    assert count(session, ExternalBusinessRow) == 1


def test_the_same_business_from_another_source_is_detected_as_a_duplicate(session):
    repository = SqlAlchemyExternalDataRepository(session)
    osm, directory = source(session), source(session, "directory")
    repository.upsert_business(osm, business())

    outcome = repository.upsert_business(directory, business("Panaderia El Trigo", "dir-9", latitude=1.21365))

    assert outcome is UpsertOutcome.DUPLICATE
    assert count(session, ExternalBusinessRow) == 1


def test_a_different_business_next_door_is_kept(session):
    repository = SqlAlchemyExternalDataRepository(session)
    osm = source(session)
    repository.upsert_business(osm, business())

    outcome = repository.upsert_business(osm, business("Restaurante La Plaza", "node/2", latitude=1.21365))

    assert outcome is UpsertOutcome.CREATED
    assert count(session, ExternalBusinessRow) == 2


def test_a_discovered_business_is_never_stored_as_affiliated_and_demo_data_is_flagged(session):
    repository = SqlAlchemyExternalDataRepository(session)
    demo = source(session, "demo", "demo")

    repository.upsert_business(demo, business())

    row = session.scalar(select(ExternalBusinessRow))
    assert row is not None
    assert (row.affiliation, row.verification_status, row.is_demo) == ("discovered", "unverified", True)


def test_a_new_product_records_its_first_price(session):
    repository = SqlAlchemyExternalDataRepository(session)
    shop = source(session, "shop", "jsonld_catalog")

    assert repository.upsert_product(shop, product()) is ProductOutcome.CREATED
    assert count(session, PriceObservationRow) == 1


def test_an_unchanged_price_does_not_add_history(session):
    repository = SqlAlchemyExternalDataRepository(session)
    shop = source(session, "shop", "jsonld_catalog")
    repository.upsert_product(shop, product())

    outcome = repository.upsert_product(shop, product(observed_at=NOW + timedelta(days=1)))

    assert outcome is ProductOutcome.UNCHANGED
    assert count(session, PriceObservationRow) == 1


def test_a_price_change_is_kept_as_history(session):
    repository = SqlAlchemyExternalDataRepository(session)
    shop = source(session, "shop", "jsonld_catalog")
    repository.upsert_product(shop, product())

    outcome = repository.upsert_product(shop, product(price=4990, observed_at=NOW + timedelta(days=1)))

    assert outcome is ProductOutcome.PRICE_CHANGED
    prices = session.scalars(select(PriceObservationRow.price_cop).order_by(PriceObservationRow.observed_at)).all()
    assert list(prices) == [5990, 4990]


def test_an_execution_records_its_result_and_the_sources_last_run(session):
    repository = SqlAlchemyExternalDataRepository(session)
    osm = source(session)
    execution_id = repository.start_execution(osm.id, Trigger.MANUAL, None, NOW)

    repository.finish_execution(execution_id, ExecutionStatus.SUCCEEDED, NOW + timedelta(minutes=2), 10, 2, 1)

    execution = session.get(ScrapingExecutionRow, execution_id)
    assert execution is not None
    assert (execution.status, execution.items_accepted, execution.items_rejected) == ("succeeded", 10, 2)
    assert osm.last_run_at is not None


def test_a_rejected_record_keeps_its_reason_and_a_bounded_payload(session):
    repository = SqlAlchemyExternalDataRepository(session)
    osm = source(session)
    execution_id = repository.start_execution(osm.id, Trigger.MANUAL, None, NOW)

    repository.add_record(
        execution_id, RecordKind.BUSINESS, RecordStatus.REJECTED, "outside_area", "https://x.example", "p" * 9000, NOW
    )

    record = session.scalar(select(ScrapingRecordRow))
    assert record is not None
    assert record.reason == "outside_area" and len(record.payload) == 2000
