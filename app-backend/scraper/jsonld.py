"""Read schema.org Product data that a page publishes for machines (JSON-LD).

Only what the page declares is used. A reference price counts only when the page marks it as a
list price; a lower price next to a higher "high price" is not treated as a discount.
"""

import json
from collections.abc import Iterator
from typing import Any

COP = "COP"
LIST_PRICE_TYPES = ("listprice", "srp")


def parse_blocks(blocks: list[str]) -> list[Any]:
    documents: list[Any] = []
    for block in blocks:
        try:
            documents.append(json.loads(block))
        except ValueError:
            continue
    return documents


def _types(node: dict[str, Any]) -> set[str]:
    declared = node.get("@type", [])
    return {str(item).lower() for item in (declared if isinstance(declared, list) else [declared])}


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, list):
        for child in node:
            yield from _walk(child)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item"):
            if key in node:
                yield from _walk(node[key])


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value] if value else []


def _list_price(offer: dict[str, Any]) -> Any:
    for spec in _as_list(offer.get("priceSpecification")):
        kind = str(spec.get("priceType", "")).rsplit("/", 1)[-1].lower() if isinstance(spec, dict) else ""
        if kind in LIST_PRICE_TYPES:
            return spec.get("price")
    return None


def _offer_fields(offers: Any) -> tuple[Any, Any, str]:
    for offer in _as_list(offers):
        if not isinstance(offer, dict):
            continue
        currency = str(offer.get("priceCurrency", COP)).upper()
        price = offer.get("price", offer.get("lowPrice"))
        availability = str(offer.get("availability", "")).rsplit("/", 1)[-1]
        return (price if currency == COP else None), _list_price(offer), availability
    return None, None, ""


def extract_products(documents: list[Any], page_url: str) -> Iterator[dict[str, Any]]:
    for node in (n for document in documents for n in _walk(document)):
        if "product" not in _types(node):
            continue
        price, original, availability = _offer_fields(node.get("offers"))
        category = node.get("category", "")
        yield {
            "name": node.get("name", ""),
            "category": category if isinstance(category, str) else "",
            "price": price,
            "original_price": original,
            "url": node.get("url") or page_url,
            "availability": availability,
            "shop_name": str((node.get("brand") or {}).get("name", "")) if isinstance(node.get("brand"), dict) else "",
        }
