# SobraCero MVP

SobraCero is a food-rescue marketplace: shops publish lots close to expiry and neighbors reserve or donate them. The repository is a two-application monorepo with FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL, LocalStack (S3-compatible storage), Next.js and Tailwind.

## Run locally

1. Copy `.env.example` to `.env` (secrets stay local, never committed).
2. Run `docker compose up --build`.
3. In another terminal run `docker compose exec backend python seed_data.py`.
4. Open `http://localhost:3000/en` and API documentation at `http://localhost:8000/docs`.

> Note: PostgreSQL is published on host port **5433** to avoid clashing with a local PostgreSQL service. The local S3 endpoint is `http://localhost:4566` (LocalStack).

The demo account is `demo@sobracero.com` with password `password123`. Do not use it outside local development. Running the seed command again updates the legacy `.local` demo account and does not duplicate its demo shop, product, or lots.

For a no-Docker backend test run, create a Python 3.12 virtual environment, install `app-backend/requirements.txt`, set `PYTHONPATH=app-backend`, and run `pytest app-backend/tests`. To verify the required application/domain coverage locally, run `pytest --cov=app.domain --cov=app.application --cov-fail-under=70 app-backend/tests` from `app-backend` with `PYTHONPATH=.`.

## Environment variables

Copy `.env.example` to `.env` for local development. The main settings are
`DATABASE_URL` and `REDIS_URL` (database, sessions, and background jobs),
`JWT_SECRET` and `REFRESH_COOKIE_SECURE` (authentication), `CORS_ORIGINS` and
`NEXT_PUBLIC_API_URL` (browser/API connectivity), `MINIO_*` (private image
storage), and `LLM_PROVIDER` plus the selected provider's API key (AI). The
complete setting reference and production guidance are in
[`docs/deployment.md`](docs/deployment.md). Example credentials are for local
development only; never commit `.env`.

