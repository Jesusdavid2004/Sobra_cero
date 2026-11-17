from dataclasses import dataclass
from datetime import datetime

from app.application.ports import DiscoveryLotSource
from app.domain.discovery import (
    DiscoveryQuery,
    LotAssessment,
    RankingMethod,
    assess_lot,
    rank,
)
from app.domain.rules import MAX_DISCOVERY_RESULTS


@dataclass(frozen=True)
class DiscoveryResult:
    feasible: tuple[LotAssessment, ...]
    excluded: tuple[LotAssessment, ...]
    nearest_unreachable: LotAssessment | None


class DiscoverLots:
    """Split open lots into those the customer can collect in time and those they cannot, with reasons."""

    def __init__(self, source: DiscoveryLotSource) -> None:
        self._source = source

    def execute(self, query: DiscoveryQuery, now: datetime) -> DiscoveryResult:
        assessments = [assess_lot(candidate, query, now) for candidate in self._source.open_candidates(now)]
        feasible = rank(assessments, RankingMethod.FEASIBILITY)
        excluded = [item for item in rank(assessments, RankingMethod.DISTANCE_ONLY) if not item.feasible]
        nearest = rank(assessments, RankingMethod.DISTANCE_ONLY)[:1]
        nearest_unreachable = nearest[0] if nearest and not nearest[0].feasible else None
        return DiscoveryResult(
            feasible=tuple(feasible[:MAX_DISCOVERY_RESULTS]),
            excluded=tuple(excluded[:MAX_DISCOVERY_RESULTS]),
            nearest_unreachable=nearest_unreachable,
        )
