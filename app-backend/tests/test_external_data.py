from datetime import datetime, timedelta, timezone

import pytest

from app.domain.exceptions import ExternalDataInvalidError
from app.domain.external_data import (
    Freshness,
    build_business_record,
    build_product_record,
    discount_percent,
    freshness,
    parse_cop_price,
)
from app.domain.places import PASTO_BOUNDS, BoundingBox, PlaceCategory

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
PASTO = BoundingBox(*PASTO_BOUNDS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$12.990", 12990),
        ("12,990", 12990),
        ("12.990,50", 12990),
        ("12990.00", 12990),
        ("COP 1.299.000", 1299000),
        (12990, 12990),
        (12990.4, 12990),
        ("  $ 8.500  ", 8500),
    ],
)
def test_common_colombian_price_formats_become_whole_pesos(raw, expected):
    assert parse_cop_price(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", None, 0, -5, True, "0", 10**10])
def test_values_that_are_not_a_plausible_price_are_rejected(raw):
    assert parse_cop_price(raw) is None


def test_the_discount_is_computed_from_the_published_reference_price():
    assert discount_percent(10000, 7500) == 25
    assert discount_percent(10000, 10000) == 0
    assert discount_percent(None, 7500) == 0
    assert discount_percent(7500, 10000) == 0


def test_data_is_fresh_only_inside_the_allowed_age():
    assert freshness(NOW - timedelta(hours=71), NOW) is Freshness.FRESH
    assert freshness(NOW - timedelta(hours=73), NOW) is Freshness.STALE
    assert freshness(NOW - timedelta(hours=5), NOW, max_age_hours=4) is Freshness.STALE


def business(**overrides):
    raw = {
        "name": "  Panadería   El Trigo ",
        "latitude": "1.2136",
        "longitude": "-77.2811",
        "address": "Calle 18 # 25-10",
        "website": "https://eltrigo.example",
        "external_id": "node/123",
        "phone": "+57 300 0000000",
        "opening_hours": "Mo-Sa 07:00-19:00",
        **overrides.pop("raw", {}),
    }
    return build_business_record(raw, "osm", NOW, PlaceCategory.BAKERY, overrides.get("area", PASTO))


def test_a_business_is_cleaned_and_keeps_its_origin():
    record = business()

    assert record.name == "Panadería El Trigo"
    assert (record.latitude, record.longitude) == (1.2136, -77.2811)
    assert record.source_key == "osm" and record.observed_at == NOW


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ({"name": "  "}, "missing_name"),
        ({"latitude": "north"}, "invalid_coordinates"),
        ({"latitude": "95"}, "invalid_coordinates"),
        ({"latitude": "4.7", "longitude": "-74.0"}, "outside_area"),
        ({"website": "javascript:alert(1)"}, "invalid_url"),
    ],
)
def test_an_unusable_business_is_rejected_with_a_reason(raw, reason):
    with pytest.raises(ExternalDataInvalidError) as error:
        business(raw=raw)

    assert str(error.value) == reason


def test_a_business_outside_any_area_is_accepted_when_no_area_is_set():
    assert business(raw={"latitude": "4.7", "longitude": "-74.0"}, area=None).latitude == 4.7


def product(**overrides):
    raw = {
        "name": "Pan tajado",
        "price": "$5.990",
        "original_price": "$7.990",
        "url": "https://tienda.example/pan-tajado",
        "category": "Panadería",
        "availability": "InStock",
        **overrides,
    }
    return build_product_record(raw, "demo-shop", NOW)


def test_a_promotion_is_recognized_from_the_two_published_prices():
    record = product()

    assert (record.price_cop, record.original_price_cop, record.discount_percent) == (5990, 7990, 25)
    assert record.is_promotion


def test_a_product_without_a_reference_price_is_not_a_promotion():
    assert not product(original_price=None).is_promotion


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"name": ""}, "missing_name"),
        ({"price": "gratis"}, "invalid_price"),
        ({"url": ""}, "invalid_url"),
        ({"url": "ftp://tienda.example/x"}, "invalid_url"),
    ],
)
def test_an_unusable_product_is_rejected_with_a_reason(overrides, reason):
    with pytest.raises(ExternalDataInvalidError) as error:
        product(**overrides)

    assert str(error.value) == reason
