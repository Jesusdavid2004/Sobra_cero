from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.application.use_cases.get_public_shop import GetPublicShop
from app.db import get_db
from app.dependencies import build_get_public_shop_use_case

router = APIRouter(prefix="/api/v1/public", tags=["public"])


class PublicShopOut(BaseModel):
    id: int
    name: str
    description: str
    business_type: str
    latitude: float
    longitude: float


@router.get("/shops/{shop_id}", response_model=PublicShopOut)
def get_public_shop(shop_id: int, db: Session = Depends(get_db)) -> PublicShopOut:
    use_case: GetPublicShop = build_get_public_shop_use_case(db)
    return PublicShopOut(**use_case.execute(shop_id).__dict__)
