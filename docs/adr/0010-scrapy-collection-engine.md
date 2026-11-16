# 0010. A Scrapy engine with a policy gate for external data

Status: accepted (2026-11-16)

## Context

We want to discover businesses in a city and read public catalogs. Most sources are not ours,
their terms differ, and a promotion or a price says nothing about stock or expiry.

## Decision

- Use **Scrapy** in a package inside the backend (`app-backend/scraper/`): one spider per source,
  items, pipelines (normalize, validate, deduplicate, persist), middlewares and central settings.
- Responsible defaults for every run: `ROBOTSTXT_OBEY`, `DOWNLOAD_DELAY`, one concurrent request
  per domain, AutoThrottle, an identifying User-Agent, retries limited, no cookies, no login.
- A **policy gate** in the application layer decides whether a source may run: its domain must be
  in an allowlist, the URL must be HTTPS and must not resolve to a private address (SSRF), and a
  person must have recorded that the terms were reviewed. New retail sources start disabled.
- A middleware **stops the connector** on the first 401, 403 or 429. It never retries to get
  around a block, never solves a CAPTCHA and never logs in.
- Results go to separate `external_*` tables with source, URL and extraction time. They are never
  copied into lots. Prices are kept as observations so history is preserved.
- The Scanner API starts a run as a **subprocess** with a timeout (Twisted's reactor cannot be
  restarted inside the web process) and records the execution, counters and errors.

## Consequences

- Scrapy brings Twisted and lxml into the backend image; accepted because the same image runs the
  worker. The web process never imports Scrapy.
- No source is scraped just because its `robots.txt` allows it. A permissive `robots.txt` is
  necessary, not sufficient.
- JavaScript-rendered catalogs are out of scope; Playwright is not added.
- Tests use a local fixture site and recorded Overpass responses, never the live internet.
