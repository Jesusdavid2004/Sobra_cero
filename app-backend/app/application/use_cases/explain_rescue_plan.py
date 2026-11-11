from app.application.ai_dto import RescueExplanation
from app.application.dto import Actor
from app.application.ports import AIProvider, RescueLotGateway, RescuePlanRepository
from app.application.rescue_explanation_prompt import (
    RESCUE_EXPLANATION_PROMPT_VERSION,
    build_rescue_explanation_prompt,
)
from app.domain.exceptions import RescuePermissionError, RescuePlanNotFoundError


class ExplainRescuePlan:
    """Reword a plan's deterministic reasons; numbers and decisions never come from the model."""

    def __init__(self, lots: RescueLotGateway, plans: RescuePlanRepository, ai_provider: AIProvider) -> None:
        self._lots = lots
        self._plans = plans
        self._ai_provider = ai_provider

    def execute(self, plan_id: int, actor: Actor, language: str) -> str:
        if not actor.can_manage_shops:
            raise RescuePermissionError("Business account required")
        plan = self._plans.get(plan_id)
        if plan is None:
            raise RescuePlanNotFoundError("Rescue plan not found")
        owner_id = self._lots.get_shop_owner_id(plan.shop_id)
        if owner_id != actor.user_id and not actor.is_admin:
            raise RescuePlanNotFoundError("Rescue plan not found")
        explanation = self._ai_provider.generate_structured(
            prompt=build_rescue_explanation_prompt(plan, language),
            response_model=RescueExplanation,
            user_id=actor.user_id,
            locale=language,
            prompt_version=RESCUE_EXPLANATION_PROMPT_VERSION,
            model_tier="fast",
        )
        return explanation.text
