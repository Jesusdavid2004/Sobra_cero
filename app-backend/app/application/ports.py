from datetime import date
from typing import Protocol, Sequence

from app.application.dto import (
    AuthUser,
    DailySales,
    PredictionEstimate,
    SessionTokens,
    UserRole,
)


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
    ) -> None: ...


class PredictionModel(Protocol):
    def predict(
        self,
        history: Sequence[DailySales],
        current_stock: int,
        days_remaining: int,
        today: date,
    ) -> PredictionEstimate: ...


class AIProvider(Protocol):
    def complete(self, prompt: str) -> str: ...


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
