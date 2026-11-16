import json
from pathlib import Path

from app.domain.places import PASTO_BOUNDS, BoundingBox
from scraper.spiders.overpass import build_overpass_query, business_items

FIXTURE = Path(__file__).parent / "fixtures" / "overpass_pasto.json"


def items() -> list:
    return list(business_items(json.loads(FIXTURE.read_text(encoding="utf-8"))))


def test_the_query_is_bounded_to_the_area_and_asks_only_for_businesses():
    query = build_overpass_query(BoundingBox(*PASTO_BOUNDS))

    assert "(1.15,-77.35,1.28,-77.22)" in query
    assert "[out:json]" in query and "out center tags" in query
    assert "supermarket|bakery" in query and "restaurant|cafe" in query


def test_every_element_becomes_an_item_with_its_osm_identity():
    found = items()

    assert [item["external_id"] for item in found] == ["node/1001", "way/2002", "node/3003", "node/4004", "node/5005"]
    assert found[0]["source_url"] == "https://www.openstreetmap.org/node/1001"


def test_a_node_uses_its_position_and_a_way_uses_its_center():
    found = items()

    assert (found[0]["latitude"], found[0]["longitude"]) == (1.2136, -77.2811)
    assert (found[1]["latitude"], found[1]["longitude"]) == (1.2150, -77.2790)


def test_tags_are_mapped_to_categories_and_fields():
    bakery, restaurant, _supermarket, _far, cafe = items()

    assert (bakery["category"], restaurant["category"], cafe["category"]) == ("bakery", "restaurant", "cafe")
    assert bakery["address"] == "Calle 18 25-10"
    assert bakery["opening_hours"] == "Mo-Sa 07:00-19:00"
    assert restaurant["website"] == "https://laplaza.example"


def test_an_element_without_a_name_keeps_an_empty_name_so_validation_can_reject_it():
    assert items()[2]["name"] == ""
