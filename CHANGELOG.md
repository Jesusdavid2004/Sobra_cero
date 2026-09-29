# Changelog

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