import logging
import time
from typing import Sequence

import grpc

from app.application.dto import ANALYSIS_SOURCE_GRPC, LotAnalysis, LotAnalysisInput
from app.application.ports import RescueAnalyzer
from app.domain.exceptions import AnalysisFailedError, AnalysisUnavailableError
from app.infrastructure.analysis.generated import rescue_analysis_pb2 as pb
from app.infrastructure.analysis.generated import rescue_analysis_pb2_grpc as pb_grpc
from app.infrastructure.analysis.grpc_mapping import (
    analysis_from_proto,
    snapshot_to_proto,
)

logger = logging.getLogger(__name__)
REQUEST_ID_METADATA = "x-request-id"
TOKEN_METADATA = "x-analysis-token"
MILLISECONDS_PER_SECOND = 1000
UNAVAILABLE_CODES = {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}


class GrpcRescueAnalyzer(RescueAnalyzer):
    def __init__(self, channel: grpc.Channel, token: str, timeout_seconds: float) -> None:
        self._stub = pb_grpc.RescueAnalysisStub(channel)
        self._token = token
        self._timeout_seconds = timeout_seconds

    def analyze_lot(self, request_id: str, lot: LotAnalysisInput) -> LotAnalysis:
        request = pb.AnalyzeLotRequest(request_id=request_id, lot=snapshot_to_proto(lot))
        response = self._call("AnalyzeLot", self._stub.AnalyzeLot, request, request_id)
        return self._convert(response)

    def analyze_shop(self, request_id: str, lots: Sequence[LotAnalysisInput]) -> list[LotAnalysis]:
        request = pb.AnalyzeShopRequest(request_id=request_id, lots=[snapshot_to_proto(lot) for lot in lots])
        response = self._call("AnalyzeShop", self._stub.AnalyzeShop, request, request_id)
        return [self._convert(result) for result in response.results]

    def _call(self, method: str, rpc, request, request_id: str):  # type: ignore[no-untyped-def]
        started_at = time.monotonic()
        status = grpc.StatusCode.OK
        try:
            return rpc(
                request,
                timeout=self._timeout_seconds,
                metadata=((REQUEST_ID_METADATA, request_id), (TOKEN_METADATA, self._token)),
            )
        except grpc.RpcError as exc:
            status = exc.code()
            if status in UNAVAILABLE_CODES:
                raise AnalysisUnavailableError("Analysis service is unavailable") from exc
            raise AnalysisFailedError("Analysis service rejected the request") from exc
        finally:
            logger.info(
                "Rescue analysis call finished",
                extra={
                    "method": method,
                    "request_id": request_id,
                    "grpc_status": status.name,
                    "latency_ms": int((time.monotonic() - started_at) * MILLISECONDS_PER_SECOND),
                },
            )

    @staticmethod
    def _convert(message: pb.LotAnalysis) -> LotAnalysis:
        try:
            return analysis_from_proto(message, ANALYSIS_SOURCE_GRPC)
        except ValueError as exc:
            raise AnalysisFailedError("Analysis service returned an invalid response") from exc


def create_grpc_analyzer(target: str, token: str, timeout_seconds: float) -> GrpcRescueAnalyzer:
    return GrpcRescueAnalyzer(grpc.insecure_channel(target), token, timeout_seconds)
