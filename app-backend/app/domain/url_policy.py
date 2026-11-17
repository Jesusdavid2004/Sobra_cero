"""Which URLs a collection source may point to. This is the guard against server-side request forgery.

A source URL must be HTTPS on the default port, carry no credentials, belong to an allowed domain
(or one of its subdomains) and resolve only to public addresses. Anything else is rejected before
a connector can run, so nobody can aim the collector at internal services.
"""

import ipaddress
from collections.abc import Callable, Collection
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit

from app.domain.exceptions import SourceUrlRejectedError

HTTPS_PORT = 443
MAX_URL_CHARS = 500
Resolver = Callable[[str], list[str]]


class UrlRejection(StrEnum):
    TOO_LONG = "too_long"
    NOT_HTTPS = "not_https"
    HAS_CREDENTIALS = "has_credentials"
    BAD_PORT = "bad_port"
    NO_HOST = "no_host"
    IP_LITERAL = "ip_literal"
    DOMAIN_NOT_ALLOWED = "domain_not_allowed"
    UNRESOLVABLE = "unresolvable"
    PRIVATE_ADDRESS = "private_address"


def _reject(reason: UrlRejection) -> SourceUrlRejectedError:
    return SourceUrlRejectedError(reason.value)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast


def _domain_allowed(host: str, allowed: Collection[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in (item.lower() for item in allowed))


def validate_source_url(url: str, allowed_domains: Collection[str], resolve: Resolver) -> str:
    """Return the URL without its fragment, or raise `SourceUrlRejectedError` with a reason code."""
    if len(url) > MAX_URL_CHARS:
        raise _reject(UrlRejection.TOO_LONG)
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise _reject(UrlRejection.NOT_HTTPS)
    if parts.username is not None or parts.password is not None:
        raise _reject(UrlRejection.HAS_CREDENTIALS)
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise _reject(UrlRejection.NO_HOST)
    try:
        port = parts.port
    except ValueError as exc:
        raise _reject(UrlRejection.BAD_PORT) from exc
    if port not in (None, HTTPS_PORT):
        raise _reject(UrlRejection.BAD_PORT)
    if _is_ip_literal(host):
        raise _reject(UrlRejection.IP_LITERAL)
    if not _domain_allowed(host, allowed_domains):
        raise _reject(UrlRejection.DOMAIN_NOT_ALLOWED)
    addresses = resolve(host)
    if not addresses:
        raise _reject(UrlRejection.UNRESOLVABLE)
    if not all(_is_public(address) for address in addresses):
        raise _reject(UrlRejection.PRIVATE_ADDRESS)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, parts.query, ""))
