from app.application.dto import Actor
from app.application.ports import LotTimelineSource, RescueLotGateway
from app.domain.exceptions import RescueLotNotFoundError, RescuePermissionError
from app.domain.timeline import TimelineEvent, build_timeline


class GetLotTimeline:
    def __init__(self, lots: RescueLotGateway, source: LotTimelineSource) -> None:
        self._lots = lots
        self._source = source

    def execute(self, lot_id: int, actor: Actor) -> tuple[TimelineEvent, ...]:
        if not actor.can_manage_shops:
            raise RescuePermissionError("Business account required")
        snapshot = self._lots.get_snapshot(lot_id)
        if snapshot is None or (snapshot.owner_id != actor.user_id and not actor.is_admin):
            raise RescueLotNotFoundError("Lot not found")
        return build_timeline(
            self._source.plan_events(lot_id),
            self._source.reservations(lot_id),
            self._source.donations(lot_id),
        )
