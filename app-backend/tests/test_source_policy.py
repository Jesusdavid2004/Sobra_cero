import pytest

from app.domain.exceptions import SourceNotRunnableError
from app.domain.source_policy import SourceState, ensure_runnable

ALLOWED = ["overpass-api.de", "exito.com"]


def public(_host: str) -> list[str]:
    return ["93.184.216.34"]


def state(**overrides) -> SourceState:
    fields = {
        "key": "exito",
        "kind": "jsonld_catalog",
        "enabled": True,
        "terms_reviewed": True,
        "base_url": "https://www.exito.com/pan",
        **overrides,
    }
    return SourceState(**fields)


def reason(source: SourceState, **kwargs) -> str:
    with pytest.raises(SourceNotRunnableError) as error:
        ensure_runnable(source, ALLOWED, kwargs.pop("resolve", public), **kwargs)
    return str(error.value)


def test_a_reviewed_enabled_source_with_a_safe_url_may_run():
    ensure_runnable(state(), ALLOWED, public)


def test_a_new_source_does_not_run_until_its_terms_are_reviewed():
    assert reason(state(terms_reviewed=False)) == "terms_not_reviewed"


def test_a_disabled_source_does_not_run_even_if_its_terms_were_reviewed():
    assert reason(state(enabled=False)) == "disabled"


def test_demo_and_unknown_kinds_cannot_run():
    assert reason(state(kind="demo")) == "unsupported_kind"
    assert reason(state(kind="google_maps")) == "unsupported_kind"


def test_an_unsafe_url_is_reported_with_its_own_reason():
    assert reason(state(base_url="http://www.exito.com/")) == "url_rejected:not_https"
    assert reason(state(base_url="https://evil.example/")) == "url_rejected:domain_not_allowed"
    assert reason(state(), resolve=lambda _host: ["10.0.0.5"]) == "url_rejected:private_address"


def test_the_url_policy_can_be_skipped_only_by_an_explicit_argument():
    ensure_runnable(state(base_url="http://127.0.0.1:8000/"), ALLOWED, public, enforce_url_policy=False)
