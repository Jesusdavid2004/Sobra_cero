import httpx

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
from app.application.use_cases.discover_lots import DiscoverLots
from app.application.use_cases.donation_offers import (
    ConfirmDonationDelivery,
    CreateDonationOffer,
    DraftDonationMessage,
    FindDonationReceivers,
    GetMyReceiver,
    ListLotDonationOffers,
    ListReceiverOffers,
    RegisterReceiver,
    RespondToDonationOffer,
)
from app.application.use_cases.explain_rescue_plan import ExplainRescuePlan
from app.application.use_cases.get_public_shop import GetPublicShop
from app.application.use_cases.import_sales_history import ImportSalesHistoryCsv
from app.application.use_cases.inventory import DiagnoseShop, ListShopWaste, RecordWaste
from app.application.use_cases.lot_timeline import GetLotTimeline
from app.application.use_cases.map_places import (
    GetMapOpportunities,
    ListMapPlaces,
    ListPublicPromotions,
    SearchGeocode,
)
from app.application.use_cases.parse_discovery_intent import ParseDiscoveryIntent
from app.application.use_cases.rescue_plan import (
    DecideRescuePlan,
    GenerateRescuePlan,
    ListRescuePlans,
)
from app.application.use_cases.scanner import (
    GetPriceHistory,
    GetScannerSummary,
    ListCollectedProducts,
    ListDiscoveredBusinesses,
    ListExecutionRecords,
    ListExecutions,
    ListScannerSources,
    RecordTermsReview,
    RegisterSource,
    RunDueSources,
    RunSourceNow,
    SetSourceEnabled,
    SetSourceSchedule,
    VerifyBusiness,
)
from app.application.use_cases.shop_impact import GetShopImpact
from app.application.use_cases.simulate_rescue_plan import SimulateRescuePlan
from app.application.use_cases.train_sales_forecast_model import TrainSalesForecastModel
from app.auth import password_hasher
from app.config import settings
from app.config import settings as app_settings
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
from app.infrastructure.geocoding import FakeGeocoder, NominatimGeocoder
from app.infrastructure.network import resolve_host
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
from app.infrastructure.repositories.discovery_repository import (
    SqlAlchemyDiscoveryLotSource,
)
from app.infrastructure.repositories.donation_repository import (
    SqlAlchemyDonationRepository,
)
from app.infrastructure.repositories.impact_repository import SqlAlchemyImpactRepository
from app.infrastructure.repositories.inventory_repository import (
    SqlAlchemyInventoryRepository,
)
from app.infrastructure.repositories.map_repository import SqlAlchemyMapRepository
from app.infrastructure.repositories.public_shop_repository import (
    SqlAlchemyPublicShopRepository,
)
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
from app.infrastructure.repositories.scanner_repository import (
    SqlAlchemyScannerRepository,
)
from app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyLotTimelineSource,
)
from app.infrastructure.repositories.user_repository import SqlAlchemyAuthUserRepository
from app.infrastructure.scanner_runner import SubprocessSourceRunner
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


def build_get_public_shop_use_case(db: Session) -> GetPublicShop:
    return GetPublicShop(SqlAlchemyPublicShopRepository(db))


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


def build_discover_lots_use_case(db: Session) -> DiscoverLots:
    return DiscoverLots(SqlAlchemyDiscoveryLotSource(db))


def build_parse_discovery_intent_use_case() -> ParseDiscoveryIntent:
    return ParseDiscoveryIntent(build_client())


def build_find_donation_receivers_use_case(db: Session) -> FindDonationReceivers:
    return FindDonationReceivers(SqlAlchemyDonationRepository(db))


def build_create_donation_offer_use_case(db: Session) -> CreateDonationOffer:
    return CreateDonationOffer(SqlAlchemyDonationRepository(db), SqlAlchemyUnitOfWork(db))


def build_draft_donation_message_use_case(db: Session) -> DraftDonationMessage:
    return DraftDonationMessage(SqlAlchemyDonationRepository(db), build_client())


def build_respond_to_donation_offer_use_case(db: Session) -> RespondToDonationOffer:
    return RespondToDonationOffer(SqlAlchemyDonationRepository(db), SqlAlchemyUnitOfWork(db))


def build_confirm_donation_delivery_use_case(db: Session) -> ConfirmDonationDelivery:
    return ConfirmDonationDelivery(SqlAlchemyDonationRepository(db), SqlAlchemyUnitOfWork(db))


def build_register_receiver_use_case(db: Session) -> RegisterReceiver:
    return RegisterReceiver(SqlAlchemyDonationRepository(db), SqlAlchemyUnitOfWork(db))


