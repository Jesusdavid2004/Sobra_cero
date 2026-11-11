import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect
from test_rescue_plan import auth_headers, reset_db, seed_lot

from app import main
from app.config import settings
from app.db import SessionLocal
from app.domain.events import LotStockChanged
from app.infrastructure.realtime.hub import LotStreamHub
from app.infrastructure.realtime.messages import LOT_EVENTS_CHANNEL, event_message
from app.infrastructure.realtime.publishers import RedisLotEventPublisher
from app.models import Lot, Reservation
from app.services import cancel_reservation, confirm_reservation_pickup

STREAM_URL = "/api/v1/ws/lots"
RECEIVE_TIMEOUT_SECONDS = 5
EVENT_KEYS = {"type", "lot_id", "version", "quantity", "status", "discount_percent", "occurred_at"}
POLICY_VIOLATION = 1008


def receive(socket: WebSocketTestSession) -> dict[str, Any]:
    """Receive one frame, failing instead of hanging when nothing arrives."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(socket.receive_json).result(timeout=RECEIVE_TIMEOUT_SECONDS)


def subscribe(socket: WebSocketTestSession, *lot_ids: int) -> dict[str, Any]:
    socket.send_json({"action": "subscribe", "lot_ids": list(lot_ids)})
    return receive(socket)


def stock_event(lot_id: int = 1, version: int = 1) -> LotStockChanged:
    return LotStockChanged(
        lot_id=lot_id,
        version=version,
        quantity=4,
        status="active",
        discount_percent=30,
        occurred_at=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
    )


class FakeConnection:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[Any] = []
        self.fail = fail

    async def send_json(self, data: Any) -> None:
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(data)


# ---- hub ----


def test_hub_delivers_events_only_to_subscribers_of_that_lot():
    hub, first, second = LotStreamHub(), FakeConnection(), FakeConnection()
    hub.subscribe(first, {1})
    hub.subscribe(second, {2})

    asyncio.run(hub.dispatch(event_message(stock_event(lot_id=1))))

    assert len(first.sent) == 1 and second.sent == []


def test_hub_stops_delivering_after_unsubscribe_or_removal():
    hub, connection = LotStreamHub(), FakeConnection()
    hub.subscribe(connection, {1, 2})
    hub.unsubscribe(connection, {1})

    asyncio.run(hub.dispatch(event_message(stock_event(lot_id=1))))
    asyncio.run(hub.dispatch(event_message(stock_event(lot_id=2))))
    assert len(connection.sent) == 1

    hub.remove(connection)
    asyncio.run(hub.dispatch(event_message(stock_event(lot_id=2))))
    assert len(connection.sent) == 1 and hub.subscription_count(connection) == 0


def test_hub_drops_a_connection_that_cannot_be_written_to():
    hub, broken, healthy = LotStreamHub(), FakeConnection(fail=True), FakeConnection()
    hub.subscribe(broken, {1})
    hub.subscribe(healthy, {1})

    asyncio.run(hub.dispatch(event_message(stock_event())))

    assert len(healthy.sent) == 1 and hub.subscription_count(broken) == 0


def test_hub_without_a_running_loop_ignores_events():
    LotStreamHub().dispatch_threadsafe(event_message(stock_event()))


# ---- messages and publishers ----


def test_event_message_exposes_only_public_stock_facts():
    message = event_message(stock_event())

    assert set(message) == EVENT_KEYS
    assert message["type"] == "lot.stock_changed"


def test_redis_publisher_sends_the_event_on_the_lot_channel():
    class FakeRedis:
        def __init__(self) -> None:
            self.published: list[tuple[str, str]] = []

        def publish(self, channel: str, payload: str) -> None:
            self.published.append((channel, payload))

    client = FakeRedis()

    RedisLotEventPublisher(client).publish(stock_event(lot_id=7, version=3))  # type: ignore[arg-type]

    channel, payload = client.published[0]
    assert channel == LOT_EVENTS_CHANNEL
    assert json.loads(payload)["lot_id"] == 7 and json.loads(payload)["version"] == 3


# ---- WebSocket endpoint ----


@pytest.fixture
def api():
    reset_db()
    return TestClient(main.app)


def seed_public_lot(client: TestClient, quantity: int = 5) -> tuple[int, dict[str, str]]:
    owner = auth_headers(client, "owner@example.com")
    _shop_id, _product_id, lot_id = seed_lot(client, owner, history_days=0, quantity=quantity)
    return lot_id, owner


def reserve(client: TestClient, lot_id: int, email: str, quantity: int = 1) -> dict[str, Any]:
    customer = auth_headers(client, email, role="customer")
    response = client.post(f"/api/v1/lots/{lot_id}/reserve", json={"quantity": quantity}, headers=customer)
    assert response.status_code == 201, response.text
    return response.json()


def test_subscribing_returns_a_snapshot_of_the_current_state(api):
    lot_id, _owner = seed_public_lot(api, quantity=5)

    with api.websocket_connect(STREAM_URL) as socket:
        snapshot = subscribe(socket, lot_id)

    assert snapshot["type"] == "snapshot"
    assert snapshot["lots"] == [
        {"lot_id": lot_id, "version": 0, "quantity": 5, "status": "active", "discount_percent": 20}
    ]


def test_a_reservation_in_another_session_updates_the_stream_with_a_newer_version(api):
    lot_id, _owner = seed_public_lot(api, quantity=5)

    with api.websocket_connect(STREAM_URL) as socket:
        subscribe(socket, lot_id)
        reserve(api, lot_id, "first@example.com", quantity=2)
        first = receive(socket)
        reserve(api, lot_id, "second@example.com", quantity=1)
        second = receive(socket)

    assert (first["quantity"], first["version"]) == (3, 1)
    assert (second["quantity"], second["version"]) == (2, 2)
    assert set(first) == EVENT_KEYS


def test_stream_messages_never_contain_pickup_codes(api):
    lot_id, _owner = seed_public_lot(api)

    with api.websocket_connect(STREAM_URL) as socket:
        subscribe(socket, lot_id)
        reservation = reserve(api, lot_id, "customer@example.com")
        event = receive(socket)

    assert reservation["pickup_code"] not in json.dumps(event)


def test_reconnecting_returns_a_snapshot_with_the_missed_changes(api):
    lot_id, _owner = seed_public_lot(api, quantity=5)
    with api.websocket_connect(STREAM_URL) as socket:
        subscribe(socket, lot_id)

    reserve(api, lot_id, "while-offline@example.com", quantity=3)

    with api.websocket_connect(STREAM_URL) as socket:
        snapshot = subscribe(socket, lot_id)
    assert (snapshot["lots"][0]["quantity"], snapshot["lots"][0]["version"]) == (2, 1)


def test_a_connection_from_an_untrusted_origin_is_refused(api):
    with pytest.raises(WebSocketDisconnect) as refused:
        with api.websocket_connect(STREAM_URL, headers={"origin": "https://evil.example"}):
            pass

    assert refused.value.code == POLICY_VIOLATION


def test_the_configured_frontend_origin_is_accepted(api):
    origin = settings.cors_origins.split(",")[0].strip()

    with api.websocket_connect(STREAM_URL, headers={"origin": origin}) as socket:
        socket.send_json({"action": "ping"})
        assert receive(socket) == {"type": "pong"}


def test_an_invalid_message_gets_an_error_and_the_connection_survives(api):
    with api.websocket_connect(STREAM_URL) as socket:
        socket.send_text("not json")
        assert receive(socket) == {"type": "error", "code": "invalid_message"}
        socket.send_json({"action": "delete-everything"})
        assert receive(socket)["code"] == "invalid_message"
        socket.send_json({"action": "ping"})
        assert receive(socket) == {"type": "pong"}


def test_an_oversized_message_is_rejected(api, monkeypatch):
    monkeypatch.setattr(settings, "realtime_max_message_bytes", 40)

    with api.websocket_connect(STREAM_URL) as socket:
        socket.send_json({"action": "subscribe", "lot_ids": list(range(1, 30))})
        assert receive(socket)["code"] == "invalid_message"


def test_subscriptions_per_connection_are_capped(api, monkeypatch):
    monkeypatch.setattr(settings, "realtime_max_subscriptions", 2)

    with api.websocket_connect(STREAM_URL) as socket:
        assert subscribe(socket, 1, 2)["type"] == "snapshot"
        assert subscribe(socket, 3) == {"type": "error", "code": "too_many_subscriptions"}


def test_a_client_that_floods_the_socket_is_disconnected(api, monkeypatch):
    monkeypatch.setattr(settings, "realtime_messages_per_window", 3)

    with api.websocket_connect(STREAM_URL) as socket:
        for _ in range(3):
            socket.send_json({"action": "ping"})
            receive(socket)
        socket.send_json({"action": "ping"})
        with pytest.raises(WebSocketDisconnect) as closed:
            receive(socket)

    assert closed.value.code == POLICY_VIOLATION


# ---- the version is the ordering key ----


def current_version(lot_id: int) -> int:
    with SessionLocal() as db:
        lot = db.get(Lot, lot_id)
        assert lot is not None
        return lot.version


def test_every_stock_change_increases_the_version_but_a_pickup_does_not(api):
    lot_id, _owner = seed_public_lot(api, quantity=5)
    assert current_version(lot_id) == 0

    reservation = reserve(api, lot_id, "customer@example.com")
    assert current_version(lot_id) == 1

    with SessionLocal() as db:
        confirm_reservation_pickup(db, reservation["id"], reservation["pickup_code"])
    assert current_version(lot_id) == 1

    other = reserve(api, lot_id, "other@example.com")
    with SessionLocal() as db:
        reservation_row = db.get(Reservation, other["id"])
        assert reservation_row is not None
        cancel_reservation(db, other["id"], reservation_row.user_id)
    assert current_version(lot_id) == 3
