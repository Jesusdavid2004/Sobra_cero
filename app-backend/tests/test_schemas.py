from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas import LotCreate


def lot_data(discount_percent: int) -> dict[str, object]:
    return {
        "shop_id": 1,
        "product_id": 1,
        "title": "Surplus box",
        "quantity": 1,
        "original_price_cents": 1000,
        "discount_percent": discount_percent,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    }


def test_lot_schema_uses_the_domain_discount_limit() -> None:
    assert LotCreate(**lot_data(90)).discount_percent == 90

    with pytest.raises(ValidationError):
        LotCreate(**lot_data(91))
