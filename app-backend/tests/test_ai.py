from collections.abc import Iterator

import pytest

from app.application.ai_dto import PromotionCopy
from app.domain.exceptions import AIQuotaExceededError, AIResponseInvalidError
from app.infrastructure.ai.providers import AnthropicAdapter, OpenAICompatibleAdapter
from app.infrastructure.ai.request_store import InMemoryAIRequestStore
from app.llm import StructuredAIProvider


def create_provider(store: InMemoryAIRequestStore) -> StructuredAIProvider:
    return StructuredAIProvider("test", None, None, "test-model", store)


def test_structured_provider_retries_schema_validation_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryAIRequestStore()
    provider = create_provider(store)
    responses: Iterator[str] = iter(['{"text":""}', '{"text":"Fresh food rescued"}'])
    requests: list[dict[str, object]] = []

    def request(**kwargs: object) -> tuple[str, int, int]:
        requests.append(kwargs)
        return next(responses), 12, 4

    monkeypatch.setattr(provider, "_request", request)
    monkeypatch.setattr("app.llm.settings.ai_daily_quota", 1)

    result = provider.generate_structured(
        prompt="Write a short promotion",
        response_model=PromotionCopy,
        user_id=7,
        locale="en",
        prompt_version="test-v1",
    )
    cached_result = provider.generate_structured(
        prompt="Write a short promotion",
        response_model=PromotionCopy,
        user_id=7,
        locale="en",
        prompt_version="test-v1",
    )

    assert result.text == "Fresh food rescued"
    assert cached_result == result
    assert len(requests) == 2
    assert requests[1]["validation_errors"] is not None


def test_structured_provider_enforces_daily_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = create_provider(InMemoryAIRequestStore())
    calls = 0

    def request(**kwargs: object) -> tuple[str, int, int]:
        nonlocal calls
        calls += 1
        return '{"text":"Rescue this food"}', 0, 0

    monkeypatch.setattr(provider, "_request", request)
    monkeypatch.setattr("app.llm.settings.ai_daily_quota", 1)

    for prompt in ("first request", "different request"):
        if prompt == "first request":
            provider.generate_structured(
                prompt=prompt,
                response_model=PromotionCopy,
                user_id=8,
                locale="en",
                prompt_version="test-v1",
            )
            continue
        with pytest.raises(AIQuotaExceededError):
            provider.generate_structured(
                prompt=prompt,
                response_model=PromotionCopy,
                user_id=8,
                locale="en",
                prompt_version="test-v1",
            )

    assert calls == 1


def test_structured_provider_reports_invalid_output_after_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = create_provider(InMemoryAIRequestStore())
    monkeypatch.setattr(provider, "_request", lambda **kwargs: ('{"text":""}', 0, 0))
    monkeypatch.setattr("app.llm.settings.ai_daily_quota", 1)

    with pytest.raises(AIResponseInvalidError):
        provider.generate_structured(
            prompt="Write a short promotion",
            response_model=PromotionCopy,
            user_id=9,
            locale="en",
            prompt_version="test-v1",
        )


def test_anthropic_adapter_sends_schema_and_image_as_tool_request(monkeypatch: pytest.MonkeyPatch) -> None:
    request: dict[str, object] = {}

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "content": [{"type": "tool_use", "input": {"text": "Rescue this food"}}],
                "usage": {"input_tokens": 11, "output_tokens": 4},
            }

    def post(url: str, **kwargs: object) -> ResponseStub:
        request.update(url=url, **kwargs)
        return ResponseStub()

    monkeypatch.setattr("app.infrastructure.ai.providers.httpx.post", post)
    adapter = AnthropicAdapter("test-key", "haiku-model", "sonnet-model")

    result = adapter.generate(
        prompt="Write a short message",
        response_model=PromotionCopy,
        image_data=b"image",
        image_mime_type="image/jpeg",
        model_tier="smart",
        validation_errors=None,
    )

    payload = request["json"]
    assert request["url"] == "https://api.anthropic.com/v1/messages"
    assert payload["model"] == "sonnet-model"
    assert payload["tool_choice"] == {"type": "tool", "name": "return_structured_result"}
    assert payload["tools"][0]["input_schema"] == PromotionCopy.model_json_schema()
    assert payload["messages"][0]["content"][1]["source"]["data"] == "aW1hZ2U="
    assert result == ('{"text": "Rescue this food"}', 11, 4)


def test_openai_adapter_uses_strict_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    request: dict[str, object] = {}

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [{"message": {"content": '{"text":"Rescue this food"}'}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            }

    def post(url: str, **kwargs: object) -> ResponseStub:
        request.update(url=url, **kwargs)
        return ResponseStub()

    monkeypatch.setattr("app.infrastructure.ai.providers.httpx.post", post)
    adapter = OpenAICompatibleAdapter("openai", "test-key", "https://api.openai.com/v1", "test-model")

    result = adapter.generate(
        prompt="Write a short message",
        response_model=PromotionCopy,
        image_data=None,
        image_mime_type=None,
        model_tier="fast",
        validation_errors=None,
    )

    payload = request["json"]
    assert request["url"] == "https://api.openai.com/v1/chat/completions"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert request["headers"]["Authorization"].startswith("Bearer ")
    assert result == ('{"text":"Rescue this food"}', 8, 3)
