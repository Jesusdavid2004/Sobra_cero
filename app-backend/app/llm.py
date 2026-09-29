"""Abstract LLM client so the generative provider can be swapped freely.

Supported providers:
- ``mock``: deterministic fallback, no network, no API key (CI safe).
- ``openai``: OpenAI's hosted API.
- any other value (``ollama``, ``groq``, ``openrouter``, ``gemini``...):
  treated as an OpenAI-compatible ``/chat/completions`` endpoint configured
  through ``LLM_BASE_URL`` and ``LLM_MODEL``.
"""

from __future__ import annotations

import abc

import httpx

from app.config import settings


class BaseLLMClient(abc.ABC):
    """Contract for generative text providers."""

    @abc.abstractmethod
    def complete(self, prompt: str) -> str:
        """Return the model completion for the given prompt."""


class OpenAICompatibleClient(BaseLLMClient):
    """Client for any OpenAI-compatible chat completions endpoint."""

    def __init__(self, api_key: str | None, base_url: str | None, model: str) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a food-rescue marketing copywriter."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 160,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


class MockLLMClient(BaseLLMClient):
    """Deterministic fallback that never requires network access or API keys."""

    def complete(self, prompt: str) -> str:
        first_line = prompt.splitlines()[0] if prompt.splitlines() else "Rescue food"
        return f"{first_line[:70]} - grab it before it expires!"


def build_client() -> BaseLLMClient:
    """Instantiate the client configured through the environment."""
    if settings.llm_provider == "mock":
        return MockLLMClient()
    if settings.llm_provider == "openai":
        return OpenAICompatibleClient(
            settings.llm_api_key or settings.openai_api_key,
            "https://api.openai.com/v1",
            settings.llm_model,
        )
    return OpenAICompatibleClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
