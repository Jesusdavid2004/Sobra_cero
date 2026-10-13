import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from datetime import time as datetime_time
from datetime import timedelta, timezone
from uuid import uuid4

from botocore.exceptions import BotoCoreError
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from kombu.exceptions import OperationalError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.application.ai_dto import ExpiryDateRead
from app.application.dto import DailySales
from app.auth import current_user
from app.config import settings
from app.db import engine, get_db
from app.dependencies import (
    build_calculate_waste_risk_use_case,
    build_import_sales_history_csv_use_case,
    build_sales_history_repository,
    build_train_sales_forecast_model_use_case,
)
from app.domain.exceptions import (
    AIProviderUnavailableError,
    AIQuotaExceededError,
    AIResponseInvalidError,
    BatchAlreadyReservedError,
    InsufficientSalesHistoryError,
    InsufficientSalesTrainingDataError,
    InvalidImageError,
    InvalidSalesHistoryCsvError,
    RefreshSessionStoreUnavailableError,
)
from app.domain.rules import (
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_SALES_HISTORY_IMPORT_BYTES,
    MIN_EXPIRY_OCR_CONFIDENCE,
)
from app.llm import build_client
from app.migrations import upgrade_database_schema
from app.models import (
    Donation,
    ExpiryScanSuggestion,
    Lot,
    Product,
    Promotion,
    Reservation,
    Shop,
    User,
)
from app.presentation.routers.auth import router as auth_router
from app.prompts import EXPIRY_SCAN_PROMPT_VERSION, build_expiry_scan_prompt
from app.schemas import (
    DonationCreate,
    ExpiryScanSuggestionOut,
    LotCreate,
    LotOut,
    PickupConfirmation,
    ProductCreate,
    ProductOut,
    PromotionOut,
    ReservationCreate,
    SalesForecastTrainingOut,
    SalesHistoryCreate,
    SalesHistoryCreated,
    ShopCreate,
    ShopOut,
    WasteRiskOut,
)
from app.services import (
    build_promotions,
    cancel_lot,
    cancel_reservation,
    confirm_reservation_pickup,
    donate_lot,
    reserve_lot,
)
from app.storage import get_storage, sanitize_image
from app.synthetic_sales import DEFAULT_HISTORY_DAYS, generate_shop_sales_history
from app.worker import generate_promotions_task

upgrade_database_schema(engine.url)
app = FastAPI(title="SobraCero API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.exception_handler(InsufficientSalesHistoryError)
@app.exception_handler(BatchAlreadyReservedError)
def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    status_code = 409 if isinstance(exc, BatchAlreadyReservedError) else 422
    error_code = (
        "batch_already_reserved" if isinstance(exc, BatchAlreadyReservedError) else "insufficient_sales_history"
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc), "code": error_code})


@app.exception_handler(RefreshSessionStoreUnavailableError)
def handle_refresh_session_store_error(request: Request, exc: RefreshSessionStoreUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Authentication service is unavailable"})


@app.exception_handler(AIQuotaExceededError)
def handle_ai_quota_error(_request: Request, _exc: AIQuotaExceededError) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Daily AI request allowance exceeded", "code": "ai_quota_exceeded"},
    )


@app.exception_handler(AIResponseInvalidError)
def handle_invalid_ai_response(_request: Request, _exc: AIResponseInvalidError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "AI provider returned an invalid response", "code": "ai_response_invalid"},
    )


@app.exception_handler(AIProviderUnavailableError)
def handle_ai_provider_error(_request: Request, _exc: AIProviderUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "AI service is unavailable", "code": "ai_provider_unavailable"},
    )


@app.exception_handler(InvalidSalesHistoryCsvError)
def handle_invalid_sales_history_csv(request: Request, exc: InvalidSalesHistoryCsvError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "code": "invalid_sales_history_csv"},
    )


@app.exception_handler(InsufficientSalesTrainingDataError)
def handle_insufficient_sales_training_data(request: Request, exc: InsufficientSalesTrainingDataError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "code": "insufficient_sales_training_data"},
    )


_rate_buckets: dict[str, list[float]] = defaultdict(list)
MODEL_TRAINING_REQUESTS_PER_MINUTE = 2


