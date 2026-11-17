from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.public_shop import PublicShop
from app.models import Shop


class SqlAlchemyPublicShopRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, shop_id: int) -> PublicShop | None:
        row = self._session.execute(
            select(Shop.id, Shop.name, Shop.description, Shop.business_type, Shop.latitude, Shop.longitude).where(
                Shop.id == shop_id
            )
        ).one_or_none()
        if row is None:
            return None
        return PublicShop(row[0], row[1], row[2], row[3], row[4], row[5])
