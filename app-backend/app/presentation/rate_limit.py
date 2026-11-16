import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request

from app.domain.exceptions import RateLimitedError

buckets: dict[str, list[float]] = defaultdict(list)


def rate_limited(limit: int, window_seconds: int = 60) -> Callable[[Request], None]:
    """Sliding-window limit per client address and route. Raises a typed error mapped to HTTP 429."""

    def dependency(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        route = request.scope.get("route")
        key = f"{client_host}:{getattr(route, 'path', request.url.path)}"
        now = time.time()
        bucket = buckets[key]
        bucket[:] = [stamp for stamp in bucket if now - stamp < window_seconds]
        if len(bucket) >= limit:
            raise RateLimitedError("Too many requests")
        bucket.append(now)

    return dependency