def rate_limited(limit: int, window_seconds: int = 60) -> Callable[[Request], None]:
    """Simple in-memory sliding-window rate limiter keyed by client IP."""

    def dependency(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        key = f"{client_host}:{route_path}"
        now = time.time()
        bucket = _rate_buckets[key]
        bucket[:] = [ts for ts in bucket if now - ts < window_seconds]
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        bucket.append(now)

    return dependency


def lot_response(lot: Lot) -> LotOut:
    image_url = lot.image_url
    if lot.image_key:
        try:
            image_url = get_storage().signed_url(lot.image_key)
        except BotoCoreError as exc:
            raise HTTPException(status_code=503, detail="Image storage unavailable") from exc
    return LotOut.model_validate(lot).model_copy(update={"image_url": image_url})


def require_business(user: User) -> None:
    if user.role != "business" and not user.is_admin:
        raise HTTPException(403, "Business account required")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/shops", response_model=ShopOut, status_code=201)
def create_shop(data: ShopCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Shop:
    require_business(user)
    shop = Shop(**data.model_dump(), owner_id=user.id)
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


@app.get("/api/v1/shops", response_model=list[ShopOut])
def shops(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Shop]:
    query = select(Shop)
    if not user.is_admin:
        query = query.where(Shop.owner_id == user.id)
    return list(db.scalars(query.order_by(Shop.id)))


@app.post("/api/v1/shops/{shop_id}/products", response_model=ProductOut, status_code=201)
def create_product(
    shop_id: int, data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Product:
    require_business(user)
    shop = db.get(Shop, shop_id)
    if not shop or shop.owner_id != user.id:
        raise HTTPException(404, "Shop not found")
    product = Product(shop_id=shop_id, **data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.get("/api/v1/shops/{shop_id}/products", response_model=list[ProductOut])
def shop_products(
    shop_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Product]:
    shop = db.get(Shop, shop_id)
    if not shop or (shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Shop not found")
    return list(db.scalars(select(Product).where(Product.shop_id == shop_id)))


@app.post("/api/v1/products/{product_id}/sales-history", response_model=SalesHistoryCreated, status_code=201)
def add_sales_history(
    product_id: int,
    data: SalesHistoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SalesHistoryCreated:
    require_business(user)
    product = db.get(Product, product_id)
    shop = db.get(Shop, product.shop_id) if product else None
    if not shop or (shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Product not found")
    seen_dates = set()
    entries = []
    for entry in data.entries:
        if entry.sales_date in seen_dates:
            raise HTTPException(422, "Each sales date may only appear once per request")
        seen_dates.add(entry.sales_date)
        entries.append(
            DailySales(
                sales_date=entry.sales_date,
                units_sold=entry.units_sold,
                had_promotion=entry.had_promotion,
            )
        )
    created, existing = build_sales_history_repository(db).upsert_many(
        product_id,
        [
            DailySales(
                sales_date=entry.sales_date,
                units_sold=entry.units_sold,
                had_promotion=entry.had_promotion,
            )
            for entry in entries
        ],
    )
    return SalesHistoryCreated(created=created, existing=existing)


@app.post(
    "/api/v1/products/{product_id}/sales-history/csv",
    response_model=SalesHistoryCreated,
    status_code=201,
    dependencies=[Depends(rate_limited(10, 60))],
)
async def import_sales_history_csv(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SalesHistoryCreated:
    require_business(user)
    product = db.get(Product, product_id)
    shop = db.get(Shop, product.shop_id) if product else None
    if not shop or (shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Product not found")
    content = await file.read(MAX_SALES_HISTORY_IMPORT_BYTES + 1)
    if len(content) > MAX_SALES_HISTORY_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Sales history CSV is too large")
    created, existing = build_import_sales_history_csv_use_case(db).execute(product_id, content)
    return SalesHistoryCreated(created=created, existing=existing)


@app.post("/api/v1/shops/{shop_id}/sales-history/sample", response_model=SalesHistoryCreated, status_code=201)
def load_sample_sales_history(
    shop_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SalesHistoryCreated:
    require_business(user)
    shop = db.get(Shop, shop_id)
    if not shop or shop.owner_id != user.id:
        raise HTTPException(404, "Shop not found")
    products = db.scalars(select(Product).where(Product.shop_id == shop_id)).all()
    if not products:
        raise HTTPException(409, "Create a product before loading sample sales history")
    created, existing = generate_shop_sales_history(db, shop_id, days=DEFAULT_HISTORY_DAYS)
    return SalesHistoryCreated(created=created, existing=existing)


@app.get("/api/v1/shops/{shop_id}/waste-risk", response_model=list[WasteRiskOut])
def shop_waste_risk(
    shop_id: int,
    language: str = Query("en", pattern="^(en|es)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[WasteRiskOut]:
    require_business(user)
    shop = db.get(Shop, shop_id)
    if not shop or (shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Shop not found")
    lots = db.scalars(select(Lot).where(Lot.shop_id == shop_id, Lot.quantity > 0).order_by(Lot.expires_at)).all()
    calculate_risk = build_calculate_waste_risk_use_case(db)
    results = []
    for lot in lots:
        expires_at = lot.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            continue
        result = calculate_risk.execute(
            product_id=lot.product_id,
            product_name=lot.product.name,
            business_type=lot.shop.business_type,
            lot_id=lot.id,
            current_stock=lot.quantity,
            expires_at=expires_at,
            language=language,
            user_id=user.id,
        )
        results.append(
            WasteRiskOut(
                product_id=result.product_id,
                product_name=result.product_name,
                lot_id=result.lot_id,
                current_stock=result.current_stock,
                days_remaining=result.days_remaining,
                data_points=result.data_points,
                average_daily_sales=result.average_daily_sales,
                expected_sales=result.expected_sales,
                units_at_risk=result.units_at_risk,
                risk_score=result.risk_score.value,
                risk_level=result.risk_score.level,
                recommendation=result.recommendation,
                calculated_at=datetime.now(timezone.utc),
                prediction_model=result.model_version,
            )
        )
    return results


@app.post("/api/v1/lots", response_model=LotOut, status_code=201)
def create_lot(data: LotCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> LotOut:
    require_business(user)
    shop = db.get(Shop, data.shop_id)
    if not shop or shop.owner_id != user.id:
        raise HTTPException(404, "Shop not found")
    product = db.get(Product, data.product_id)
    if not product or product.shop_id != shop.id:
        raise HTTPException(404, "Product not found")
    lot = Lot(**data.model_dump())
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot_response(lot)


@app.post(
    "/api/v1/lots/{lot_id}/image",
    response_model=LotOut,
    dependencies=[Depends(rate_limited(10, 60))],
)
async def upload_image(
    lot_id: int, image: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)
) -> LotOut:
    require_business(user)
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Unsupported image type")
    lot = db.get(Lot, lot_id)
    if not lot or lot.shop.owner_id != user.id:
        raise HTTPException(404, "Lot not found")
    content = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(413, "Image is too large")
    try:
        content, content_type = sanitize_image(content, image.content_type)
    except InvalidImageError as exc:
        raise HTTPException(415, "Uploaded image is invalid or unsupported") from exc
    key = f"lots/{lot_id}/{uuid4().hex}"
    try:
        get_storage().upload(key, content, content_type)
    except BotoCoreError as exc:
        raise HTTPException(503, "Image storage unavailable") from exc
    lot.image_key = key
    lot.image_url = None
    db.commit()
    db.refresh(lot)
    return lot_response(lot)


@app.post(
    "/api/v1/lots/{lot_id}/expiry-scans",
    response_model=ExpiryScanSuggestionOut,
    status_code=201,
    dependencies=[Depends(rate_limited(3, 60))],
)
def scan_expiry_date(
    lot_id: int,
    language: str = Query("en", pattern="^(en|es)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ExpiryScanSuggestionOut:
    require_business(user)
    lot = db.get(Lot, lot_id)
    if not lot or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Lot not found")
    if not lot.image_key:
        raise HTTPException(409, "Upload a lot image before scanning its expiry date")
    try:
        image_data, image_mime_type = get_storage().download(lot.image_key)
    except BotoCoreError as exc:
        raise HTTPException(503, "Image storage unavailable") from exc
    if len(image_data) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(415, "Stored lot image is invalid")
    try:
        image_data, image_mime_type = sanitize_image(image_data, image_mime_type)
    except InvalidImageError as exc:
        raise HTTPException(415, "Stored lot image is invalid") from exc

    result = build_client().generate_structured(
        prompt=build_expiry_scan_prompt(language),
        response_model=ExpiryDateRead,
        user_id=user.id,
        locale=language,
        prompt_version=EXPIRY_SCAN_PROMPT_VERSION,
        image_data=image_data,
        image_mime_type=image_mime_type,
        model_tier="smart",
    )
    is_readable = result.expires_on is not None and result.confidence >= MIN_EXPIRY_OCR_CONFIDENCE
    db.execute(
        update(ExpiryScanSuggestion)
        .where(
            ExpiryScanSuggestion.lot_id == lot.id,
            ExpiryScanSuggestion.status == "awaiting_confirmation",
        )
        .values(status="rejected")
    )
    suggestion = ExpiryScanSuggestion(
        lot_id=lot.id,
        user_id=user.id,
        printed_date=result.printed_date,
        expires_on=result.expires_on,
        confidence=result.confidence,
        status="awaiting_confirmation" if is_readable else "unreadable",
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return ExpiryScanSuggestionOut.model_validate(suggestion)


@app.get(
    "/api/v1/lots/{lot_id}/expiry-scans",
    response_model=list[ExpiryScanSuggestionOut],
)
def list_expiry_scans(
    lot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ExpiryScanSuggestion]:
    require_business(user)
    lot = db.get(Lot, lot_id)
    if not lot or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Lot not found")
    return list(
        db.scalars(
            select(ExpiryScanSuggestion)
            .where(ExpiryScanSuggestion.lot_id == lot_id)
            .order_by(ExpiryScanSuggestion.created_at.desc(), ExpiryScanSuggestion.id.desc())
        )
    )


@app.post(
    "/api/v1/lots/{lot_id}/expiry-scans/{suggestion_id}/confirm",
    response_model=ExpiryScanSuggestionOut,
)
def confirm_expiry_scan(
    lot_id: int,
    suggestion_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ExpiryScanSuggestionOut:
    require_business(user)
    lot = db.scalar(select(Lot).where(Lot.id == lot_id).with_for_update())
    if not lot or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Lot not found")
    suggestion = db.scalar(
        select(ExpiryScanSuggestion)
        .where(
            ExpiryScanSuggestion.id == suggestion_id,
            ExpiryScanSuggestion.lot_id == lot_id,
            ExpiryScanSuggestion.status == "awaiting_confirmation",
        )
        .with_for_update()
    )
    if not suggestion or suggestion.expires_on is None:
        raise HTTPException(409, "Expiry-date suggestion is not awaiting confirmation")
    lot.expires_at = datetime.combine(suggestion.expires_on, datetime_time.max, tzinfo=timezone.utc)
    suggestion.status = "confirmed"
    db.commit()
    db.refresh(suggestion)
    return ExpiryScanSuggestionOut.model_validate(suggestion)


@app.post(
    "/api/v1/lots/{lot_id}/expiry-scans/{suggestion_id}/reject",
    response_model=ExpiryScanSuggestionOut,
)
def reject_expiry_scan(
    lot_id: int,
    suggestion_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ExpiryScanSuggestionOut:
    require_business(user)
    lot = db.get(Lot, lot_id)
    if not lot or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Lot not found")
    suggestion = db.scalar(
        select(ExpiryScanSuggestion).where(
            ExpiryScanSuggestion.id == suggestion_id,
            ExpiryScanSuggestion.lot_id == lot_id,
            ExpiryScanSuggestion.status == "awaiting_confirmation",
        )
    )
    if not suggestion:
        raise HTTPException(409, "Expiry-date suggestion is not awaiting confirmation")
    suggestion.status = "rejected"
    db.commit()
    db.refresh(suggestion)
    return ExpiryScanSuggestionOut.model_validate(suggestion)


@app.get("/api/v1/lots", response_model=list[LotOut])
def list_lots(
    expires_in: int | None = Query(None, ge=1),
    min_discount: int | None = Query(None, ge=0, le=100),
    category: str | None = Query(None, min_length=2, max_length=80),
    business_type: str | None = Query(None, pattern="^(restaurant|supermarket)$"),
    lat_min: float | None = Query(None, ge=-90, le=90),
    lat_max: float | None = Query(None, ge=-90, le=90),
    lng_min: float | None = Query(None, ge=-180, le=180),
    lng_max: float | None = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
) -> list[LotOut]:
    query = select(Lot).where(
        Lot.quantity > 0,
        Lot.status == "active",
        Lot.expires_at > datetime.now(timezone.utc),
    )
    has_location_filter = any(value is not None for value in (lat_min, lat_max, lng_min, lng_max))
    if category is not None or business_type is not None or has_location_filter:
        query = query.join(Lot.product).join(Lot.shop)
        if category is not None:
            query = query.where(Product.category == category)
        if business_type is not None:
            query = query.where(Shop.business_type == business_type)
    if expires_in:
        query = query.where(
            Lot.expires_at <= datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=expires_in)
        )
    if min_discount is not None:
        query = query.where(Lot.discount_percent >= min_discount)
    if lat_min is not None:
        query = query.where(Shop.latitude >= lat_min)
    if lat_max is not None:
        query = query.where(Shop.latitude <= lat_max)
    if lng_min is not None:
        query = query.where(Shop.longitude >= lng_min)
    if lng_max is not None:
        query = query.where(Shop.longitude <= lng_max)
    return [lot_response(lot) for lot in db.scalars(query.order_by(Lot.expires_at))]


@app.get("/api/v1/lots/{lot_id}", response_model=LotOut)
def lot_detail(lot_id: int, db: Session = Depends(get_db)) -> LotOut:
    lot = db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(404, "Lot not found")
    return lot_response(lot)


@app.post(
    "/api/v1/lots/{lot_id}/reserve",
    status_code=201,
    dependencies=[Depends(rate_limited(10, 60))],
)
def reserve(
    lot_id: int, data: ReservationCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, int | str]:
    if user.role != "customer" and not user.is_admin:
        raise HTTPException(403, "Customer account required to reserve a batch")
    reservation = reserve_lot(db, lot_id, user.id, data.quantity)
    return {
        "id": reservation.id,
        "status": "reserved",
        "quantity": reservation.quantity,
        "pickup_code": reservation.pickup_code,
    }


@app.post(
    "/api/v1/admin/models/sales-forecast/train",
    response_model=SalesForecastTrainingOut,
    dependencies=[Depends(rate_limited(MODEL_TRAINING_REQUESTS_PER_MINUTE, 60))],
)
def train_sales_forecast_model(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> SalesForecastTrainingOut:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    result = build_train_sales_forecast_model_use_case(db).execute()
    return SalesForecastTrainingOut(
        model_version=result.version,
        training_samples=result.training_samples,
        evaluation_samples=result.evaluation_samples,
        baseline_mae=result.baseline_mae,
        model_mae=result.model_mae,
        activated=result.activated,
    )


@app.post("/api/v1/lots/{lot_id}/donate", status_code=201)
def donate(
    lot_id: int, data: DonationCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, int | str]:
    require_business(user)
    lot = db.get(Lot, lot_id)
    if lot is None or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Lot not found")
    donation = donate_lot(db, lot_id, data.quantity)
    return {"id": donation.id, "status": "donated", "quantity": donation.quantity}


@app.post("/api/v1/lots/{lot_id}/cancel", response_model=LotOut)
def cancel_lot_route(lot_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> LotOut:
    require_business(user)
    lot = db.get(Lot, lot_id)
    if lot is None or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Lot not found")
    return lot_response(cancel_lot(db, lot_id))


@app.post("/api/v1/reservations/{reservation_id}/cancel")
def cancel_reservation_route(
    reservation_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, int | str]:
    reservation = cancel_reservation(db, reservation_id, user.id)
    return {"id": reservation.id, "status": reservation.status, "quantity": reservation.quantity}


@app.post(
    "/api/v1/reservations/{reservation_id}/pickup",
    dependencies=[Depends(rate_limited(5, 60))],
)
def confirm_pickup(
    reservation_id: int,
    data: PickupConfirmation,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, int | str]:
    require_business(user)
    reservation = db.get(Reservation, reservation_id)
    lot = db.get(Lot, reservation.lot_id) if reservation else None
    if lot is None or (lot.shop.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Reservation not found")
    reservation = confirm_reservation_pickup(db, reservation_id, data.pickup_code)
    return {"id": reservation.id, "status": reservation.status, "quantity": reservation.quantity}


@app.post(
    "/api/v1/lots/{lot_id}/generate-promos",
    status_code=202,
    dependencies=[Depends(rate_limited(5, 60))],
)
def generate_promos(
    lot_id: int,
    language: str = Query("en", pattern="^(en|es)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, str]:
    require_business(user)
    lot = db.get(Lot, lot_id)
    if not lot or lot.shop.owner_id != user.id:
        raise HTTPException(404, "Lot not found")
    try:
        generate_promotions_task.delay(lot_id, user.id, language)
    except OperationalError:
        build_promotions(db, lot, language, user_id=user.id)
    return {"status": "queued"}


@app.get("/api/v1/lots/{lot_id}/promos", response_model=list[PromotionOut])
def promos(lot_id: int, db: Session = Depends(get_db)) -> list[Promotion]:
    return list(db.scalars(select(Promotion).where(Promotion.lot_id == lot_id).order_by(Promotion.id)))


@app.get("/api/v1/shops/{shop_id}/forecast")
def forecast(shop_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, object]:
    require_business(user)
    shop = db.get(Shop, shop_id)
    if not shop or shop.owner_id != user.id:
        raise HTTPException(404, "Shop not found")
    count = db.scalar(select(func.count(Lot.id)).where(Lot.shop_id == shop_id)) or 0
    return {
        "shop_id": shop_id,
        "series": [{"day": index, "predicted_lots": max(0, count + index - 2)} for index in range(1, 8)],
    }


@app.get("/api/v1/admin/report")
def report(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, int]:
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "shops": db.scalar(select(func.count(Shop.id))) or 0,
        "lots": db.scalar(select(func.count(Lot.id))) or 0,
        "reservations": db.scalar(select(func.count(Reservation.id))) or 0,
        "donations": db.scalar(select(func.count(Donation.id))) or 0,
    }
