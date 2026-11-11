from app.application.ports import PublicShopRepository
from app.domain.exceptions import ShopNotFoundError
from app.domain.public_shop import PublicShop


class GetPublicShop:
    def __init__(self, shops: PublicShopRepository) -> None:
        self._shops = shops

    def execute(self, shop_id: int) -> PublicShop:
        shop = self._shops.get(shop_id)
        if shop is None:
            raise ShopNotFoundError("Shop not found")
        return shop
