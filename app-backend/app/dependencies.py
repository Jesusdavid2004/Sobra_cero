"""Application composition root for request-scoped dependencies."""

from functools import lru_cache

from fastapi import Depends
from redis import Redis
from sqlalchemy.orm import Session

from app.application.ports import LotEventPublisher, RescueAnalyzer, SessionManager
from app.application.use_cases.auth import (
    Login,
    LogoutSession,
    RefreshSession,
    RegisterUser,
)
from app.application.use_cases.calculate_waste_risk import CalculateWasteRiskUseCase
from app.application.use_cases.explain_rescue_plan import ExplainRescuePlan
from app.application.use_cases.import_sales_history import ImportSalesHistoryCsv
from app.application.use_cases.lot_timeline import GetLotTimeline
from app.application.use_cases.rescue_plan import (
    DecideRescuePlan,
    GenerateRescuePlan,
    ListRescuePlans,
)
from app.application.use_cases.shop_impact import GetShopImpact
from app.application.use_cases.simulate_rescue_plan import SimulateRescuePlan
from app.application.use_cases.train_sales_forecast_model import TrainSalesForecastModel
from app.auth import password_hasher
from app.config import settings
from app.db import get_db
from app.infrastructure.analysis.fallback_analyzer import FallbackRescueAnalyzer
from app.infrastructure.analysis.grpc_analyzer import (
    GrpcRescueAnalyzer,
    create_grpc_analyzer,
)
from app.infrastructure.analysis.local_analyzer import LocalRescueAnalyzer
from app.infrastructure.auth.refresh_sessions import (
    JwtRedisSessionManager,
    RedisRefreshTokenStore,
)
from app.infrastructure.prediction.weekday_sales_forecast import (
    WeekdaySalesForecastModel,
    WeekdaySalesForecastTrainer,
)
from app.infrastructure.prediction.weighted_moving_average import (
    WeightedMovingAveragePredictionModel,
)
from app.infrastructure.realtime.hub import LotStreamHub
from app.infrastructure.realtime.publishers import (
    InMemoryLotEventPublisher,
    RedisLotEventPublisher,
)
from app.infrastructure.repositories.impact_repository import SqlAlchemyImpactRepository
from app.infrastructure.repositories.rescue_plan_repository import (
    SqlAlchemyRescueLotGateway,
    SqlAlchemyRescuePlanRepository,
    SqlAlchemyUnitOfWork,
)
from app.infrastructure.repositories.sales_forecast_model_repository import (
    SqlAlchemySalesForecastModelRepository,
)
from app.infrastructure.repositories.sales_history_repository import (
    PostgresSalesHistoryRepository,
)
from app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyLotTimelineSource,
)
from app.infrastructure.repositories.user_repository import SqlAlchemyAuthUserRepository
from app.llm import build_client


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_session_manager() -> SessionManager:
    return JwtRedisSessionManager(
        secret=settings.jwt_secret,
        token_store=RedisRefreshTokenStore(get_redis_client()),
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
    model_repository = build_sales_forecast_model_repository(db)
    artifact = model_repository.get_active_model()
    return CalculateWasteRiskUseCase(
        repository=build_sales_history_repository(db),
        prediction_model=(
            WeekdaySalesForecastModel(artifact) if artifact is not None else WeightedMovingAveragePredictionModel()
        ),
        ai_provider=build_client(),
    )


def build_sales_history_repository(db: Session) -> PostgresSalesHistoryRepository:
    return PostgresSalesHistoryRepository(db)


def build_generate_rescue_plan_use_case(db: Session) -> GenerateRescuePlan:
    return GenerateRescuePlan(
        lots=SqlAlchemyRescueLotGateway(db),
        plans=SqlAlchemyRescuePlanRepository(db),
        history=build_sales_history_repository(db),
        models=build_sales_forecast_model_repository(db),
        analyzer=build_rescue_analyzer(),
        unit_of_work=SqlAlchemyUnitOfWork(db),
    )


@lru_cache(maxsize=1)
def get_grpc_rescue_analyzer() -> GrpcRescueAnalyzer:
    assert settings.analysis_grpc_target and settings.analysis_shared_token
    return create_grpc_analyzer(
        settings.analysis_grpc_target, settings.analysis_shared_token, settings.analysis_grpc_timeout_seconds
    )


def build_rescue_analyzer() -> RescueAnalyzer:
    local = LocalRescueAnalyzer()
    if not settings.analysis_grpc_target:
        return local
    return FallbackRescueAnalyzer(get_grpc_rescue_analyzer(), local)


@lru_cache(maxsize=1)
def get_lot_stream_hub() -> LotStreamHub:
    return LotStreamHub()


@lru_cache(maxsize=1)
def get_lot_event_publisher() -> LotEventPublisher:
    if settings.realtime_broker == "redis":
        return RedisLotEventPublisher(Redis.from_url(settings.redis_url))
    return InMemoryLotEventPublisher(get_lot_stream_hub())


def build_simulate_rescue_plan_use_case(db: Session) -> SimulateRescuePlan:
    return SimulateRescuePlan(SqlAlchemyRescueLotGateway(db), SqlAlchemyRescuePlanRepository(db))


def build_get_lot_timeline_use_case(db: Session) -> GetLotTimeline:
    return GetLotTimeline(SqlAlchemyRescueLotGateway(db), SqlAlchemyLotTimelineSource(db))


def build_get_shop_impact_use_case(db: Session) -> GetShopImpact:
    return GetShopImpact(SqlAlchemyRescueLotGateway(db), SqlAlchemyImpactRepository(db))


def build_explain_rescue_plan_use_case(db: Session) -> ExplainRescuePlan:
    return ExplainRescuePlan(
        lots=SqlAlchemyRescueLotGateway(db),
        plans=SqlAlchemyRescuePlanRepository(db),
        ai_provider=build_client(),
    )


def build_decide_rescue_plan_use_case(db: Session) -> DecideRescuePlan:
    return DecideRescuePlan(
        lots=SqlAlchemyRescueLotGateway(db),
        plans=SqlAlchemyRescuePlanRepository(db),
        unit_of_work=SqlAlchemyUnitOfWork(db),
    )


def build_list_rescue_plans_use_case(db: Session) -> ListRescuePlans:
    return ListRescuePlans(SqlAlchemyRescueLotGateway(db), SqlAlchemyRescuePlanRepository(db))


def build_import_sales_history_csv_use_case(db: Session) -> ImportSalesHistoryCsv:
    return ImportSalesHistoryCsv(repository=build_sales_history_repository(db))


def build_sales_forecast_model_repository(db: Session) -> SqlAlchemySalesForecastModelRepository:
    return SqlAlchemySalesForecastModelRepository(db)


def build_train_sales_forecast_model_use_case(db: Session) -> TrainSalesForecastModel:
    return TrainSalesForecastModel(
        repository=build_sales_forecast_model_repository(db),
        trainer=WeekdaySalesForecastTrainer(),
    )