def build_get_my_receiver_use_case(db: Session) -> GetMyReceiver:
    return GetMyReceiver(SqlAlchemyDonationRepository(db))


def build_list_receiver_offers_use_case(db: Session) -> ListReceiverOffers:
    return ListReceiverOffers(SqlAlchemyDonationRepository(db))


def build_list_lot_donation_offers_use_case(db: Session) -> ListLotDonationOffers:
    return ListLotDonationOffers(SqlAlchemyDonationRepository(db))


def _scanner(db: Session) -> SqlAlchemyScannerRepository:
    return SqlAlchemyScannerRepository(db)


def build_list_sources_use_case(db: Session) -> ListScannerSources:
    return ListScannerSources(_scanner(db))


def build_register_source_use_case(db: Session) -> RegisterSource:
    allowed = [item.strip() for item in app_settings.scraper_allowed_domains.split(",") if item.strip()]
    enforce = not (app_settings.scraper_disable_url_policy and app_settings.app_environment != "production")
    return RegisterSource(_scanner(db), SqlAlchemyUnitOfWork(db), allowed, resolve_host, enforce)


def build_record_terms_review_use_case(db: Session) -> RecordTermsReview:
    return RecordTermsReview(_scanner(db), SqlAlchemyUnitOfWork(db))


def build_set_source_enabled_use_case(db: Session) -> SetSourceEnabled:
    return SetSourceEnabled(_scanner(db), SqlAlchemyUnitOfWork(db))


def build_set_source_schedule_use_case(db: Session) -> SetSourceSchedule:
    return SetSourceSchedule(_scanner(db), SqlAlchemyUnitOfWork(db))


def build_run_source_now_use_case(db: Session) -> RunSourceNow:
    return RunSourceNow(_scanner(db), SqlAlchemyUnitOfWork(db), SubprocessSourceRunner())


def build_run_due_sources_use_case(db: Session) -> RunDueSources:
    return RunDueSources(_scanner(db), SqlAlchemyUnitOfWork(db), SubprocessSourceRunner())


def build_get_scanner_summary_use_case(db: Session) -> GetScannerSummary:
    return GetScannerSummary(_scanner(db))


def build_list_executions_use_case(db: Session) -> ListExecutions:
    return ListExecutions(_scanner(db))


def build_list_execution_records_use_case(db: Session) -> ListExecutionRecords:
    return ListExecutionRecords(_scanner(db))


def build_list_products_use_case(db: Session) -> ListCollectedProducts:
    return ListCollectedProducts(_scanner(db))


def build_get_price_history_use_case(db: Session) -> GetPriceHistory:
    return GetPriceHistory(_scanner(db))


def build_list_businesses_use_case(db: Session) -> ListDiscoveredBusinesses:
    return ListDiscoveredBusinesses(_scanner(db))


def build_verify_business_use_case(db: Session) -> VerifyBusiness:
    return VerifyBusiness(_scanner(db), SqlAlchemyUnitOfWork(db))


def build_list_map_places_use_case(db: Session) -> ListMapPlaces:
    return ListMapPlaces(SqlAlchemyMapRepository(db))


def build_get_map_opportunities_use_case(db: Session) -> GetMapOpportunities:
    return GetMapOpportunities(SqlAlchemyMapRepository(db))


def build_list_public_promotions_use_case(db: Session) -> ListPublicPromotions:
    return ListPublicPromotions(SqlAlchemyMapRepository(db))


_nominatim: NominatimGeocoder | None = None


def build_search_geocode_use_case() -> SearchGeocode:
    """One geocoder per process, so its rate limit and cache are shared by every request."""
    global _nominatim
    if app_settings.geocoder_provider == "fake":
        return SearchGeocode(FakeGeocoder())
    if _nominatim is None:
        _nominatim = NominatimGeocoder(httpx.Client(), app_settings.geocoder_user_agent, app_settings.geocoder_base_url)
    return SearchGeocode(_nominatim)


def build_record_waste_use_case(db: Session) -> RecordWaste:
    return RecordWaste(SqlAlchemyInventoryRepository(db), SqlAlchemyUnitOfWork(db))


def build_list_shop_waste_use_case(db: Session) -> ListShopWaste:
    return ListShopWaste(SqlAlchemyInventoryRepository(db))


def build_diagnose_shop_use_case(db: Session) -> DiagnoseShop:
    return DiagnoseShop(SqlAlchemyInventoryRepository(db), build_client())
