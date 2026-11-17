import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import date, timedelta

import grpc
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.dependencies as dependencies
import app.main as main
from app.application.dto import (
    ANALYSIS_SOURCE_GRPC,
    ANALYSIS_SOURCE_LOCAL,
    ANALYSIS_SOURCE_LOCAL_FALLBACK,
    DailySales,
    LotAnalysisInput,
    SalesForecastModelArtifact,
)
from app.config import Settings, settings
from app.db import SessionLocal
from app.domain.exceptions import AnalysisFailedError, AnalysisUnavailableError
from app.infrastructure.analysis.fallback_analyzer import FallbackRescueAnalyzer
from app.infrastructure.analysis.generated import rescue_analysis_pb2 as pb
from app.infrastructure.analysis.generated import rescue_analysis_pb2_grpc as pb_grpc
from app.infrastructure.analysis.grpc_analyzer import GrpcRescueAnalyzer
from app.infrastructure.analysis.grpc_mapping import snapshot_to_proto
from app.infrastructure.analysis.local_analyzer import LocalRescueAnalyzer
from app.infrastructure.analysis.server import build_server
from app.models import RescuePlanEventRecord
from tests.test_rescue_plan import auth_headers, reset_db, seed_lot

TOKEN = "test-shared-token"
TODAY = date(2026, 11, 10)


def make_input(lot_ref: str = "1", quantity: int = 20, hours: float = 48, days: int = 30, model=None):
    return LotAnalysisInput(
        lot_ref=lot_ref,
        available_quantity=quantity,
        current_discount_percent=20,
        horizon_hours=hours,
        as_of_date=TODAY,
        history=[DailySales(TODAY - timedelta(days=i + 1), 3 + i % 2, i % 5 == 0) for i in range(days)],
        model=model,
    )


class SlowAnalyzer(LocalRescueAnalyzer):
    def analyze_lot(self, request_id, lot):
        time.sleep(0.5)
        return super().analyze_lot(request_id, lot)


def start_server(analyzer=None):
    server = build_server(analyzer or LocalRescueAnalyzer(), TOKEN)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    return server, port


@pytest.fixture
def running_server() -> Iterator[int]:
    server, port = start_server()
    yield port
    server.stop(grace=None)


def client_for(port: int, token: str = TOKEN, timeout: float = 2.0) -> GrpcRescueAnalyzer:
    return GrpcRescueAnalyzer(grpc.insecure_channel(f"127.0.0.1:{port}"), token, timeout)


def comparable(analysis):
    return replace(analysis, source="")


def test_grpc_result_matches_the_local_analyzer(running_server):
    lot = make_input()

    remote = client_for(running_server).analyze_lot("req-1", lot)
    local = LocalRescueAnalyzer().analyze_lot("req-1", lot)

    assert remote.source == ANALYSIS_SOURCE_GRPC
    assert local.source == ANALYSIS_SOURCE_LOCAL
    assert comparable(remote) == comparable(local)


def test_trained_weekday_model_travels_over_the_wire(running_server):
    model = SalesForecastModelArtifact("weekday-test-v1", (1.2, 1.0, 0.9, 1.1, 1.3, 0.8, 0.7), TODAY)
    lot = make_input(model=model)

    remote = client_for(running_server).analyze_lot("req-2", lot)

    assert remote.model_version == "weekday-test-v1"
    assert comparable(remote) == comparable(LocalRescueAnalyzer().analyze_lot("req-2", lot))


def test_shop_analysis_is_ranked_by_surplus_ratio_and_matches_local(running_server):
    lots = [make_input("covered", quantity=5), make_input("surplus", quantity=60), make_input("mid", quantity=9)]

    remote = client_for(running_server).analyze_shop("req-3", lots)
    local = LocalRescueAnalyzer().analyze_shop("req-3", lots)

    assert [item.lot_ref for item in remote] == [item.lot_ref for item in local]
    assert remote[0].lot_ref == "surplus"
    assert [comparable(item) for item in remote] == [comparable(item) for item in local]


def test_wrong_token_is_rejected_without_fallback(running_server):
    analyzer = FallbackRescueAnalyzer(client_for(running_server, token="wrong"), LocalRescueAnalyzer())

    with pytest.raises(AnalysisFailedError):
        analyzer.analyze_lot("req-4", make_input())


