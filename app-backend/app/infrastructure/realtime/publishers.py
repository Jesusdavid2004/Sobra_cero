import asyncio
import json
import logging

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from app.domain.events import LotStockChanged
from app.infrastructure.realtime.hub import LotStreamHub
from app.infrastructure.realtime.messages import LOT_EVENTS_CHANNEL, event_message

logger = logging.getLogger(__name__)
LISTENER_RETRY_SECONDS = 2.0


class InMemoryLotEventPublisher:
    """Single-process delivery, enough for one replica and for tests."""

    def __init__(self, hub: LotStreamHub) -> None:
        self._hub = hub

    def publish(self, event: LotStockChanged) -> None:
        self._hub.dispatch_threadsafe(event_message(event))


class RedisLotEventPublisher:
    """Pub/Sub only says that something changed; the database stays the source of truth."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    def publish(self, event: LotStockChanged) -> None:
        self._client.publish(LOT_EVENTS_CHANNEL, json.dumps(event_message(event)))


async def listen_for_lot_events(redis_url: str, hub: LotStreamHub) -> None:
    """Forward Redis messages to the connections of this process, reconnecting after failures."""
    while True:
        client = AsyncRedis.from_url(redis_url, decode_responses=True)
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(LOT_EVENTS_CHANNEL)
            async for item in pubsub.listen():
                if item.get("type") == "message":
                    await hub.dispatch(json.loads(item["data"]))
        except (RedisError, OSError, json.JSONDecodeError):
            logger.warning("Lot event listener lost its connection; retrying")
        finally:
            await client.aclose()
        await asyncio.sleep(LISTENER_RETRY_SECONDS)
