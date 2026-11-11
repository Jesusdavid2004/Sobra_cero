from datetime import date, datetime
from typing import Mapping, Protocol, Sequence, TypeVar

from pydantic import BaseModel

from app.application.dto import (
    AuthUser,
    DailySales,
    LotAnalysis,
    LotAnalysisInput,
    LotSnapshot,
    PredictionEstimate,
    SalesForecastEvaluation,
    SalesForecastModelArtifact,
    SessionTokens,
    UserRole,
)
from app.domain.events import LotStockChanged
from app.domain.rescue import RescuePlan, RescuePlanStatus


class SalesHistoryRepository(Protocol):
    def list_for_product(self, product_id: int, since: date) -> list[DailySales]: ...

    def upsert_many(self, product_id: int, entries: Sequence[DailySales]) -> tuple[int, int]: ...

    def save_prediction(
        self,
        *,
        product_id: int,
        lot_id: int,
        risk_score: int,
        units_at_risk: float,
        expected_sales: float,
        recommendation: str,
        model_version: str,
    ) -> None: ...


class PredictionModel(Protocol):
    def predict(
        self,
        history: Sequence[DailySales],
        current_stock: int,
        days_remaining: int,
        today: date,
    ) -> PredictionEstimate: ...


class SalesForecastTrainer(Protocol):
    def train(self, histories: Sequence[Sequence[DailySales]]) -> SalesForecastEvaluation: ...


class SalesForecastModelRepository(Protocol):
    def list_training_history(self) -> list[list[DailySales]]: ...

    def get_active_model(self) -> SalesForecastModelArtifact | None: ...

    def save_evaluation(self, evaluation: SalesForecastEvaluation, *, activate: bool) -> None: ...


AIOutput = TypeVar("AIOutput", bound=BaseModel)


class AIProvider(Protocol):
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
    ) -> AIOutput: ...


class LotEventPublisher(Protocol):
    def publish(self, event: LotStockChanged) -> None: ...


class AuthUserRepository(Protocol):
    def find_by_email(self, email: str) -> AuthUser | None: ...

    def create_user(self, email: str, password_hash: str, role: UserRole) -> AuthUser: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class SessionManager(Protocol):
    def issue(self, user_id: int) -> SessionTokens: ...

    def rotate(self, refresh_token: str) -> SessionTokens: ...

    def revoke(self, refresh_token: str) -> None: ...


class RefreshTokenStore(Protocol):
    def issue(self, token_id: str, user_id: int, ttl_seconds: int) -> bool: ...

    def rotate(self, old_token_id: str, new_token_id: str, user_id: int, ttl_seconds: int) -> bool: ...

    def revoke(self, token_id: str, user_id: int) -> None: ...


class UnitOfWork(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class RescueAnalyzer(Protocol):
    def analyze_lot(self, request_id: str, lot: LotAnalysisInput) -> LotAnalysis: ...

    def analyze_shop(self, request_id: str, lots: Sequence[LotAnalysisInput]) -> list[LotAnalysis]: ...


class RescueLotGateway(Protocol):
    def get_snapshot(self, lot_id: int) -> LotSnapshot | None: ...

    def get_shop_owner_id(self, shop_id: int) -> int | None: ...

    def apply_discount_if_unchanged(self, lot_id: int, expected_quantity: int, discount_percent: int) -> bool: ...


class RescuePlanRepository(Protocol):
    def add(self, plan: RescuePlan) -> RescuePlan: ...

    def get(self, plan_id: int) -> RescuePlan | None: ...

    def list_for_shop(self, shop_id: int, status: RescuePlanStatus | None) -> list[RescuePlan]: ...

    def supersede_pending_for_lot(self, lot_id: int) -> list[int]: ...

    def mark_decided(self, plan_id: int, status: RescuePlanStatus, actor_id: int, now: datetime) -> bool: ...

    def record_event(
        self, plan_id: int, event_type: str, actor_id: int | None, payload: Mapping[str, object]
    ) -> None: ...
