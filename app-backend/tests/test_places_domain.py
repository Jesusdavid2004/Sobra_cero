from datetime import datetime, timezone

import pytest

from app.domain.exceptions import PlaceInvalidError
from app.domain.places import (
    PASTO_BOUNDS,
    PASTO_CENTER,
    Affiliation,
    BoundingBox,
    Place,
    PlaceCategory,
    are_duplicates,
    category_from_osm,
    name_similarity,
    normalize_name,
    validate_place_name,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def place(name: str, latitude: float = 1.2136, longitude: float = -77.2811) -> Place:
    return Place(
        place_id="ext:1",
        name=name,
        category=PlaceCategory.BAKERY,
        affiliation=Affiliation.DISCOVERED,
        latitude=latitude,
        longitude=longitude,
        address="",
        city="Pasto",
        website="",
        opening_hours="",
        source="openstreetmap",
        source_url="",
        last_seen_at=NOW,
        verified=False,
    )


def test_pasto_center_lies_inside_the_pasto_bounds():
    box = BoundingBox(*PASTO_BOUNDS)

    assert box.contains(*PASTO_CENTER)
    assert not box.contains(4.7, -74.0)


@pytest.mark.parametrize(
    "corners",
    [(1.3, -77.3, 1.2, -77.2), (1.1, -77.2, 1.2, -77.3), (-91, 0, 0, 1), (0, -181, 1, 0)],
)
def test_an_invalid_bounding_box_is_rejected(corners):
    with pytest.raises(PlaceInvalidError):
        BoundingBox(*corners)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"shop": "supermarket"}, PlaceCategory.SUPERMARKET),
        ({"shop": "bakery"}, PlaceCategory.BAKERY),
        ({"shop": "greengrocer"}, PlaceCategory.STORE),
        ({"amenity": "restaurant"}, PlaceCategory.RESTAURANT),
        ({"amenity": "fast_food"}, PlaceCategory.RESTAURANT),
        ({"amenity": "cafe"}, PlaceCategory.CAFE),
        ({"amenity": "marketplace"}, PlaceCategory.MARKET),
        ({"amenity": "bank"}, PlaceCategory.OTHER),
        ({}, PlaceCategory.OTHER),
    ],
)
def test_osm_tags_map_to_a_category(tags, expected):
    assert category_from_osm(tags) is expected


def test_names_are_normalized_without_accents_case_or_punctuation():
    assert normalize_name("  Panadería  «El Trigo» — Pasto! ") == "panaderia el trigo pasto"


def test_identical_names_are_fully_similar_and_unrelated_names_are_not():
    assert name_similarity("Panadería El Trigo", "panaderia el trigo") == 1.0
    assert name_similarity("Panadería El Trigo", "Restaurante La Plaza") < 0.3


def test_two_records_of_the_same_business_close_together_are_duplicates():
    assert are_duplicates(place("Panadería El Trigo"), place("Panaderia El Trigo", latitude=1.21365))


def test_the_same_name_far_apart_is_a_different_business():
    assert not are_duplicates(place("Panadería El Trigo"), place("Panadería El Trigo", latitude=1.25))


def test_different_names_at_the_same_point_are_different_businesses():
    assert not are_duplicates(place("Panadería El Trigo"), place("Restaurante La Plaza"))


def test_a_place_name_is_trimmed_and_must_not_be_empty_or_huge():
    assert validate_place_name("  Café   Central ") == "Café Central"
    with pytest.raises(PlaceInvalidError):
        validate_place_name("   ")
    with pytest.raises(PlaceInvalidError):
        validate_place_name("x" * 161)
