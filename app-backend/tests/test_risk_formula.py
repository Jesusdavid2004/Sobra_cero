import pytest

from app.domain.exceptions import InvalidBatchQuantityError
from app.domain.services.waste_risk import calculate_waste_risk


def test_risk_formula_sums_forecasts_and_calculates_units_and_score() -> None:
    assessment = calculate_waste_risk(10, [2.0, 3.0, 1.0])

    assert assessment.expected_sales == 6.0
    assert assessment.units_at_risk == 4.0
    assert assessment.risk_score.value == 40


def test_risk_formula_caps_risk_at_full_stock_when_forecasts_are_zero() -> None:
    assessment = calculate_waste_risk(10, [0.0, 0.0])

    assert assessment.units_at_risk == 10.0
    assert assessment.risk_score.value == 100


def test_risk_formula_has_no_at_risk_units_when_forecasts_exceed_stock() -> None:
    assessment = calculate_waste_risk(10, [8.0, 7.0])

    assert assessment.expected_sales == 15.0
    assert assessment.units_at_risk == 0.0
    assert assessment.risk_score.value == 0


@pytest.mark.parametrize("quantity", [0, -1])
def test_risk_formula_rejects_non_positive_stock(quantity: int) -> None:
    with pytest.raises(InvalidBatchQuantityError):
        calculate_waste_risk(quantity, [1.0])
