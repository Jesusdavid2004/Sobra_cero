import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.auth import create_token, current_user, hash_password, verify_password
from app.config import settings
from app.db import Base, engine, get_db
from app.dependencies import build_calculate_waste_risk_use_case
from app.domain.exceptions import (
    BatchAlreadyReservedError,
    InsufficientSalesHistoryError,
)
from app.models import (
    Donation,
    Lot,
    Product,
    Promotion,
    Reservation,
    SalesHistory,
    Shop,
    User,
)
from app.schemas import (
    DonationCreate,
    LotCreate,
    LotOut,
    ProductCreate,
    ProductOut,
    PromotionOut,
    ReservationCreate,
    SalesHistoryCreate,
    SalesHistoryCreated,
    ShopCreate,
    ShopOut,
    Token,
    UserCreate,
    UserOut,
    WasteRiskOut,
)
from app.services import build_promotions, donate_lot, reserve_lot
from app.storage import get_storage
from app.synthetic_sales import DEFAULT_HISTORY_DAYS, generate_shop_sales_history
from app.worker import generate_promotions_task

Base.metadata.create_all(bind=engine)
backend_root = Path(__file__).resolve().parent.parent
alembic_config = Config(str(backend_root / "alembic.ini"))
alembic_config.set_main_option("script_location", str(backend_root / "migrations"))
alembic_config.set_main_option(
    "sqlalchemy.url",
    engine.url.render_as_string(hide_password=False).replace("%", "%%"),
)
command.upgrade(alembic_config, "head")
app = FastAPI(title="SobraCero API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(InsufficientSalesHistoryError)
@app.exception_handler(BatchAlreadyReservedError)
def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    status_code = 409 if isinstance(exc, BatchAlreadyReservedError) else 422
    error_code = (
        "batch_already_reserved" if isinstance(exc, BatchAlreadyReservedError) else "insufficient_sales_history"
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc), "code": error_code})


_rate_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limited(limit: int, window_seconds: int = 60):
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


def require_business(user: User) -> None:
    if user.role != "business" and not user.is_admin:
        raise HTTPException(403, "Business account required")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/auth/register", response_model=Token, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)) -> Token:
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=data.email, password_hash=hash_password(data.password), role=data.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_token(user.id))


@app.post("/api/v1/auth/login", response_model=Token)
def login(data: UserCreate, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return Token(access_token=create_token(user.id))


@app.get("/api/v1/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.post("/api/v1/shops", response_model=ShopOut, status_code=201)
def create_shop(data: ShopCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Shop:
    require_business(user)
    shop = Shop(**data.model_dump(), owner_id=user.id)
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


@app.get("/api/v1/shops", response_model=list[ShopOut])
def shops(db: Session = Depends(get_db)) -> list[Shop]:
    return list(db.scalars(select(Shop)))


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
def shop_products(shop_id: int, db: Session = Depends(get_db)) -> list[Product]:
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
    if not shop or shop.owner_id != user.id:
        raise HTTPException(404, "Product not found")
    seen_dates = set()
    created = 0
    existing = 0
    for entry in data.entries:
        if entry.sales_date in seen_dates:
            raise HTTPException(422, "Each sales date may only appear once per request")
        seen_dates.add(entry.sales_date)
        row = db.scalar(
            select(SalesHistory).where(
                SalesHistory.product_id == product_id,
                SalesHistory.sales_date == entry.sales_date,
            )
        )
        if row:
            row.units_sold = entry.units_sold
            row.had_promotion = entry.had_promotion
            existing += 1
        else:
            db.add(
                SalesHistory(
                    product_id=product_id,
                    sales_date=entry.sales_date,
                    units_sold=entry.units_sold,
                    had_promotion=entry.had_promotion,
                )
            )
            created += 1
    db.commit()
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
    if not shop or shop.owner_id != user.id:
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
            )
        )
    return results


@app.post("/api/v1/lots", response_model=LotOut, status_code=201)
def create_lot(data: LotCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Lot:
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
    return lot


@app.post(
    "/api/v1/lots/{lot_id}/image",
    response_model=LotOut,
    dependencies=[Depends(rate_limited(10, 60))],
)
async def upload_image(
    lot_id: int, image: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Lot:
    require_business(user)
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Unsupported image type")
    content = await image.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image is too large")
    lot = db.get(Lot, lot_id)
    if not lot or lot.shop.owner_id != user.id:
        raise HTTPException(404, "Lot not found")
    key = f"lots/{lot_id}/{image.filename or 'image.jpg'}"
    try:
        lot.image_url = get_storage().upload(key, content, image.content_type)
    except Exception as exc:
        raise HTTPException(503, "Image storage unavailable") from exc
    db.commit()
    db.refresh(lot)
    return lot


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
) -> list[Lot]:
    query = select(Lot).where(Lot.quantity > 0)
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
    return list(db.scalars(query.order_by(Lot.expires_at)))


@app.get("/api/v1/lots/{lot_id}", response_model=LotOut)
def lot_detail(lot_id: int, db: Session = Depends(get_db)) -> Lot:
    lot = db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(404, "Lot not found")
    return lot


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


@app.post("/api/v1/lots/{lot_id}/donate", status_code=201)
def donate(
    lot_id: int, data: DonationCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, int | str]:
    donation = donate_lot(db, lot_id, data.quantity)
    return {"id": donation.id, "status": "donated", "quantity": donation.quantity}


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
        generate_promotions_task.delay(lot_id, language)
    except Exception:
        build_promotions(db, lot, language)
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
