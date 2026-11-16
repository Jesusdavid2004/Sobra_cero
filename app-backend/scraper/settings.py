"""Central Scrapy settings. Every value here favours the site being read over speed.

The collector identifies itself, obeys robots.txt, waits between requests, reads one page at a
time per domain, keeps no cookies, never logs in and does not retry beyond a small limit.
"""

import os
import tempfile
from pathlib import Path

BOT_NAME = "sobracero"
SPIDER_MODULES = ["scraper.spiders"]
USER_AGENT = os.environ.get("SCRAPER_USER_AGENT", "SobraCeroBot/1.0 (food-waste research project)")

ROBOTSTXT_OBEY = True
COOKIES_ENABLED = False
TELNETCONSOLE_ENABLED = False
LOG_LEVEL = os.environ.get("SCRAPER_LOG_LEVEL", "INFO")

DOWNLOAD_DELAY = float(os.environ.get("SCRAPER_DOWNLOAD_DELAY", "2"))
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 2
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_TIMEOUT = 20

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = DOWNLOAD_DELAY
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504]

HTTPCACHE_ENABLED = True
HTTPCACHE_DIR = str(Path(os.environ.get("SCRAPER_CACHE_DIR", tempfile.gettempdir())) / "sobracero-httpcache")
HTTPCACHE_EXPIRATION_SECS = 6 * 3600
HTTPCACHE_IGNORE_HTTP_CODES = [401, 403, 429, 500, 502, 503, 504]

CLOSESPIDER_TIMEOUT = 240
CLOSESPIDER_PAGECOUNT = int(os.environ.get("SCRAPER_MAX_PAGES", "50"))

DOWNLOADER_MIDDLEWARES = {"scraper.middlewares.StopOnAccessDeniedMiddleware": 543}
ITEM_PIPELINES = {
    "scraper.pipelines.ValidationPipeline": 100,
    "scraper.pipelines.PersistencePipeline": 300,
}
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
FEED_EXPORT_ENCODING = "utf-8"
