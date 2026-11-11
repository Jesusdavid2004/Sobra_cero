import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class StreamConnection(Protocol):
    async def send_json(self, data: Any) -> None: ...


class LotStreamHub:
    """Fan-out of lot events to the WebSocket connections of this process."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[StreamConnection]] = {}
        self._subscriptions: dict[StreamConnection, set[int]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscription_count(self, connection: StreamConnection) -> int:
        return len(self._subscriptions.get(connection, ()))

    def subscribe(self, connection: StreamConnection, lot_ids: set[int]) -> None:
        self._subscriptions.setdefault(connection, set()).update(lot_ids)
        for lot_id in lot_ids:
            self._subscribers.setdefault(lot_id, set()).add(connection)

    def unsubscribe(self, connection: StreamConnection, lot_ids: set[int]) -> None:
        owned = self._subscriptions.get(connection, set())
        for lot_id in lot_ids & owned:
            owned.discard(lot_id)
            self._drop_subscriber(lot_id, connection)

    def remove(self, connection: StreamConnection) -> None:
        for lot_id in self._subscriptions.pop(connection, set()):
            self._drop_subscriber(lot_id, connection)

    def _drop_subscriber(self, lot_id: int, connection: StreamConnection) -> None:
        subscribers = self._subscribers.get(lot_id)
        if subscribers is None:
            return
        subscribers.discard(connection)
        if not subscribers:
            del self._subscribers[lot_id]

    async def dispatch(self, message: dict[str, Any]) -> None:
        for connection in list(self._subscribers.get(int(message["lot_id"]), ())):
            try:
                await connection.send_json(message)
            except (RuntimeError, OSError):
                logger.info("Dropping a lot stream connection that could not be written to")
                self.remove(connection)

    def dispatch_threadsafe(self, message: dict[str, Any]) -> None:
        """Called from worker threads (sync request handlers). Without a bound loop nobody is listening."""
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.dispatch(message), self._loop)
