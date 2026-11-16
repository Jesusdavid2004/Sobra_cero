from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.map_dto import MapPlace, PromotionView
from app.domain.external_data import DEFAULT_MAX_AGE_HOURS, freshness
from app.domain.opportunities import Signal, SignalPoint
from app.domain.places import Affiliation, BoundingBox, normalize_name, shop_category
from app.models import Lot, Product, ReceiverRecord, Shop
from app.models_external import (
    ExternalBusinessRow,
    ExternalProductRow,
    ExternalSourceRow,
)

AFFILIATED_SOURCE = "sobracero"
RECEIVER_SOURCE = "sobracero"
DEFAULT_PLACE_LIMIT = 500


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SqlAlchemyMapRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _offer_counts(self, now: datetime) -> dict[int, int]:
        rows = self._session.execute(
            select(Lot.shop_id, func.count())
            .where(Lot.status == "active", Lot.quantity > 0, Lot.expires_at > now)
            .group_by(Lot.shop_id)
        ).all()
        return {shop_id: count for shop_id, count in rows}

    def _dominant_product_categories(self) -> dict[int, str]:
        rows = self._session.execute(
            select(Product.shop_id, Product.category, func.count())
            .group_by(Product.shop_id, Product.category)
            .order_by(Product.shop_id, func.count().desc(), Product.category)
        ).all()
        dominant: dict[int, str] = {}
        for shop_id, category, _count in rows:
            dominant.setdefault(shop_id, category)
        return dominant

    def affiliated(self, bounds: BoundingBox, categories: frozenset[str], text: str, only_offers: bool,
                   limit: int, now: datetime) -> list[MapPlace]:  # fmt: skip
        offers = self._offer_counts(now)
        dominant = self._dominant_product_categories()
        query = select(Shop).where(
            Shop.latitude.between(bounds.south, bounds.north),
            Shop.longitude.between(bounds.west, bounds.east),
            (Shop.latitude != 0) | (Shop.longitude != 0),
        )
        places = []
        for shop in self._session.scalars(query.order_by(Shop.name)):
            category = shop_category(shop.business_type, dominant.get(shop.id))
            if categories and category.value not in categories:
                continue
            if text and text not in normalize_name(shop.name):
                continue
            count = offers.get(shop.id, 0)
            if only_offers and count == 0:
                continue
            places.append(
                MapPlace(
                    place_id=f"shop:{shop.id}",
                    kind="business",
                    name=shop.name,
                    category=category.value,
                    affiliation=Affiliation.AFFILIATED.value,
                    latitude=shop.latitude,
                    longitude=shop.longitude,
                    address="",
                    city="",
                    website="",
                    opening_hours="",
                    source=AFFILIATED_SOURCE,
                    source_url="",
                    last_seen_at=None,
                    freshness="",
                    verified=True,
                    is_demo=False,
                    offer_count=count,
                )
            )
        return places[:limit]

    def discovered(self, bounds: BoundingBox, categories: frozenset[str], text: str, include_demo: bool,
                   limit: int, now: datetime) -> list[MapPlace]:  # fmt: skip
        query = (
            select(ExternalBusinessRow, ExternalSourceRow.key)
            .join(ExternalSourceRow, ExternalBusinessRow.source_id == ExternalSourceRow.id)
            .where(
                ExternalBusinessRow.latitude.between(bounds.south, bounds.north),
                ExternalBusinessRow.longitude.between(bounds.west, bounds.east),
                ExternalBusinessRow.verification_status != "rejected",
            )
        )
        if not include_demo:
            query = query.where(ExternalBusinessRow.is_demo.is_(False))
        if categories:
            query = query.where(ExternalBusinessRow.category.in_(categories))
        if text:
            query = query.where(ExternalBusinessRow.normalized_name.contains(text))
        rows = self._session.execute(query.order_by(ExternalBusinessRow.name).limit(limit))
        return [
            MapPlace(
                place_id=f"ext:{b.id}",
                kind="business",
                name=b.name,
                category=b.category,
                affiliation=b.affiliation,
                latitude=b.latitude,
                longitude=b.longitude,
                address=b.address,
                city=b.city,
                website=b.website,
                opening_hours=b.opening_hours,
                source=key,
                source_url=b.source_url,
                last_seen_at=_aware(b.last_seen_at),
                freshness=freshness(_aware(b.last_seen_at), now).value,
                verified=b.verification_status == "verified",
                is_demo=b.is_demo,
                offer_count=0,
            )
            for b, key in rows
        ]

    def receivers(self, bounds: BoundingBox, text: str, limit: int) -> list[MapPlace]:
        rows = self._session.scalars(
            select(ReceiverRecord)
            .where(
                ReceiverRecord.latitude.between(bounds.south, bounds.north),
                ReceiverRecord.longitude.between(bounds.west, bounds.east),
            )
            .order_by(ReceiverRecord.name)
            .limit(limit)
        )
        return [
            MapPlace(
                place_id=f"receiver:{r.id}",
                kind="receiver",
                name=r.name,
                category="receiver",
                affiliation=Affiliation.AFFILIATED.value,
                latitude=r.latitude,
                longitude=r.longitude,
                address="",
                city="",
                website="",
                opening_hours="",
                source=RECEIVER_SOURCE,
                source_url="",
                last_seen_at=None,
                freshness="",
                verified=False,
                is_demo=False,
                offer_count=0,
            )
            for r in rows
            if not text or text in normalize_name(r.name)
        ]

    def signal_points(self, bounds: BoundingBox, include_demo: bool, now: datetime) -> list[SignalPoint]:
        offers = self._offer_counts(now)
        points: list[SignalPoint] = []
        for place in self.affiliated(bounds, frozenset(), "", False, DEFAULT_PLACE_LIMIT, now):
            points.append(SignalPoint(place.latitude, place.longitude, Signal.AFFILIATED_SHOP))
            shop_id = int(place.place_id.split(":")[1])
            if offers.get(shop_id):
                points.append(SignalPoint(place.latitude, place.longitude, Signal.LIVE_OFFER, offers[shop_id]))
        for place in self.receivers(bounds, "", DEFAULT_PLACE_LIMIT):
            points.append(SignalPoint(place.latitude, place.longitude, Signal.RECEIVER))
        for place in self.discovered(bounds, frozenset(), "", include_demo, DEFAULT_PLACE_LIMIT, now):
            points.append(SignalPoint(place.latitude, place.longitude, Signal.DISCOVERED_BUSINESS))
        return points

    def fresh_promotions(self, limit: int, now: datetime) -> list[PromotionView]:
        since = now - timedelta(hours=DEFAULT_MAX_AGE_HOURS)
        rows = self._session.execute(
            select(ExternalProductRow, ExternalSourceRow.name)
            .join(ExternalSourceRow, ExternalProductRow.source_id == ExternalSourceRow.id)
            .where(ExternalProductRow.discount_percent > 0, ExternalProductRow.last_seen_at >= since)
            .order_by(ExternalProductRow.discount_percent.desc(), ExternalProductRow.id)
            .limit(limit)
        )
        return [
            PromotionView(
                p.name,
                p.category,
                p.current_price_cop,
                p.original_price_cop,
                p.discount_percent,
                p.url,
                name,
                _aware(p.last_seen_at),
            )
            for p, name in rows
        ]
