import json

from scraper.jsonld import extract_products, parse_blocks

PAGE = "https://tienda.example/categoria/pan"


def products(*documents) -> list[dict]:
    return list(extract_products(list(documents), PAGE))


def test_a_product_with_one_offer_is_read():
    [item] = products(
        {
            "@type": "Product",
            "name": "Pan tajado",
            "category": "Panadería",
            "url": "https://tienda.example/pan",
            "offers": {
                "@type": "Offer",
                "price": "5990",
                "priceCurrency": "COP",
                "availability": "https://schema.org/InStock",
            },
        }
    )

    assert (item["name"], item["price"], item["availability"]) == ("Pan tajado", "5990", "InStock")
    assert item["original_price"] is None


def test_a_reference_price_counts_only_when_the_page_marks_it_as_a_list_price():
    offer = {
        "price": "4990",
        "priceCurrency": "COP",
        "priceSpecification": [{"priceType": "https://schema.org/ListPrice", "price": "6990"}],
    }

    [item] = products({"@type": "Product", "name": "Leche", "offers": offer})

    assert (item["price"], item["original_price"]) == ("4990", "6990")


def test_a_high_price_without_a_list_price_is_not_taken_as_a_discount():
    offer = {"@type": "AggregateOffer", "lowPrice": "4990", "highPrice": "6990", "priceCurrency": "COP"}

    [item] = products({"@type": "Product", "name": "Leche", "offers": offer})

    assert (item["price"], item["original_price"]) == ("4990", None)


def test_a_price_in_another_currency_is_not_read_as_pesos():
    [item] = products({"@type": "Product", "name": "Import", "offers": {"price": "9.99", "priceCurrency": "USD"}})

    assert item["price"] is None


def test_products_inside_a_graph_and_an_item_list_are_found():
    graph = {"@graph": [{"@type": "WebPage"}, {"@type": "Product", "name": "A", "offers": {"price": "1000"}}]}
    listing = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "item": {"@type": "Product", "name": "B", "offers": {"price": "2000"}}},
            {"@type": ["Thing", "Product"], "name": "C", "offers": [{"price": "3000"}]},
        ],
    }

    assert [item["name"] for item in products(graph, listing)] == ["A", "B", "C"]


def test_nodes_that_are_not_products_are_ignored_and_the_page_url_is_the_fallback():
    assert products({"@type": "Organization", "name": "Tienda"}) == []
    [item] = products({"@type": "Product", "name": "Sin url", "offers": {"price": "1000"}})
    assert item["url"] == PAGE


def test_unparseable_blocks_are_skipped():
    documents = parse_blocks(["{not json", json.dumps({"@type": "Product", "name": "X"})])

    assert len(documents) == 1
