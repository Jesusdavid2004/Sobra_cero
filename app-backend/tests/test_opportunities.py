from app.domain.opportunities import CELL_DEGREES, Signal, SignalPoint, aggregate


def point(latitude: float, longitude: float, signal: Signal, count: int = 1) -> SignalPoint:
    return SignalPoint(latitude, longitude, signal, count)


def test_points_in_the_same_cell_are_counted_together_by_signal():
    cells = aggregate(
        [
            point(1.2136, -77.2811, Signal.AFFILIATED_SHOP),
            point(1.2140, -77.2805, Signal.LIVE_OFFER, count=3),
            point(1.2149, -77.2801, Signal.DISCOVERED_BUSINESS),
            point(1.2149, -77.2801, Signal.RECEIVER),
        ]
    )

    assert len(cells) == 1
    cell = cells[0]
    assert (cell.affiliated_shops, cell.live_offers, cell.discovered_businesses, cell.receivers) == (1, 3, 1, 1)
    assert cell.total == 6


def test_points_in_different_cells_stay_apart_and_the_busiest_cell_comes_first():
    cells = aggregate(
        [
            point(1.2136, -77.2811, Signal.DISCOVERED_BUSINESS),
            point(1.2300, -77.2450, Signal.DISCOVERED_BUSINESS),
            point(1.2301, -77.2449, Signal.DISCOVERED_BUSINESS),
        ]
    )

    assert [cell.total for cell in cells] == [2, 1]


def test_a_cell_is_aligned_to_the_grid_and_reports_its_center():
    [cell] = aggregate([point(1.2136, -77.2811, Signal.AFFILIATED_SHOP)])

    assert cell.south == 1.21 and cell.west == -77.29
    assert cell.center == (1.215, -77.285)
    assert CELL_DEGREES == 0.01


def test_a_cell_of_discovered_businesses_without_shops_or_offers_is_flagged_as_somewhere_to_invite():
    [uncovered] = aggregate([point(1.2136, -77.2811, Signal.DISCOVERED_BUSINESS)])
    [covered] = aggregate(
        [point(1.2136, -77.2811, Signal.DISCOVERED_BUSINESS), point(1.2136, -77.2811, Signal.AFFILIATED_SHOP)]
    )

    assert uncovered.has_unserved_businesses
    assert not covered.has_unserved_businesses


def test_the_number_of_cells_is_capped():
    points = [point(1.0 + index * 0.01, -77.0, Signal.DISCOVERED_BUSINESS) for index in range(30)]

    assert len(aggregate(points, max_cells=10)) == 10
