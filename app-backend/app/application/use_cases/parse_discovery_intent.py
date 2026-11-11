from app.application.ai_dto import DiscoveryIntent
from app.application.discovery_intent_prompt import (
    DISCOVERY_INTENT_PROMPT_VERSION,
    build_discovery_intent_prompt,
)
from app.application.ports import AIProvider


class ParseDiscoveryIntent:
    """Read a free-text pickup request into constraints. The customer reviews them before any search runs."""

    def __init__(self, ai_provider: AIProvider) -> None:
        self._ai_provider = ai_provider

    def execute(self, text: str, user_id: int, language: str) -> DiscoveryIntent:
        return self._ai_provider.generate_structured(
            prompt=build_discovery_intent_prompt(text, language),
            response_model=DiscoveryIntent,
            user_id=user_id,
            locale=language,
            prompt_version=DISCOVERY_INTENT_PROMPT_VERSION,
            model_tier="fast",
        )
