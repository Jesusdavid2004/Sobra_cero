from typing import Any

from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response

from app.domain.collection import StopReason

ACCESS_DENIED_STATUSES = {401, 403}
RATE_LIMITED_STATUS = 429


class StopOnAccessDeniedMiddleware:
    """End the run on the first refusal. The collector never retries around a block.

    A 401 or 403 means the source does not want this access; a 429 means we are asking too often.
    In both cases the connector stops and the run records why, instead of trying harder.
    """

    def process_response(self, request: Request, response: Response, spider: Any) -> Response:
        if response.status in ACCESS_DENIED_STATUSES:
            reason = StopReason.ACCESS_DENIED
        elif response.status == RATE_LIMITED_STATUS:
            reason = StopReason.RATE_LIMITED
        else:
            return response
        spider.context.stop_reason = reason.value
        spider.crawler.engine.close_spider(spider, reason.value)
        raise IgnoreRequest(f"Source refused access ({response.status}); the connector stopped")
