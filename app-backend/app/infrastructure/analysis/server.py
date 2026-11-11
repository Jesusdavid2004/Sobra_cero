import hmac
import logging
import time
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.application.ports import RescueAnalyzer
from app.domain.exceptions import InvalidAnalysisRequestError
from app.infrastructure.analysis.generated import rescue_analysis_pb2 as pb
from app.infrastructure.analysis.generated import rescue_analysis_pb2_grpc as pb_grpc
from app.infrastructure.analysis.grpc_analyzer import (
    REQUEST_ID_METADATA,
    TOKEN_METADATA,
)
from app.infrastructure.analysis.grpc_mapping import (
    analysis_to_proto,
    snapshot_from_proto,
)

logger = logging.getLogger(__name__)
DEFAULT_MAX_WORKERS = 4
MILLISECONDS_PER_SECOND = 1000


class RescueAnalysisServicer(pb_grpc.RescueAnalysisServicer):
    def __init__(self, analyzer: RescueAnalyzer, token: str) -> None:
        if not token:
            raise ValueError("The analysis service requires a shared token")
        self._analyzer = analyzer
        self._token = token

    def AnalyzeLot(self, request: pb.AnalyzeLotRequest, context: grpc.ServicerContext) -> pb.LotAnalysis:
        return self._handle("AnalyzeLot", request.request_id, context, lambda: self._analyze_lot(request))

    def AnalyzeShop(self, request: pb.AnalyzeShopRequest, context: grpc.ServicerContext) -> pb.AnalyzeShopResponse:
        return self._handle("AnalyzeShop", request.request_id, context, lambda: self._analyze_shop(request))

    def _analyze_lot(self, request: pb.AnalyzeLotRequest) -> pb.LotAnalysis:
        lot = snapshot_from_proto(request.lot)
        return analysis_to_proto(self._analyzer.analyze_lot(request.request_id, lot))

    def _analyze_shop(self, request: pb.AnalyzeShopRequest) -> pb.AnalyzeShopResponse:
        lots = [snapshot_from_proto(message) for message in request.lots]
        results = self._analyzer.analyze_shop(request.request_id, lots)
        return pb.AnalyzeShopResponse(results=[analysis_to_proto(result) for result in results])

    def _handle(self, method, request_id, context, action):  # type: ignore[no-untyped-def]
        started_at = time.monotonic()
        metadata = dict(context.invocation_metadata())
        status = grpc.StatusCode.OK
        try:
            if not hmac.compare_digest(str(metadata.get(TOKEN_METADATA, "")), self._token):
                status = grpc.StatusCode.UNAUTHENTICATED
                context.abort(status, "Invalid credentials")
            context.set_trailing_metadata(((REQUEST_ID_METADATA, request_id),))
            return action()
        except InvalidAnalysisRequestError:
            status = grpc.StatusCode.INVALID_ARGUMENT
            context.abort(status, "Invalid analysis request")
        finally:
            logger.info(
                "Rescue analysis request handled",
                extra={
                    "method": method,
                    "request_id": request_id,
                    "grpc_status": status.name,
                    "latency_ms": int((time.monotonic() - started_at) * MILLISECONDS_PER_SECOND),
                },
            )


def build_server(analyzer: RescueAnalyzer, token: str, max_workers: int = DEFAULT_MAX_WORKERS) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb_grpc.add_RescueAnalysisServicer_to_server(RescueAnalysisServicer(analyzer, token), server)
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    return server
