from app.application.dto import Actor
from app.application.ports import ImpactRepository, RescueLotGateway
from app.domain.exceptions import RescueLotNotFoundError, RescuePermissionError
from app.domain.impact import ShopImpact, summarize_impact


class GetShopImpact:
    def __init__(self, lots: RescueLotGateway, impact: ImpactRepository) -> None:
        self._lots = lots
        self._impact = impact

    def execute(self, shop_id: int, actor: Actor) -> ShopImpact:
        if not actor.can_manage_shops:
            raise RescuePermissionError("Business account required")
        owner_id = self._lots.get_shop_owner_id(shop_id)
        if owner_id is None or (owner_id != actor.user_id and not actor.is_admin):
            raise RescueLotNotFoundError("Shop not found")
        return summarize_impact(self._impact.reservation_outcomes(shop_id), self._impact.donated_units(shop_id))
