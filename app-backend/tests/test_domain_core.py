from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.entities import Batch, BatchStatus, OfferType
from app.domain.exceptions import (
    BatchExpiredError,
    BatchNotReservableError,
    DiscountPercentValidationError,
    InsufficientStockError,
    InvalidMoneyError,
)
from app.domain.value_objects import DiscountPercent, Money


def active_batch(
    *,
    available_quantity: int = 3,
    expires_in: timedelta = timedelta(hours=1),
    offer_type: OfferType = OfferType.SALE,
) -> Batch:
    now = datetime.now(timezone.utc)
    return Batch(
        id=1,
        quantity=3,
        available_quantity=available_quantity,
        expiration_date=now + expires_in,
        original_price=Money(Decimal("12.50"), "USD"),
        discount_percent=DiscountPercent(20),
        status=BatchStatus.ACTIVE,
        offer_type=offer_type,
    )


def test_discount_percent_allows_the_domain_maximum() -> None:
    assert DiscountPercent(90).value == 90


def test_money_rejects_negative_amounts_and_invalid_currencies() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("-0.01"), "USD")
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("1.00"), "usd")


@pytest.mark.parametrize("value", [-1, 91])
def test_discount_percent_rejects_values_outside_domain_range(value: int) -> None:
    with pytest.raises(DiscountPercentValidationError):
        DiscountPercent(value)


def test_batch_reservation_reduces_stock_and_marks_batch_sold_out() -> None:
    batch = active_batch()
    now = datetime.now(timezone.utc)

    batch.reserve(2, now)
    assert batch.available_quantity == 1
    assert batch.status is BatchStatus.ACTIVE

    batch.reserve(1, now)
    assert batch.available_quantity == 0
    assert batch.status is BatchStatus.SOLD_OUT
    assert not batch.is_reservable(now)


def test_batch_reservation_rejects_insufficient_stock() -> None:
    batch = active_batch()

    with pytest.raises(InsufficientStockError):
        batch.reserve(4, datetime.now(timezone.utc))


def test_donation_only_batch_is_not_reservable() -> None:
    batch = active_batch(offer_type=OfferType.DONATION)

    assert not batch.is_reservable(datetime.now(timezone.utc))
    with pytest.raises(BatchNotReservableError):
        batch.reserve(1, datetime.now(timezone.utc))


def test_batch_reservation_rejects_expired_batches() -> None:
    batch = active_batch(expires_in=timedelta(seconds=-1))

    with pytest.raises(BatchExpiredError):
        batch.reserve(1, datetime.now(timezone.utc))


def test_batch_expiration_changes_active_status() -> None:
    batch = active_batch(expires_in=timedelta(seconds=-1))

    assert batch.expire_if_due(datetime.now(timezone.utc))
    assert batch.status is BatchStatus.EXPIRED


def test_batch_discount_rejects_terminal_status() -> None:
    batch = active_batch()
    batch.status = BatchStatus.SOLD_OUT

    with pytest.raises(BatchNotReservableError):
        batch.apply_discount(DiscountPercent(30))
