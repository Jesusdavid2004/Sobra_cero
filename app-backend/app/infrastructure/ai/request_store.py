from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from threading import Lock
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.domain.exceptions import AIProviderUnavailableError, AIQuotaExceededError


class AIRequestStore(Protocol):
    def get_cached_response(self, key: str) -> str | None: ...

    def cache_response(self, key: str, response: str, ttl_seconds: int) -> None: ...

    def consume_daily_quota(self, user_id: int, daily_limit: int) -> None: ...


class InMemoryAIRequestStore:
    """Thread-safe cache and quota store for deterministic local/test use."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[str, datetime]] = {}
        self._requests: dict[tuple[int, str], int] = {}
        self._lock = Lock()

    def get_cached_response(self, key: str) -> str | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            if cached[1] <= now:
                del self._cache[key]
                return None
            return cached[0]

    def cache_response(self, key: str, response: str, ttl_seconds: int) -> None:
        with self._lock:
            self._cache[key] = (response, datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))

    def consume_daily_quota(self, user_id: int, daily_limit: int) -> None:
        day_key = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            key = (user_id, day_key)
            request_count = self._requests.get(key, 0) + 1
            if request_count > daily_limit:
                raise AIQuotaExceededError("Daily AI request allowance exceeded")
            self._requests[key] = request_count


class RedisAIRequestStore:
    """Shared cache and per-user daily quota for application instances."""

    _INCREMENT_WITH_DAILY_EXPIRY = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return count
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    def get_cached_response(self, key: str) -> str | None:
        try:
            cached = self._client.get(f"ai:cache:{key}")
        except RedisError as exc:
            raise AIProviderUnavailableError("AI request policy store is unavailable") from exc
        return cached if isinstance(cached, str) else None

    def cache_response(self, key: str, response: str, ttl_seconds: int) -> None:
        try:
            self._client.setex(f"ai:cache:{key}", ttl_seconds, response)
        except RedisError as exc:
            raise AIProviderUnavailableError("AI request policy store is unavailable") from exc

    def consume_daily_quota(self, user_id: int, daily_limit: int) -> None:
        now = datetime.now(timezone.utc)
        midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
        ttl_seconds = max(1, int((midnight - now).total_seconds()))
        key = f"ai:quota:{user_id}:{now.date().isoformat()}"
        try:
            request_count = self._client.eval(self._INCREMENT_WITH_DAILY_EXPIRY, 1, key, ttl_seconds)
        except RedisError as exc:
            raise AIProviderUnavailableError("AI request policy store is unavailable") from exc
        if int(request_count) > daily_limit:
            raise AIQuotaExceededError("Daily AI request allowance exceeded")
