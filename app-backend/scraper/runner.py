"""Run one source end to end: gate, record, crawl, summarize.

This must run in its own process: Twisted's reactor cannot be restarted, so the web process
never imports Scrapy and instead starts `python -m scraper.run` (see ADR 0010).
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.domain.collection import ExecutionStatus, SourceKind, StopReason, Trigger
from app.domain.exceptions import SourceNotRunnableError
from app.domain.places import PASTO_BOUNDS, BoundingBox
from app.domain.source_policy import SourceState, ensure_runnable
from app.infrastructure.network import resolve_host
from app.infrastructure.repositories.external_data_repository import (
    SqlAlchemyExternalDataRepository,
)
from scraper.context import (
    ACCEPTED,
    DUPLICATES,
    PENDING,
    REJECTED,
    CollectionContext,
    utc_now,
)
from scraper.spiders.jsonld_catalog import JsonLdCatalogSpider
from scraper.spiders.overpass import OverpassSpider

SPIDERS = {
    SourceKind.OVERPASS.value: OverpassSpider,
    SourceKind.JSONLD_CATALOG.value: JsonLdCatalogSpider,
}
ROBOTS_FORBIDDEN_STAT = "robotstxt/forbidden"
TIMEOUT_FINISH_REASON = "closespider_timeout"


@dataclass(frozen=True)
class RunSummary:
    execution_id: int
    status: str
    accepted: int
    rejected: int
    pending: int
    duplicates: int
    stop_reason: str
    error: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _allowed_domains() -> list[str]:
    return [item.strip() for item in app_settings.scraper_allowed_domains.split(",") if item.strip()]


def _enforce_url_policy() -> bool:
    return not (app_settings.scraper_disable_url_policy and app_settings.app_environment != "production")


def _refused(repository: SqlAlchemyExternalDataRepository, session: Session, source_id: int, trigger: Trigger,
             user_id: int | None, reason: str) -> RunSummary:  # fmt: skip
    now = utc_now()
    execution_id = repository.start_execution(source_id, trigger, user_id, now)
    repository.finish_execution(
        execution_id, ExecutionStatus.STOPPED, now, 0, 0, 0, StopReason.NOT_ALLOWED.value, reason
    )
    session.commit()
    return RunSummary(execution_id, ExecutionStatus.STOPPED.value, 0, 0, 0, 0, StopReason.NOT_ALLOWED.value, reason)


def _crawl(spider_class: type, context: CollectionContext) -> tuple[dict[str, object], str]:
    crawl_settings = Settings()
    crawl_settings.setmodule("scraper.settings")
    process = CrawlerProcess(crawl_settings)
    crawler = process.create_crawler(spider_class)
    process.crawl(crawler, context=context)
    process.start()
    stats = crawler.stats.get_stats() if crawler.stats else {}
    return stats, str(stats.get("finish_reason", ""))


def run_source(
    source_key: str,
    trigger: Trigger,
    user_id: int | None,
    session_factory: Callable[[], Session],
) -> RunSummary:
    with session_factory() as session:
        repository = SqlAlchemyExternalDataRepository(session)
        source = repository.get_source(source_key)
        if source is None:
            raise SourceNotRunnableError("unknown_source")
        state = SourceState(source.key, source.kind, source.enabled, source.terms_reviewed, source.base_url)
        try:
            ensure_runnable(state, _allowed_domains(), resolve_host, _enforce_url_policy())
        except SourceNotRunnableError as error:
            return _refused(repository, session, source.id, trigger, user_id, str(error))

        execution_id = repository.start_execution(source.id, trigger, user_id, utc_now())
        session.commit()
        area = BoundingBox(*PASTO_BOUNDS) if source.kind == SourceKind.OVERPASS.value else None
        context = CollectionContext(session, source, execution_id, area)
        status, error = ExecutionStatus.SUCCEEDED, ""
        stats: dict[str, object] = {}
        finish_reason = ""
        try:
            stats, finish_reason = _crawl(SPIDERS[source.kind], context)
        except Exception as exc:  # the run records any crash; the web process must never see a traceback
            status, error = ExecutionStatus.FAILED, f"{type(exc).__name__}: {exc}"
            context.stop_reason = StopReason.CRASHED.value
            session.rollback()
        counters = context.counters
        if not context.stop_reason and stats.get(ROBOTS_FORBIDDEN_STAT) and not counters[ACCEPTED]:
            context.stop_reason = StopReason.ROBOTS_FORBIDDEN.value
        if not context.stop_reason and finish_reason == TIMEOUT_FINISH_REASON:
            context.stop_reason = StopReason.TIMEOUT.value
        if context.stop_reason and status is ExecutionStatus.SUCCEEDED:
            status = ExecutionStatus.STOPPED
        repository.finish_execution(
            execution_id,
            status,
            utc_now(),
            counters[ACCEPTED],
            counters[REJECTED],
            counters[PENDING],
            context.stop_reason,
            error,
        )
        session.commit()
        return RunSummary(
            execution_id,
            status.value,
            counters[ACCEPTED],
            counters[REJECTED],
            counters[PENDING],
            counters[DUPLICATES],
            context.stop_reason,
            error,
        )
