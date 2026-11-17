"""Where the map shows activity worth looking at, using only counts of verifiable records.

A cell reports how many affiliated shops, live offers, receivers and discovered businesses it
holds. Nothing here estimates waste from a location or a price; a cell with many discovered
businesses and no affiliated shop is a place to invite, not evidence of surplus.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from math import floor

CELL_DEGREES = 0.01
MAX_CELLS = 100


class Signal(StrEnum):
    AFFILIATED_SHOP = "affiliated_shop"
    LIVE_OFFER = "live_offer"
    RECEIVER = "receiver"
    DISCOVERED_BUSINESS = "discovered_business"


@dataclass(frozen=True)
class SignalPoint:
    latitude: float
    longitude: float
    signal: Signal
    count: int = 1


@dataclass(frozen=True)
class Cell:
    south: float
    west: float
    affiliated_shops: int
    live_offers: int
    receivers: int
    discovered_businesses: int

    @property
    def center(self) -> tuple[float, float]:
        return round(self.south + CELL_DEGREES / 2, 6), round(self.west + CELL_DEGREES / 2, 6)

    @property
    def total(self) -> int:
        return self.affiliated_shops + self.live_offers + self.receivers + self.discovered_businesses

    @property
    def has_unserved_businesses(self) -> bool:
        """Discovered businesses with no affiliated shop and no offer: somewhere to invite."""
        return self.discovered_businesses > 0 and self.affiliated_shops == 0 and self.live_offers == 0


def _origin(value: float) -> float:
    return round(floor(value / CELL_DEGREES) * CELL_DEGREES, 6)


def aggregate(points: list[SignalPoint], max_cells: int = MAX_CELLS) -> list[Cell]:
    """Group points into grid cells and return the busiest cells first."""
    totals: dict[tuple[float, float], dict[Signal, int]] = defaultdict(lambda: defaultdict(int))
    for point in points:
        totals[(_origin(point.latitude), _origin(point.longitude))][point.signal] += point.count
    cells = [
        Cell(
            south=south,
            west=west,
            affiliated_shops=counts[Signal.AFFILIATED_SHOP],
            live_offers=counts[Signal.LIVE_OFFER],
            receivers=counts[Signal.RECEIVER],
            discovered_businesses=counts[Signal.DISCOVERED_BUSINESS],
        )
        for (south, west), counts in totals.items()
    ]
    return sorted(cells, key=lambda cell: (-cell.total, cell.south, cell.west))[:max_cells]
