"""Public lot stream: live stock for lots a browser is looking at.

Business changes still go through the HTTPS endpoints (authentication, validation, transactions).
The socket only delivers facts that anyone can already read from `GET /lots/{id}`: quantity, status,
discount and a version. A client applies an event only if its version is newer, and asks for a
snapshot (by subscribing again) after every reconnect.
"""

import asyncio
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.dependencies import get_lot_stream_hub
from app.infrastructure.realtime.hub import LotStreamHub
from app.infrastructure.realtime.messages import error_message, snapshot_message
from app.infrastructure.realtime.snapshots import read_lot_states

router = APIRouter(prefix="/api/v1", tags=["realtime"])

POLICY_VIOLATION = 1008
RATE_WINDOW_SECONDS = 10.0
MAX_IDS_PER_MESSAGE = 50

ERROR_INVALID_MESSAGE = "invalid_message"
ERROR_TOO_MANY_SUBSCRIPTIONS = "too_many_subscriptions"


class ClientMessage(BaseModel):
    action: Literal["subscribe", "unsubscribe", "ping"]
    lot_ids: list[int] = Field(default_factory=list, max_length=MAX_IDS_PER_MESSAGE)


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    allowed = {item.strip() for item in settings.cors_origins.split(",") if item.strip()}
    return origin is None or origin in allowed


class _MessageBudget:
    """Sliding window so a client cannot flood the server."""

    def __init__(self) -> None:
        self._stamps: list[float] = []

    def allow(self) -> bool:
        now = time.monotonic()
        self._stamps = [stamp for stamp in self._stamps if now - stamp < RATE_WINDOW_SECONDS]
        self._stamps.append(now)
        return len(self._stamps) <= settings.realtime_messages_per_window


def _parse(raw: str) -> ClientMessage | None:
    if len(raw.encode("utf-8")) > settings.realtime_max_message_bytes:
        return None
    try:
        return ClientMessage.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        return None


async def _subscribe(websocket: WebSocket, hub: LotStreamHub, lot_ids: set[int]) -> None:
    if hub.subscription_count(websocket) + len(lot_ids) > settings.realtime_max_subscriptions:
        await websocket.send_json(error_message(ERROR_TOO_MANY_SUBSCRIPTIONS))
        return
    hub.subscribe(websocket, lot_ids)
    states = await run_in_threadpool(read_lot_states, lot_ids)
    await websocket.send_json(snapshot_message(states))


async def _handle(websocket: WebSocket, hub: LotStreamHub, message: ClientMessage) -> None:
    lot_ids = {lot_id for lot_id in message.lot_ids if lot_id > 0}
    if message.action == "subscribe" and lot_ids:
        await _subscribe(websocket, hub, lot_ids)
    elif message.action == "unsubscribe":
        hub.unsubscribe(websocket, lot_ids)
    elif message.action == "ping":
        await websocket.send_json({"type": "pong"})


@router.websocket("/ws/lots")
async def lot_stream(websocket: WebSocket, hub: LotStreamHub = Depends(get_lot_stream_hub)) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=POLICY_VIOLATION)
        return
    await websocket.accept()
    hub.bind_loop(asyncio.get_running_loop())
    budget = _MessageBudget()
    try:
        while True:
            raw = await websocket.receive_text()
            if not budget.allow():
                await websocket.close(code=POLICY_VIOLATION)
                return
            message = _parse(raw)
            if message is None:
                await websocket.send_json(error_message(ERROR_INVALID_MESSAGE))
                continue
            await _handle(websocket, hub, message)
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(websocket)
