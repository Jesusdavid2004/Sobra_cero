# Research: sources, references and what we may do with them

Checked on 2026-11-16 from public pages only. "Reviewed" means the `robots.txt` was read; it
never means the site's terms of use were reviewed.

## Data sources

| Source | What it offers | `robots.txt` (read 2026-11-16) | Terms of use | Decision |
| --- | --- | --- | --- | --- |
| OpenStreetMap through the Overpass API | Open map data (ODbL): shops, restaurants, cafes, markets, with coordinates and often address and hours | Not applicable (API with a fair-use policy) | ODbL requires attribution "OpenStreetMap contributors" and share-alike on derived databases | **Implemented.** One bounded query per run, identifying User-Agent, results cached in our own tables, attribution shown on the map and in each record. The public instance asks for modest use (no mass queries). |
| Nominatim (OpenStreetMap geocoder) | Address and place search | Not applicable | Usage policy: at most 1 request per second, valid identifying User-Agent, no autocomplete, no bulk geocoding, cache results, show attribution | **Implemented** behind a provider interface with a 1 req/s limiter and an in-memory cache; swappable. |
| Exito Colombia | Public catalog pages | Allows `/`; disallows account, login, checkout, quick-view and spy paths | Not reviewed | **Connector class provided, disabled by default.** |
| Alkosto Colombia | Public catalog pages, sitemaps | Allows `/`; disallows search (`?q=`), cart, checkout and account; publishes product sitemaps | Not reviewed | **Connector class provided, disabled by default.** |
| Jumbo Colombia | Public catalog pages | Allows `/`; disallows search, checkout, account, cart and many query parameters | Not reviewed | **Connector class provided, disabled by default.** |
| Google Maps | Places | Not used | Prohibits scraping | **Not used**, as required. |

The retail connectors read only the schema.org `Product` and `Offer` markup that a page publishes
for machines (JSON-LD). They are enabled per source by an administrator who records that the
terms were reviewed; until then the Scanner refuses to run them. They stop on the first 401, 403
or 429 and never try to get around a block.

## Technology

| Choice | Why | Alternatives considered |
| --- | --- | --- |
| Scrapy | Structured spiders, items, pipelines, AutoThrottle, `ROBOTSTXT_OBEY`, caching and retries are built in | Playwright is kept out: it is needed only for pages that require JavaScript, which we do not scrape; plain `requests` scripts have no politeness layer |
| Leaflet + marker clustering | Small, mature, no WebGL, accessible popups | MapLibre GL JS (vector tiles we do not host), Google Maps (licensing) |
| Haversine and bounding box in code | Enough for thousands of rows, works in SQLite tests | PostGIS (adopt when polygon queries or tens of thousands of rows appear) |
| Deterministic engine plus language model for wording | Numbers are testable; the model only explains | Letting the model compute (rejected) |

## References studied (capabilities only, nothing copied)

| Reference | Public capability | Opening for SobraCero |
| --- | --- | --- |
| Too Good To Go | Marketplace of surplus food, near-expiry management for businesses | The distinguishing part here is explainable, human-approved rescue plans and feasibility by pickup window |
| FoodCloud | Connects retailers with charities, traceability and impact analytics | Receiver compatibility and fair ordering, delivery proof |
| Winnow | Measures kitchen waste with hardware | Needs hardware and data we do not have; we record waste declared by shops instead |

## What the evidence does not support

- A promotion is not a surplus and not a near-expiry signal.
- A price on a retail page is not stock.
- A business discovered on OpenStreetMap is not a partner and is never shown as affiliated.
- Ley 1990 de 2019 and the sanitary rules require things this app cannot verify; the app records
  who is responsible and what they declared, and says so.
