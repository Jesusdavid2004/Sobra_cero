import re
from collections.abc import AsyncIterator, Iterator
from typing import Any
from urllib.parse import urlsplit

import scrapy
from scrapy.http import Request, Response

from scraper.context import CollectionContext
from scraper.items import ProductItem
from scraper.jsonld import extract_products, parse_blocks

JSONLD_XPATH = '//script[@type="application/ld+json"]/text()'


class JsonLdCatalogSpider(scrapy.Spider):
    """Products and prices a store publishes as schema.org markup.

    It reads the start page and, only if a link pattern is configured, links on the same domain
    that match it. It does not render JavaScript and does not search the site.
    """

    name = "jsonld_catalog"

    def __init__(self, context: CollectionContext, link_pattern: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.context = context
        self.link_regex = re.compile(link_pattern) if link_pattern else None
        self.domain = urlsplit(context.source.base_url).hostname or ""

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.context.source.base_url, callback=self.parse_page)

    def parse_page(self, response: Response) -> Iterator[Any]:
        documents = parse_blocks(response.xpath(JSONLD_XPATH).getall())
        for fields in extract_products(documents, response.url):
            yield ProductItem(**{**fields, "shop_name": fields["shop_name"] or self.context.source.name})
        if self.link_regex is None:
            return
        for href in response.css("a::attr(href)").getall():
            url = response.urljoin(href)
            if urlsplit(url).hostname == self.domain and self.link_regex.search(url):
                yield response.follow(url, callback=self.parse_page)