def test_server_enforces_authentication_and_semantic_limits(running_server):
    stub = pb_grpc.RescueAnalysisStub(grpc.insecure_channel(f"127.0.0.1:{running_server}"))
    valid = pb.AnalyzeLotRequest(request_id="req-5", lot=snapshot_to_proto(make_input()))

    with pytest.raises(grpc.RpcError) as missing_token:
        stub.AnalyzeLot(valid)
    assert missing_token.value.code() is grpc.StatusCode.UNAUTHENTICATED

    short_history = pb.AnalyzeLotRequest(request_id="req-5", lot=snapshot_to_proto(make_input(days=3)))
    with pytest.raises(grpc.RpcError) as invalid:
        stub.AnalyzeLot(short_history, metadata=(("x-analysis-token", TOKEN),))
    assert invalid.value.code() is grpc.StatusCode.INVALID_ARGUMENT
    assert invalid.value.details() == "Invalid analysis request"

    too_many = pb.AnalyzeShopRequest(
        request_id="req-5", lots=[snapshot_to_proto(make_input(str(i))) for i in range(51)]
    )
    with pytest.raises(grpc.RpcError) as limit:
        stub.AnalyzeShop(too_many, metadata=(("x-analysis-token", TOKEN),))
    assert limit.value.code() is grpc.StatusCode.INVALID_ARGUMENT

    bad_date = snapshot_to_proto(make_input())
    bad_date.as_of_date = "not-a-date"
    with pytest.raises(grpc.RpcError) as malformed:
        stub.AnalyzeLot(pb.AnalyzeLotRequest(request_id="req-5", lot=bad_date), metadata=(("x-analysis-token", TOKEN),))
    assert malformed.value.code() is grpc.StatusCode.INVALID_ARGUMENT


def test_request_id_round_trips_in_trailing_metadata(running_server):
    stub = pb_grpc.RescueAnalysisStub(grpc.insecure_channel(f"127.0.0.1:{running_server}"))
    request = pb.AnalyzeLotRequest(request_id="trace-42", lot=snapshot_to_proto(make_input()))

    _response, call = stub.AnalyzeLot.with_call(request, metadata=(("x-analysis-token", TOKEN),))

    assert dict(call.trailing_metadata())["x-request-id"] == "trace-42"


def test_stopped_server_is_unavailable_and_falls_back_with_an_identified_source():
    server, port = start_server()
    server.stop(grace=None).wait()
    remote = client_for(port, timeout=0.5)

    with pytest.raises(AnalysisUnavailableError):
        remote.analyze_lot("req-6", make_input())

    result = FallbackRescueAnalyzer(remote, LocalRescueAnalyzer()).analyze_lot("req-6", make_input())
    assert result.source == ANALYSIS_SOURCE_LOCAL_FALLBACK
    assert comparable(result) == comparable(LocalRescueAnalyzer().analyze_lot("req-6", make_input()))


def test_deadline_exceeded_falls_back():
    server, port = start_server(SlowAnalyzer())
    try:
        slow_client = client_for(port, timeout=0.05)
        with pytest.raises(AnalysisUnavailableError):
            slow_client.analyze_lot("req-7", make_input())
        result = FallbackRescueAnalyzer(slow_client, LocalRescueAnalyzer()).analyze_lot("req-7", make_input())
        assert result.source == ANALYSIS_SOURCE_LOCAL_FALLBACK
    finally:
        server.stop(grace=None)


def test_local_analyzer_rejects_invalid_input_like_the_service():
    with pytest.raises(ValueError):
        LocalRescueAnalyzer().analyze_lot("req-8", make_input(quantity=0))
    with pytest.raises(ValueError):
        LocalRescueAnalyzer().analyze_lot("req-8", make_input(hours=0))


def test_target_requires_a_shared_token():
    with pytest.raises(ValidationError):
        Settings(analysis_grpc_target="analysis.internal:50051", analysis_shared_token=None, _env_file=None)


# ---- API integration ----


def api_plan_events(plan_id: int) -> list[str]:
    with SessionLocal() as session:
        events = session.query(RescuePlanEventRecord).filter_by(plan_id=plan_id).order_by(RescuePlanEventRecord.id)
        return [event.event_type for event in events]


def create_api_plan(email: str) -> dict:
    reset_db()
    client = TestClient(main.app)
    headers = auth_headers(client, email)
    _shop_id, _product_id, lot_id = seed_lot(client, headers, history_days=30)
    response = client.post(f"/api/v1/lots/{lot_id}/rescue-plan", headers={**headers, "x-request-id": "api-trace-1"})
    assert response.status_code == 201
    return response.json()


def test_api_uses_the_grpc_service_when_configured(running_server, monkeypatch):
    monkeypatch.setattr(settings, "analysis_grpc_target", f"127.0.0.1:{running_server}")
    monkeypatch.setattr(settings, "analysis_shared_token", TOKEN)
    dependencies.get_grpc_rescue_analyzer.cache_clear()

    plan = create_api_plan("grpc-owner@example.com")

    assert plan["status"] == "pending_approval"
    assert "analysis_fallback" not in api_plan_events(plan["id"])
    dependencies.get_grpc_rescue_analyzer.cache_clear()


def test_api_still_creates_the_plan_when_the_service_is_down(monkeypatch):
    server, port = start_server()
    server.stop(grace=None).wait()
    monkeypatch.setattr(settings, "analysis_grpc_target", f"127.0.0.1:{port}")
    monkeypatch.setattr(settings, "analysis_shared_token", TOKEN)
    monkeypatch.setattr(settings, "analysis_grpc_timeout_seconds", 0.5)
    dependencies.get_grpc_rescue_analyzer.cache_clear()

    plan = create_api_plan("fallback-owner@example.com")

    assert plan["status"] == "pending_approval"
    assert api_plan_events(plan["id"]) == ["generated", "analysis_fallback"]
    dependencies.get_grpc_rescue_analyzer.cache_clear()
