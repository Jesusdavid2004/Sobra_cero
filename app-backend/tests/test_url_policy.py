import pytest

from app.domain.exceptions import SourceUrlRejectedError
from app.domain.url_policy import validate_source_url

ALLOWED = ["exito.com", "overpass-api.de"]
PUBLIC = "93.184.216.34"


def resolver(*addresses: str):
    return lambda _host: list(addresses or [PUBLIC])


def validate(url: str, *addresses: str) -> str:
    return validate_source_url(url, ALLOWED, resolver(*addresses))


def reason(url: str, *addresses: str) -> str:
    with pytest.raises(SourceUrlRejectedError) as error:
        validate(url, *addresses)
    return str(error.value)


def test_an_https_url_on_an_allowed_domain_is_accepted_without_its_fragment():
    assert validate("https://www.Exito.com/pan?x=1#top") == "https://www.exito.com/pan?x=1"


def test_the_domain_itself_and_its_subdomains_are_allowed():
    assert validate("https://exito.com/a")
    assert validate("https://catalog.api.exito.com/a")


def test_a_lookalike_domain_is_not_allowed():
    assert reason("https://notexito.com/") == "domain_not_allowed"
    assert reason("https://exito.com.evil.example/") == "domain_not_allowed"


def test_credentials_in_the_url_cannot_disguise_the_real_host():
    assert reason("https://exito.com@evil.example/") == "has_credentials"
    assert reason("https://user:secret@exito.com/") == "has_credentials"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://exito.com/", "not_https"),
        ("ftp://exito.com/", "not_https"),
        ("file:///etc/passwd", "not_https"),
        ("https://exito.com:8443/", "bad_port"),
        ("https://exito.com:notaport/", "bad_port"),
        ("https:///path", "no_host"),
        ("https://127.0.0.1/", "ip_literal"),
        ("https://[::1]/", "ip_literal"),
        ("https://169.254.169.254/latest/meta-data", "ip_literal"),
        ("https://exito.com/" + "a" * 600, "too_long"),
    ],
)
def test_unsafe_url_shapes_are_rejected_with_a_reason(url, expected):
    assert reason(url) == expected


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "172.16.3.1", "192.168.1.10", "169.254.169.254", "::1", "fe80::1", "0.0.0.0"],
)
def test_a_domain_that_resolves_to_a_private_address_is_rejected(address):
    assert reason("https://exito.com/", address) == "private_address"


def test_one_private_address_among_public_ones_is_enough_to_reject():
    assert reason("https://exito.com/", PUBLIC, "10.0.0.5") == "private_address"


def test_a_domain_that_does_not_resolve_is_rejected():
    with pytest.raises(SourceUrlRejectedError) as error:
        validate_source_url("https://exito.com/", ALLOWED, lambda _host: [])

    assert str(error.value) == "unresolvable"
