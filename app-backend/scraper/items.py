import scrapy


class BusinessItem(scrapy.Item):
    """A business as a source published it, before validation."""

    external_id = scrapy.Field()
    name = scrapy.Field()
    category = scrapy.Field()
    latitude = scrapy.Field()
    longitude = scrapy.Field()
    address = scrapy.Field()
    city = scrapy.Field()
    website = scrapy.Field()
    phone = scrapy.Field()
    opening_hours = scrapy.Field()
    source_url = scrapy.Field()


class ProductItem(scrapy.Item):
    """A product with the price a source published, before validation."""

    name = scrapy.Field()
    category = scrapy.Field()
    price = scrapy.Field()
    original_price = scrapy.Field()
    url = scrapy.Field()
    availability = scrapy.Field()
    shop_name = scrapy.Field()
