"""Application composition root for request-scoped dependencies."""

from functools import lru_cache

from fastapi import Depends
from redis import Redis
from sqlalchemy.orm import Session

from app.application.ports import SessionManager
from app.application.use_cases.auth import (
    Login,
    LogoutSession,
    RefreshSession,
    RegisterUser,
)
from app.application.use_cases.calculate_waste_risk import CalculateWasteRiskUseCase
from app.application.use_cases.import_sales_history import ImportSalesHistoryCsv
from app.auth import password_hasher
from app.config import settings
from app.db import get_db
from app.infrastructure.auth.refresh_sessions import (
    JwtRedisSessionManager,
    RedisRefreshTokenStore,
)
from app.infrastructure.prediction.weighted_moving_average import (
    WeightedMovingAveragePredictionModel,
)
from app.infrastructure.repositories.sales_history_repository import (
    PostgresSalesHistoryRepository,
)
from app.infrastructure.repositories.user_repository import SqlAlchemyAuthUserRepository
from app.llm import build_client


@lru_cache(maxsize=1)
def _redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_session_manager() -> SessionManager:
    return JwtRedisSessionManager(
        secret=settings.jwt_secret,
        token_store=RedisRefreshTokenStore(_redis_client()),
        access_token_minutes=settings.access_token_expire_minutes,
        refresh_token_days=settings.refresh_token_expire_days,
    )


def get_register_user_use_case(
    db: Session = Depends(get_db),
    sessions: SessionManager = Depends(get_session_manager),
) -> RegisterUser:
    return RegisterUser(SqlAlchemyAuthUserRepository(db), password_hasher, sessions)


def get_login_use_case(
    db: Session = Depends(get_db),
    sessions: SessionManager = Depends(get_session_manager),
) -> Login:
    return Login(SqlAlchemyAuthUserRepository(db), password_hasher, sessions)


def get_refresh_session_use_case(
    sessions: SessionManager = Depends(get_session_manager),
) -> RefreshSession:
    return RefreshSession(sessions)


def get_logout_session_use_case(
    sessions: SessionManager = Depends(get_session_manager),
) -> LogoutSession:
    return LogoutSession(sessions)


def build_calculate_waste_risk_use_case(db: Session) -> CalculateWasteRiskUseCase:
    return CalculateWasteRiskUseCase(
        repository=build_sales_history_repository(db),
        prediction_model=WeightedMovingAveragePredictionModel(),
        ai_provider=build_client(),
    )


def build_sales_history_repository(db: Session) -> PostgresSalesHistoryRepository:
    return PostgresSalesHistoryRepository(db)


def build_import_sales_history_csv_use_case(db: Session) -> ImportSalesHistoryCsv:
    return ImportSalesHistoryCsv(repository=build_sales_history_repository(db))
