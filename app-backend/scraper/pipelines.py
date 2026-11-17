from typing import Any

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from app.domain.collection import RecordKind
from app.domain.exceptions import ExternalDataInvalidError
from app.domain.external_data import build_business_record, build_product_record
from app.domain.places import PlaceCategory
from scraper.items import BusinessItem


class ValidationPipeline:
    """Turn a raw item into a validated domain record, or reject it with a stable reason code."""

    def process_item(self, item: Any, spider: Any) -> dict[str, Any]:
        context = spider.context
        raw = ItemAdapter(item).asdict()
        kind = RecordKind.BUSINESS if isinstance(item, BusinessItem) else RecordKind.PRODUCT
        source_url = str(raw.get("source_url") or raw.get("url") or "")
        try:
            if kind is RecordKind.BUSINESS:
                category = PlaceCategory(raw.get("category") or PlaceCategory.OTHER)
                record = build_business_record(raw, context.source.key, context.clock(), category, context.area)
            else:
                record = build_product_record(raw, context.source.key, context.clock())
        except ExternalDataInvalidError as error:
            context.reject(kind, str(error), source_url, raw)
            raise DropItem(str(error)) from error
        return {"kind": kind, "record": record}


class PersistencePipeline:
    """Store validated records. Nothing stored here is an affiliated shop, a lot or an offer."""

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        context = spider.context
        if item["kind"] is RecordKind.BUSINESS:
            context.store_business(item["record"])
        else:
            context.store_product(item["record"])
        return item

    def close_spider(self, spider: Any) -> None:
        spider.context.commit()
