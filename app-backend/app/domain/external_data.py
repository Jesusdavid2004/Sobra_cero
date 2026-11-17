"""Normalization and validation of records collected from external sources.

A record here is something a source published: a business, or a product with a price. It says
nothing about stock, expiry or surplus, and nothing here turns it into an offer.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse

from app.domain.exceptions import ExternalDataInvalidError
from app.domain.places import BoundingBox, PlaceCategory, validate_place_name

MAX_PRICE_COP = 1_000_000_000
THOUSANDS_GROUP_DIGITS = 3
PERCENT = 100
MAX_TEXT_CHARS = 500
MAX_URL_CHARS = 500
DEFAULT_MAX_AGE_HOURS = 72
NON_PRICE_CHARACTERS = re.compile(r"[^\d.,]")


class RejectionReason(StrEnum):
    MISSING_NAME = "missing_name"
    INVALID_COORDINATES = "invalid_coordinates"
    OUTSIDE_AREA = "outside_area"
    INVALID_PRICE = "invalid_price"
    INVALID_URL = "invalid_url"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True)
class ExternalBusinessRecord:
    source_key: str
    external_id: str
    name: str
    category: PlaceCategory
    latitude: float
    longitude: float
    address: str
    city: str
    website: str
    phone: str
    opening_hours: str
    source_url: str
    observed_at: datetime


@dataclass(frozen=True)
class ExternalProductRecord:
    source_key: str
    name: str
    category: str
    url: str
    price_cop: int
    original_price_cop: int | None
    discount_percent: int
    availability: str
    shop_name: str
    observed_at: datetime

    @property
    def is_promotion(self) -> bool:
        return self.discount_percent > 0


def parse_cop_price(raw: object) -> int | None:
    """Read a Colombian peso amount in the common formats and return whole pesos, or None."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return _within_range(round(raw))
    digits = NON_PRICE_CHARACTERS.sub("", str(raw))
    if not digits:
        return None
    return _within_range(round(_to_number(digits)))


def _to_number(digits: str) -> float:
    has_dot, has_comma = "." in digits, "," in digits
    if has_dot and has_comma:
        decimal = "." if digits.rfind(".") > digits.rfind(",") else ","
    elif has_dot or has_comma:
        separator = "." if has_dot else ","
        parts = digits.split(separator)
        is_thousands = len(parts) > 2 or len(parts[-1]) == THOUSANDS_GROUP_DIGITS
        decimal = "" if is_thousands else separator
    else:
        decimal = ""
    integer_part, _, fraction = digits.rpartition(decimal) if decimal else (digits, "", "")
    cleaned = re.sub(r"[.,]", "", integer_part)
    try:
        return float(f"{cleaned}.{fraction}" if fraction else cleaned)
    except ValueError:
        return 0.0


def _within_range(value: int) -> int | None:
    return value if 0 < value <= MAX_PRICE_COP else None


def discount_percent(original_cop: int | None, current_cop: int) -> int:
    """Whole-number discount shown by the source; zero when there is no valid reference price."""
    if original_cop is None or original_cop <= 0 or current_cop <= 0 or current_cop >= original_cop:
        return 0
    return round((1 - current_cop / original_cop) * PERCENT)


def freshness(observed_at: datetime, now: datetime, max_age_hours: int = DEFAULT_MAX_AGE_HOURS) -> Freshness:
    return Freshness.FRESH if now - observed_at <= timedelta(hours=max_age_hours) else Freshness.STALE


def _text(value: object, limit: int = MAX_TEXT_CHARS) -> str:
    return " ".join(str(value or "").split())[:limit]


def _web_url(value: object, required: bool = False) -> str:
    candidate = _text(value, MAX_URL_CHARS)
    if not candidate:
        if required:
            raise ExternalDataInvalidError(RejectionReason.INVALID_URL.value)
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ExternalDataInvalidError(RejectionReason.INVALID_URL.value)
    return candidate


def build_business_record(
    raw: Mapping[str, object],
    source_key: str,
    observed_at: datetime,
    category: PlaceCategory,
    area: BoundingBox | None,
) -> ExternalBusinessRecord:
    try:
        name = validate_place_name(str(raw.get("name") or ""))
    except Exception as exc:
        raise ExternalDataInvalidError(RejectionReason.MISSING_NAME.value) from exc
    try:
        latitude, longitude = float(raw["latitude"]), float(raw["longitude"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        raise ExternalDataInvalidError(RejectionReason.INVALID_COORDINATES.value) from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ExternalDataInvalidError(RejectionReason.INVALID_COORDINATES.value)
    if area is not None and not area.contains(latitude, longitude):
        raise ExternalDataInvalidError(RejectionReason.OUTSIDE_AREA.value)
    return ExternalBusinessRecord(
        source_key=source_key,
        external_id=_text(raw.get("external_id"), 80),
        name=name,
        category=category,
        latitude=latitude,
        longitude=longitude,
        address=_text(raw.get("address")),
        city=_text(raw.get("city"), 80),
        website=_web_url(raw.get("website")),
        phone=_text(raw.get("phone"), 40),
        opening_hours=_text(raw.get("opening_hours"), 200),
        source_url=_web_url(raw.get("source_url")),
        observed_at=observed_at,
    )


def build_product_record(raw: Mapping[str, object], source_key: str, observed_at: datetime) -> ExternalProductRecord:
    name = _text(raw.get("name"), 200)
    if not name:
        raise ExternalDataInvalidError(RejectionReason.MISSING_NAME.value)
    price = parse_cop_price(raw.get("price"))
    if price is None:
        raise ExternalDataInvalidError(RejectionReason.INVALID_PRICE.value)
    original = parse_cop_price(raw.get("original_price"))
    return ExternalProductRecord(
        source_key=source_key,
        name=name,
        category=_text(raw.get("category"), 120),
        url=_web_url(raw.get("url"), required=True),
        price_cop=price,
        original_price_cop=original,
        discount_percent=discount_percent(original, price),
        availability=_text(raw.get("availability"), 80),
        shop_name=_text(raw.get("shop_name"), 160),
        observed_at=observed_at,
    )
