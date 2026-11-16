# Scraping guide: the Scanner

How data is collected from outside the platform, what is allowed, and how to add a source.
Decisions are in ADR 0010; sources and their policies are in `research-sources.md`.

## Principles

1. **A permissive `robots.txt` is not permission.** Every source needs a person to record that its
   terms of use were reviewed. Until then it can be neither enabled nor run.
2. **Politeness by default.** Identifying User-Agent, `ROBOTSTXT_OBEY`, a delay between requests,
   one request at a time per domain, AutoThrottle, cache, no cookies, no login, few retries.
3. **Stop, never evade.** The first 401, 403 or 429 ends the run. There is no CAPTCHA solving, no
   proxy rotation and no retry designed to get around a block.
4. **Collected data is not stock.** A price is a price a page published. It is never copied into a
   lot, never an offer, and never evidence of surplus or near-expiry.
5. **Nothing external is an affiliate.** Discovered businesses are `discovered` until they register
   themselves.

## Architecture

```
POST /api/v1/admin/scanner/sources/{key}/run
        |  (administrator)
        v
 RunSourceNow  --->  SubprocessSourceRunner  --->  python -m scraper.run --source KEY
                                                        |
                                    ensure_runnable (enabled + terms reviewed + safe URL)
                                                        |
                                           Scrapy spider  ->  ValidationPipeline -> PersistencePipeline
                                                        |                                   |
                                            StopOnAccessDeniedMiddleware        external_* tables
```

- `app-backend/scraper/` holds the engine: `settings.py`, `items.py`, `pipelines.py`,
  `middlewares.py`, `context.py`, `jsonld.py`, `runner.py`, `run.py` and one spider per kind of
  source in `spiders/`.
- The web process never imports Scrapy. It starts the engine as a subprocess with a time limit,
  because Twisted's reactor cannot be restarted.
- The domain holds the rules (`external_data.py`, `url_policy.py`, `source_policy.py`); the
  repositories persist; the engine only collects.

## Connectors

| Kind | Spider | Reads | Notes |
| --- | --- | --- | --- |
| `overpass` | `OverpassSpider` | Businesses from OpenStreetMap through one bounded Overpass query for the area | ODbL licence; attribution is kept on each record. The public instance asks for modest use. |
| `jsonld_catalog` | `JsonLdCatalogSpider` | schema.org `Product` and `Offer` JSON-LD on the start page | A reference price counts only when the page marks it as a list price. Only COP prices are read. |

Not implemented: JavaScript-rendered pages, search, login, and any marketplace that forbids
automated reading. A connector for such a source is not a missing feature; it is a decision.

## Running and scheduling

- **Manually** from `/admin/scanner` (Run now) or `POST /api/v1/admin/scanner/sources/{key}/run`.
- **From a terminal** (inside `app-backend/`): `python -m scraper.run --source KEY`. It prints one
  JSON line with the counters.
- **On a schedule**: set a source's schedule (at least every 15 minutes). A Celery beat task
  (`run-due-scanner-sources`, checked every 15 minutes) runs every enabled, reviewed source whose
  interval has passed. It needs the `scheduler` and `worker` services running, as for lot expiry.
- A run left in `running` by a dead process is closed as `failed` on the next run, so the history
  never lies.

## Adding a source

1. Register it (`/admin/scanner` → Register a source). The address must be HTTPS, on a domain in
   `SCRAPER_ALLOWED_DOMAINS`, with no credentials, no IP literal, default port, and must resolve only
   to public addresses.
2. Read its terms of use and `robots.txt`. Record what you checked (Review terms). This is stored
   with your user and the date.
3. Enable it, then run it. Check the run history and the rejected records.
4. If the page needs JavaScript or forbids automated access, do not add a connector for it.

## What a run records

Each run stores its status (`running`, `succeeded`, `failed`, `stopped`), counters (accepted,
rejected, awaiting validation), a stop reason (`access_denied`, `robots_forbidden`, `rate_limited`,
`timeout`, `crashed`, `not_allowed`) and a bounded sample of every rejected record with its reason
(`missing_name`, `invalid_coordinates`, `outside_area`, `invalid_price`, `invalid_url`).
A refused run (source disabled, terms not reviewed, unsafe address) also appears in the history.

## Freshness

Every record has `last_seen_at`. Data older than 72 hours is shown as out of date and the screens
say not to treat it as current. Prices keep a history: a new observation is stored only when the
price or the reference price changes.

## Tests

- `tests/test_scraper_runs.py` starts a local site and runs the real engine in a subprocess, with
  robots.txt, 403 and 429 cases, repeated runs and refusals.
- `tests/test_overpass_spider.py` parses a recorded Overpass response.
- `tests/test_jsonld.py`, `tests/test_url_policy.py`, `tests/test_source_policy.py`,
  `tests/test_external_data*.py` and `tests/test_scanner_api.py` cover the rules and the API.

## Validation dates and limits

- `robots.txt` of Exito, Alkosto and Jumbo was read on 2026-11-16. Their terms of use were not.
  Those sources ship disabled.
- A live call to the Overpass API could not be made from the development machine (the public
  instance did not answer). The connector is tested against a recorded response; the live call is
  unverified.
