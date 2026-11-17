# Changelog

## [Unreleased]

- Added an interactive map of food businesses in Pasto (Leaflet, clustering, layers, filters, place
  search, opportunity areas and public promotions). Businesses found in public sources are never
  shown as affiliated, every place states its source and when it was last seen, and demonstration
  data is flagged and opt-in.
- Added the Scanner: a Scrapy collection engine behind a policy gate (recorded terms review, domain
  allowlist, SSRF protection, stop on 401, 403 and 429, `robots.txt`), an OpenStreetMap connector, a
  schema.org JSON-LD catalog connector, price history, run history with rejected records, an
  administrator API and screen, and scheduled runs.
- Added declared waste and a daily shop diagnosis: numbers, alerts and limitations come from code;
  the model only words them, and the diagnosis still works when the model is unavailable.
- Migrations 0011 (external data) and 0012 (waste records).
- Fixed the lot expiry time being shown in the server's time zone and a hydration error on every
  page for visitors in dark mode.
- Added pickup discovery: customers give a pickup window, budget, quantity and category and see
  only the lots they can collect in time, with the reason each other lot was left out. A language
  model can fill the form from a typed sentence; the customer reviews it. Includes a seeded
  synthetic comparison against distance-only ordering.
- Added donation receivers: profiles with accepted categories, capacity, refrigeration and opening
  hours; compatibility checked before a fair ordering; shop offers (with an optional AI-drafted
  message), receiver acceptance that commits stock once, and delivery confirmation. Only delivered
  offers count as donated units.
- Added a pickup QR for reservations, scanned at the shop with the browser barcode detector where
  available (manual entry otherwise); the server still validates and confirms each pickup once.
- Migration 0010 adds `receivers` and `donation_offers`.
- Added an API readiness endpoint that checks PostgreSQL and Redis separately
  from the liveness endpoint.
- Added business-dashboard confirmation for customer pickups using the
  reservation reference and pickup code, with an IP rate limit and
  cross-role/ownership coverage.
- Added an end-to-end browser test for publishing, reserving, and confirming a
  pickup, including locale and theme changes.
- Documented system architecture, API contracts, model/AI evaluation,
  deployment operations, security controls, and the live demo.

## [0.2.1] - 2026-09-29

- Replaced the archived MinIO container with LocalStack as the S3-compatible storage (MinIO open-source was discontinued upstream).
- Mapped the local PostgreSQL port to 5433 to avoid clashing with a system PostgreSQL service.

## [0.2.0] - 2026-09-29

- Connected real MinIO/S3 storage for lot images (lazy S3-compatible client, public URLs).
- Added abstract LLM client with mock (default), OpenAI and OpenAI-compatible (Ollama/Groq/OpenRouter) providers.
- Stored prompt templates separately; the exact prompt is persisted per promo variant for auditability.
- Added geographic bounding-box filtering and lot detail/product listing endpoints.
- Added in-memory rate limiting for image uploads and promo generation.
- Wired the frontend end-to-end: login/register, shop dashboard, publish lot (client-side image compression + upload), vitrine reservation, lot detail with promos, admin reporting and forecast.
- Enforced flake8 + mypy in CI and pinned bcrypt for passlib compatibility.
- PWA service worker now caches the app shell for offline use.

## [0.1.0] - 2026-09-29

- Added FastAPI food-lot marketplace MVP.
- Added JWT auth, shops, products, lots, reservations and donations.
- Added Celery promotions and forecast endpoints.
- Added responsive EN/ES Next.js vitrine with theme toggle and PWA manifest.
- Added Docker Compose, seed data, tests and GitHub Actions CI.