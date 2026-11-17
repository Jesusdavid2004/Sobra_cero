from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem, IgnoreRequest
from scrapy.http import HtmlResponse, Request
from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.domain.collection import RecordKind, Trigger
from app.domain.places import PASTO_BOUNDS, BoundingBox
from app.infrastructure.repositories.external_data_repository import (
    SqlAlchemyExternalDataRepository,
)
from app.models_external import (
    ExternalBusinessRow,
    ExternalProductRow,
    ExternalSourceRow,
    ScrapingRecordRow,
)
from scraper.context import CollectionContext
from scraper.items import BusinessItem, ProductItem
from scraper.middlewares import StopOnAccessDeniedMiddleware
from scraper.pipelines import PersistencePipeline, ValidationPipeline

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def spider():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        source = ExternalSourceRow(key="osm", name="OSM", kind="overpass")
        session.add(source)
        session.flush()
        execution_id = SqlAlchemyExternalDataRepository(session).start_execution(source.id, Trigger.MANUAL, None, NOW)
        context = CollectionContext(session, source, execution_id, BoundingBox(*PASTO_BOUNDS), clock=lambda: NOW)
        yield SimpleNamespace(context=context, crawler=MagicMock())
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def business_item(**overrides) -> BusinessItem:
    fields = {
        "external_id": "node/1",
        "name": "Panadería El Trigo",
        "category": "bakery",
        "latitude": 1.2136,
        "longitude": -77.2811,
        "address": "Calle 18",
        "city": "Pasto",
        "source_url": "https://www.openstreetmap.org/node/1",
        **overrides,
    }
    return BusinessItem(**fields)


def test_a_valid_business_becomes_a_domain_record(spider):
    result = ValidationPipeline().process_item(business_item(), spider)

    assert result["kind"] is RecordKind.BUSINESS
    assert result["record"].name == "Panadería El Trigo"


def test_a_business_outside_the_area_is_dropped_and_its_rejection_is_stored(spider):
    with pytest.raises(DropItem):
        ValidationPipeline().process_item(business_item(latitude=4.7, longitude=-74.0), spider)

    assert spider.context.counters["rejected"] == 1
    record = spider.context.session.scalar(select(ScrapingRecordRow))
    assert record is not None
    assert (record.reason, record.status, record.kind) == ("outside_area", "rejected", "business")


def test_a_product_without_a_valid_price_is_dropped(spider):
    item = ProductItem(name="Pan", price="gratis", url="https://tienda.example/pan")

    with pytest.raises(DropItem):
        ValidationPipeline().process_item(item, spider)

    assert spider.context.counters["rejected"] == 1


def test_validated_records_are_stored_and_committed(spider):
    business = ValidationPipeline().process_item(business_item(), spider)
    product = ValidationPipeline().process_item(
        ProductItem(name="Pan", price="$5.990", original_price="$7.990", url="https://tienda.example/pan"), spider
    )

    pipeline = PersistencePipeline()
    pipeline.process_item(business, spider)
    pipeline.process_item(product, spider)
    pipeline.close_spider(spider)

    with SessionLocal() as other:
        assert other.scalar(select(func.count()).select_from(ExternalBusinessRow)) == 1
        stored = other.scalar(select(ExternalProductRow))
        assert stored is not None and stored.discount_percent == 25
    assert spider.context.counters["accepted"] == 2
    assert spider.context.counters["pending"] == 1


def response(status: int) -> HtmlResponse:
    request = Request("https://tienda.example/")
    return HtmlResponse(url=request.url, status=status, body=b"", request=request)


@pytest.mark.parametrize(("status", "reason"), [(401, "access_denied"), (403, "access_denied"), (429, "rate_limited")])
def test_the_run_stops_on_the_first_refusal(status, reason):
    spider = SimpleNamespace(context=SimpleNamespace(stop_reason=""), crawler=MagicMock())

    with pytest.raises(IgnoreRequest):
        StopOnAccessDeniedMiddleware().process_response(Request("https://tienda.example/"), response(status), spider)

    assert spider.context.stop_reason == reason
    spider.crawler.engine.close_spider.assert_called_once_with(spider, reason)


@pytest.mark.parametrize("status", [200, 404, 500])
def test_other_responses_pass_through_untouched(status):
    spider = SimpleNamespace(context=SimpleNamespace(stop_reason=""), crawler=MagicMock())
    page = response(status)

    assert StopOnAccessDeniedMiddleware().process_response(page.request, page, spider) is page
    spider.crawler.engine.close_spider.assert_not_called()
