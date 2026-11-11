from app.domain.discovery import RankingMethod
from app.domain.discovery_evaluation import evaluate


def rate(report, method: RankingMethod) -> float:
    return next(item.collectable_rate for item in report.results if item.method is method)


def test_the_evaluation_is_reproducible_for_the_same_seed():
    assert evaluate(seed=7, searches=200) == evaluate(seed=7, searches=200)


def test_the_feasibility_method_always_proposes_a_collectable_lot_when_one_exists():
    report = evaluate(searches=300)

    assert rate(report, RankingMethod.FEASIBILITY) == 1.0


def test_the_distance_baseline_sometimes_proposes_a_lot_that_cannot_be_collected():
    report = evaluate(searches=300)

    assert 0.0 < rate(report, RankingMethod.DISTANCE_ONLY) < 1.0


def test_only_searches_with_a_collectable_lot_are_compared():
    report = evaluate(searches=300)

    assert 0 < report.searches_with_a_collectable_lot <= report.searches
    assert all(item.searches_answered == report.searches_with_a_collectable_lot for item in report.results)