## MVP endpoints

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`
- `GET/POST /api/v1/shops`, `GET/POST /api/v1/shops/{id}/products`
- `GET/POST /api/v1/lots`, `GET /api/v1/lots/{id}`, `POST /api/v1/lots/{id}/image`
- `POST /api/v1/lots/{id}/reserve`, `POST /api/v1/lots/{id}/donate`
- `POST /api/v1/lots/{id}/cancel`
- `POST /api/v1/reservations/{id}/cancel`, `POST /api/v1/reservations/{id}/pickup`
- `POST /api/v1/lots/{id}/generate-promos`, `GET /api/v1/lots/{id}/promos`
- `POST/GET /api/v1/lots/{id}/expiry-scans`, `POST /api/v1/lots/{id}/expiry-scans/{suggestion_id}/confirm|reject`
- `GET /api/v1/shops/{id}/forecast`, `GET /api/v1/admin/report`
- `GET /health` (liveness), `GET /ready` (PostgreSQL and Redis readiness)
- `POST /api/v1/admin/models/sales-forecast/train` (admin only)
- `POST /api/v1/products/{id}/sales-history/csv` (business owner/admin; CSV columns: `sales_date,units_sold,had_promotion`)

The public listing supports `expires_in`, `min_discount`, `category`, `business_type`, and a geographic bounding box (`lat_min`, `lat_max`, `lng_min`, `lng_max`).

## Frontend localization and checks

The storefront uses locale-prefixed routes (`/en` and `/es`). The first visit
uses the browser language when supported, and the selected locale is retained
by the locale cookie. The theme follows the operating system by default; the
theme control cycles through system, light, and dark modes and persists the
selection.

From `app-frontend`, run `npm run i18n:check`, `npm run typecheck`,
`npm test`, `npm run e2e`, `npm run lint`, `npm run format:check`, and
`npm run build` to run the frontend validation suite. Playwright installs
Chromium with `npx playwright install chromium` if it is not already present.
The PowerShell smoke path can be run with `.\scripts\smoke.ps1` after
`docker compose up --build`; it creates unique test accounts, a shop, product,
lot, and customer reservation in the local database.

## Waste-risk workflow

Business accounts can load deterministic, synthetic 60-day sales history from **Dashboard → Load 60 days of sample data**. The backend keeps that history private to the shop owner and uses it to calculate an explainable, weekday-adjusted waste-risk score for each active lot. The dashboard displays estimated unsold units and an English or Spanish recommendation.

To load sample history from a local backend environment, run `python generate_synthetic_data.py` from `app-backend`. With Docker, run `docker compose exec backend python generate_synthetic_data.py`. The script is safe to rerun; existing product/date records are left unchanged.

New accounts choose a business or customer role. Business accounts manage shops, products, lots, and forecasts; customer accounts reserve lots. Successful reservations return a unique pickup code. Schema migrations are applied automatically when the API starts.

Business owners can also import sales history from a UTF-8 CSV with the columns
`sales_date,units_sold,had_promotion` (`YYYY-MM-DD`, non-negative integer, and
`true`/`false`). Upload it as the `file` field to
`POST /api/v1/products/{id}/sales-history/csv`. Files are limited to 1 MiB and
90 data rows; a repeated product/date is updated, while invalid files are
rejected without partially importing rows. Sales history is private to the
product's shop owner and platform admins.

Waste-risk predictions use the active trained weekday-seasonal sales model when
an admin-trained candidate beats the moving-average baseline on a chronological
holdout. Training is available at
`POST /api/v1/admin/models/sales-forecast/train`; artifacts, evaluation metrics,
and the active-model pointer are stored in the database. When there is no
validated active model, the API explicitly reports
`baseline-weighted-moving-average` as `prediction_model` and continues using
the existing predictor. Training considers at most the latest 365 days and
requires enough continuous history for both training and evaluation windows.

## Product flow

The full demo flow is wired end-to-end:

1. Register/login from the locale-prefixed UI (`/en/login`, `/en/register`) →
   short-lived access token kept in memory and a rotating refresh token in an
   HttpOnly cookie.
2. Business dashboard `/en/shop`: create shops/products, review forecasts, and
   confirm customer pickups.
3. `/en/lots/new`: publish a lot (image optional, compressed on the client and
   stored in private **S3-compatible storage**).
4. Public storefront `/en/lots`: browse available lots and open `/en/lots/{id}`.
5. A customer reserves a quantity (atomic stock update) and receives a
   reservation reference and pickup code. The owning business confirms pickup
   from its dashboard.
6. Lot owners can generate **3 promo variants** and request an expiry-date
   suggestion from an uploaded image. Suggestions require explicit
   confirmation. `/en/admin` contains platform counts and model training.

Promo generation runs as a **Celery/Redis** job when available and falls back to an in-process run otherwise. The exact prompt used per variant is persisted for auditability.

## Structured AI and expiry-date scanning

Promotions, qualitative waste-risk advice, and image-based expiry-date suggestions
use schema-validated responses from the provider selected by `LLM_PROVIDER`.
Supported values are `mock`, `anthropic`, `openai`, `ollama`, `groq`, and
`openrouter`. The mock provider is deterministic and intended for development
and tests; production requires a configured remote provider.

Configure `ANTHROPIC_API_KEY` for Anthropic or `OPENAI_API_KEY` (or
`LLM_API_KEY`) for OpenAI. OpenAI-compatible providers use `LLM_BASE_URL`,
`LLM_MODEL`, and optionally `LLM_API_KEY`. `AI_MODEL_FAST` and `AI_MODEL_SMART`
select Anthropic models. `AI_MAX_TOKENS`, `AI_TIMEOUT_SECONDS`,
`AI_DAILY_QUOTA`, and `AI_CACHE_TTL_SECONDS` control response size, timeout,
per-user daily request allowance, and private response-cache duration.

Expiry-date scans require a lot image and are available only to the lot's shop
owner (or an admin). A scan is stored as `awaiting_confirmation` only when a
date is present and meets the configured confidence threshold; otherwise it is
`unreadable`. The suggested date never changes the lot automatically. The
business must explicitly confirm or reject it. Scans send the private image to
the configured AI provider; review its data-processing terms before enabling a
remote provider. Uploads accept static JPEG, PNG, and WebP images, enforce file
and pixel limits, apply EXIF orientation, and re-encode the image to remove
metadata before private storage or provider use.

## Quality and scope notes

- CI runs backend tests with at least 70% coverage for domain/application, plus `black`, `isort`, `flake8` and `mypy`; the frontend runs `eslint`, `prettier` and `next build`.
- In-memory sliding-window rate limits protect reservations, image uploads, promo generation, expiry scans, model training, and pickup confirmation. These limits are per-process and must be supplemented by a distributed edge limiter in a multi-replica production deployment.
- Reservations atomically consume lot stock; customers can cancel active reservations and the owning shop can confirm pickup with its code. Celery Beat expires lots and their outstanding reservations every minute (`docker compose up scheduler`).
- Alembic is the source of truth for the database schema. The API and both backend data scripts apply pending migrations before accessing the database.
- Images are validated by their actual JPEG/PNG/WebP signatures, limited to 5 MiB, stored under random private keys and served with short-lived signed URLs. The adapter is backed by **LocalStack** in Docker. Set `MINIO_ENDPOINT`/`MINIO_PUBLIC_URL` to point at any S3-compatible service (MinIO, AWS S3, LocalStack...).

## Demo flow

Register a user from the UI, create a shop and product, publish a lot expiring
within 48 hours (add a photo), reserve as a customer, then log in as the
business and confirm pickup using the displayed reference and code. Start the
Celery worker and scheduler with `docker compose up worker scheduler` to
process promo jobs and lot expiration asynchronously.

## Project documentation

- [Architecture and data model](docs/architecture.md)
- [API guide](docs/api.md)
- [Model and AI evaluation](docs/evaluation.md)
- [Security notes and release checklist](docs/security.md)
- [Deployment and operations](docs/deployment.md)
- [Live demo script](docs/demo-script.md)
- [Architecture decision records](docs/adr/)

There is no public production deployment or committed product screenshot yet.
See the release checklist in [`docs/security.md`](docs/security.md) before
publishing.

### Resumen en español

SobraCero conecta comercios con personas que quieren rescatar alimentos
próximos a vencer. Las cuentas de comercio pueden cargar 60 días de ventas de
ejemplo y consultar una estimación explicable del riesgo de desperdicio por
lote; esos datos solo son visibles para el comercio propietario. Las cuentas
de cliente pueden reservar lotes y reciben una referencia y un código único
para recogerlos; el comercio confirma la recogida. El OCR propone fechas de
vencimiento a partir de una foto, pero siempre requiere confirmación humana.
Las cuentas para bancos de alimentos todavía no están implementadas. No hay
despliegue público de producción verificado.