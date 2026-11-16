"""The gate every collection run passes through before any request is made.

A source runs only when it is enabled, a person recorded that its terms were reviewed, and its
URL is safe. A permissive robots.txt is never enough on its own.
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from app.domain.collection import SourceKind
from app.domain.exceptions import SourceNotRunnableError, SourceUrlRejectedError
from app.domain.url_policy import Resolver, validate_source_url

RUNNABLE_KINDS = (SourceKind.OVERPASS.value, SourceKind.JSONLD_CATALOG.value)


class NotRunnable(StrEnum):
    UNSUPPORTED_KIND = "unsupported_kind"
    DISABLED = "disabled"
    TERMS_NOT_REVIEWED = "terms_not_reviewed"
    URL_REJECTED = "url_rejected"


@dataclass(frozen=True)
class SourceState:
    key: str
    kind: str
    enabled: bool
    terms_reviewed: bool
    base_url: str


def ensure_runnable(
    source: SourceState,
    allowed_domains: Collection[str],
    resolve: Resolver,
    enforce_url_policy: bool = True,
) -> None:
    if source.kind not in RUNNABLE_KINDS:
        raise SourceNotRunnableError(NotRunnable.UNSUPPORTED_KIND.value)
    if not source.enabled:
        raise SourceNotRunnableError(NotRunnable.DISABLED.value)
    if not source.terms_reviewed:
        raise SourceNotRunnableError(NotRunnable.TERMS_NOT_REVIEWED.value)
    if not enforce_url_policy:
        return
    try:
        validate_source_url(source.base_url, allowed_domains, resolve)
    except SourceUrlRejectedError as error:
        raise SourceNotRunnableError(f"{NotRunnable.URL_REJECTED.value}:{error}") from error
