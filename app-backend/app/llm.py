"""Structured AI orchestration with schema validation, caching, and quotas."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from redis import Redis

from app.config import settings
from app.domain.exceptions import AIProviderUnavailableError, AIResponseInvalidError
from app.infrastructure.ai.providers import (
    AIProviderAdapter,
    AnthropicAdapter,
    FakeAIProviderAdapter,
    OpenAICompatibleAdapter,
)
from app.infrastructure.ai.request_store import (
    AIRequestStore,
    InMemoryAIRequestStore,
    RedisAIRequestStore,
)

AIOutput = TypeVar("AIOutput", bound=BaseModel)
logger = logging.getLogger(__name__)
MAX_PROVIDER_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 0.25
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class StructuredAIProvider:
    """Validate provider responses and apply shared request policies."""

    def __init__(
        self,
        provider: str,
        api_key: str | None,
        base_url: str | None,
        model: str,
        request_store: AIRequestStore,
        adapter: AIProviderAdapter | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.request_store = request_store
        self.adapter = adapter or self._create_adapter(provider, api_key, base_url, model)

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[AIOutput],
        user_id: int,
        locale: str,
        prompt_version: str,
        image_data: bytes | None = None,
        image_mime_type: str | None = None,
        model_tier: str = "fast",
    ) -> AIOutput:
        if (image_data is None) != (image_mime_type is None):
            raise ValueError("Image bytes and MIME type must be provided together")
        if image_mime_type is not None and image_mime_type not in SUPPORTED_IMAGE_TYPES:
            raise ValueError("Unsupported AI image MIME type")

        cache_key = self._cache_key(
            prompt,
            response_model,
            user_id,
            locale,
            prompt_version,
            image_data,
            model_tier,
        )
        cached_response = self.request_store.get_cached_response(cache_key)
        if cached_response is not None:
            try:
                return response_model.model_validate_json(cached_response)
            except ValidationError:
                logger.warning(
                    "Discarding invalid cached AI response", extra={"response_schema": response_model.__name__}
                )

        if user_id > 0:
            self.request_store.consume_daily_quota(user_id, settings.ai_daily_quota)

        validation_errors: str | None = None
        for attempt in range(MAX_PROVIDER_ATTEMPTS):
            started_at = time.monotonic()
            try:
                response_json, input_tokens, output_tokens = self._request(
                    prompt=prompt,
                    response_model=response_model,
                    image_data=image_data,
                    image_mime_type=image_mime_type,
                    model_tier=model_tier,
                    validation_errors=validation_errors,
                )
            except httpx.HTTPError as exc:
                if attempt + 1 == MAX_PROVIDER_ATTEMPTS:
                    raise AIProviderUnavailableError("AI provider is unavailable") from exc
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            except AIResponseInvalidError:
                if attempt + 1 == MAX_PROVIDER_ATTEMPTS:
                    raise
                validation_errors = "Return one valid object matching the requested schema."
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            try:
                result = response_model.model_validate_json(response_json)
            except ValidationError as exc:
                if attempt + 1 == MAX_PROVIDER_ATTEMPTS:
                    raise AIResponseInvalidError("AI provider returned invalid structured output") from exc
                validation_errors = json.dumps(exc.errors(include_input=False), ensure_ascii=True)
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            self.request_store.cache_response(
                cache_key,
                result.model_dump_json(),
                settings.ai_cache_ttl_seconds,
            )
            logger.info(
                "Structured AI request completed",
                extra={
                    "provider": self.provider,
                    "model": self._selected_model(model_tier),
                    "response_schema": response_model.__name__,
                    "latency_ms": int((time.monotonic() - started_at) * 1000),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
            return result

        raise AIResponseInvalidError("AI provider returned invalid structured output")

    def _cache_key(
        self,
        prompt: str,
        response_model: type[BaseModel],
        user_id: int,
        locale: str,
        prompt_version: str,
        image_data: bytes | None,
        model_tier: str,
    ) -> str:
        image_digest = hashlib.sha256(image_data).hexdigest() if image_data is not None else ""
        cache_input = "\x1f".join(
            (
                str(user_id),
                locale,
                prompt_version,
                self.provider,
                self._selected_model(model_tier),
                response_model.__name__,
                prompt,
                image_digest,
            )
        )
        return hashlib.sha256(cache_input.encode("utf-8")).hexdigest()

    def _request(
        self,
        *,
        prompt: str,
        response_model: type[BaseModel],
        image_data: bytes | None,
        image_mime_type: str | None,
        model_tier: str,
        validation_errors: str | None,
    ) -> tuple[str, int, int]:
        return self.adapter.generate(
            prompt=prompt,
            response_model=response_model,
            image_data=image_data,
            image_mime_type=image_mime_type,
            model_tier=model_tier,
            validation_errors=validation_errors,
        )

    def _selected_model(self, model_tier: str) -> str:
        if self.provider == "anthropic":
            return settings.ai_model_smart if model_tier == "smart" else settings.ai_model_fast
        return self.model

    @staticmethod
    def _create_adapter(
        provider: str,
        api_key: str | None,
        base_url: str | None,
        model: str,
    ) -> AIProviderAdapter:
        if provider == "mock":
            return FakeAIProviderAdapter()
        if provider == "anthropic":
            return AnthropicAdapter(api_key, settings.ai_model_fast, settings.ai_model_smart)
        return OpenAICompatibleAdapter(provider, api_key, base_url or DEFAULT_OPENAI_BASE_URL, model)


def build_client(request_store: AIRequestStore | None = None) -> StructuredAIProvider:
    """Compose the configured provider and its request policy store."""
    provider = settings.llm_provider
    if request_store is None:
        if provider == "mock":
            request_store = InMemoryAIRequestStore()
        else:
            request_store = RedisAIRequestStore(Redis.from_url(settings.redis_url, decode_responses=True))

    if provider == "anthropic":
        return StructuredAIProvider(
            provider,
            settings.anthropic_api_key,
            None,
            settings.ai_model_fast,
            request_store,
        )
    if provider == "openai":
        return StructuredAIProvider(
            provider,
            settings.llm_api_key or settings.openai_api_key,
            DEFAULT_OPENAI_BASE_URL,
            settings.llm_model,
            request_store,
        )
    if provider == "mock":
        return StructuredAIProvider(provider, None, None, "deterministic-fake", request_store)
    return StructuredAIProvider(
        provider,
        settings.llm_api_key,
        settings.llm_base_url,
        settings.llm_model,
        request_store,
    )
