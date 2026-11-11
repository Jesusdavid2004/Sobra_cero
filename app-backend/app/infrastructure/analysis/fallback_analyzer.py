import logging
from dataclasses import replace
from typing import Sequence

from app.application.dto import (
    ANALYSIS_SOURCE_LOCAL_FALLBACK,
    LotAnalysis,
    LotAnalysisInput,
)
from app.application.ports import RescueAnalyzer
from app.domain.exceptions import AnalysisUnavailableError

logger = logging.getLogger(__name__)


class FallbackRescueAnalyzer(RescueAnalyzer):
    """Use the remote analyzer; if it is unreachable, answer locally and say so."""

    def __init__(self, primary: RescueAnalyzer, fallback: RescueAnalyzer) -> None:
        self._primary = primary
        self._fallback = fallback

    def analyze_lot(self, request_id: str, lot: LotAnalysisInput) -> LotAnalysis:
        try:
            return self._primary.analyze_lot(request_id, lot)
        except AnalysisUnavailableError:
            logger.warning("Analysis service unavailable, using local analyzer", extra={"request_id": request_id})
            return replace(self._fallback.analyze_lot(request_id, lot), source=ANALYSIS_SOURCE_LOCAL_FALLBACK)

    def analyze_shop(self, request_id: str, lots: Sequence[LotAnalysisInput]) -> list[LotAnalysis]:
        try:
            return self._primary.analyze_shop(request_id, lots)
        except AnalysisUnavailableError:
            logger.warning("Analysis service unavailable, using local analyzer", extra={"request_id": request_id})
            return [
                replace(analysis, source=ANALYSIS_SOURCE_LOCAL_FALLBACK)
                for analysis in self._fallback.analyze_shop(request_id, lots)
            ]
