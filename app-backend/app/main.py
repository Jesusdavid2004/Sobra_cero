import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import create_token, current_user, hash_password, verify_password
from app.db import Base, engine, get_db
from app.models import Donation, Lot, Product, Promotion, Reservation, Shop, User
from app.schemas import (
    DonationCreate,
    LotCreate,
    LotOut,
    ProductCreate,
    ProductOut,
    PromotionOut,
    ReservationCreate,
    ShopCreate,
    ShopOut,
    Token,
    UserCreate,
    UserOut,
)
from app.services import build_promotions, donate_lot, reserve_lot
from app.storage import get_storage
from app.worker import generate_promotions_task

Base.metadata.create_all(bind=engine)
app = FastAPI(title="SobraCero API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_rate_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limited(limit: int, window_seconds: int = 60):
    """Simple in-memory sliding-window rate limiter keyed by client IP."""

    def dependency(request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _rate_buckets[key]
        bucket[:] = [ts for ts in bucket if now - ts < window_seconds]
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        bucket.append(now)

    return dependency


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/auth/register", response_model=Token, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)) -> Token:
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=data.email, password_hash=hash_password(data.password))
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


@app.post("/api/v1/lots", response_model=LotOut, status_code=201)
def create_lot(data: LotCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Lot:
    shop = db.get(Shop, data.shop_id)
    if not shop or shop.owner_id != user.id:
        raise HTTPException(404, "Shop not found")
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
    lat_min: float | None = Query(None, ge=-90, le=90),
    lat_max: float | None = Query(None, ge=-90, le=90),
    lng_min: float | None = Query(None, ge=-180, le=180),
    lng_max: float | None = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
) -> list[Lot]:
    query = select(Lot).where(Lot.quantity > 0)
    if expires_in:
        query = query.where(
            Lot.expires_at <= datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=expires_in)
        )
    if min_discount is not None:
        query = query.where(Lot.discount_percent >= min_discount)
    if lat_min is not None or lat_max is not None or lng_min is not None or lng_max is not None:
        query = query.join(Lot.shop)
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


@app.post("/api/v1/lots/{lot_id}/reserve", status_code=201)
def reserve(
    lot_id: int, data: ReservationCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, int | str]:
    reservation = reserve_lot(db, lot_id, user.id, data.quantity)
    return {"id": reservation.id, "status": "reserved", "quantity": reservation.quantity}


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
    lot = db.get(Lot, lot_id)
    if not lot:
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
