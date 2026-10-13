# SobraCero MVP

SobraCero is a food-rescue marketplace: shops publish lots close to expiry and neighbors reserve or donate them. The repository is a two-application monorepo with FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL, LocalStack (S3-compatible storage), Next.js and Tailwind.

## Run locally

1. Copy `.env.example` to `.env` (secrets stay local, never committed).
2. Run `docker compose up --build`.
3. In another terminal run `docker compose exec backend python seed_data.py`.
4. Open `http://localhost:3000` and API documentation at `http://localhost:8000/docs`.

> Note: PostgreSQL is published on host port **5433** to avoid clashing with a local PostgreSQL service. The local S3 endpoint is `http://localhost:4566` (LocalStack).

The demo account is `demo@sobracero.com` with password `password123`. Do not use it outside local development. Running the seed command again updates the legacy `.local` demo account and does not duplicate its demo shop, product, or lots.

For a no-Docker backend test run, create a Python 3.12 virtual environment, install `app-backend/requirements.txt`, set `PYTHONPATH=app-backend`, and run `pytest app-backend/tests`. To verify the required application/domain coverage locally, run `pytest --cov=app.domain --cov=app.application --cov-fail-under=70 app-backend/tests` from `app-backend` with `PYTHONPATH=.`.

## MVP endpoints

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/shops`, `GET/POST /api/v1/shops/{id}/products`
- `GET/POST /api/v1/lots`, `GET /api/v1/lots/{id}`, `POST /api/v1/lots/{id}/image`
- `POST /api/v1/lots/{id}/reserve`, `POST /api/v1/lots/{id}/donate`
- `POST /api/v1/lots/{id}/generate-promos`, `GET /api/v1/lots/{id}/promos`
- `GET /api/v1/shops/{id}/forecast`, `GET /api/v1/admin/report`
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

## Connected flow (v0.2.0)

The full demo flow is wired end-to-end:

1. Register/login from the UI (`/login`, `/register`) → short-lived access token kept in memory and a rotating refresh token in an HttpOnly cookie.
2. Dashboard `/shop`: create shops and products.
3. `/lots/new`: publish a lot (image optional, compressed on the client via canvas and stored in **S3-compatible storage** via LocalStack).
4. Vitrine `/`: lots appear with price, discount and expiry; reserve directly or open `/lots/{id}`.
5. `/lots/{id}`: reserve a quantity (atomic, reduces stock) and generate **3 promo variants**.
6. `/admin`: platform counts and a 7-day forecast.

Promo generation runs as a **Celery/Redis** job when available and falls back to an in-process run otherwise. The exact prompt used per variant is persisted for auditability.

## LLM provider (free options)

The promo generator uses an abstract client (`app/llm.py`) selected by `LLM_PROVIDER`:

| Provider | Setup | Cost |
|---|---|---|
| `mock` (default) | Nothing — deterministic texts | $0 |
| `ollama` | `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=llama3.1` (install Ollama) | $0, local |
| `groq` | Free account → API key, `LLM_BASE_URL=https://api.groq.com/openai/v1` | $0 |
| `openrouter` | Free account → use `:free` models | $0 |
| `openai` | API key from platform.openai.com (paid) | paid |

Any OpenAI-compatible endpoint works by setting `LLM_BASE_URL` and `LLM_MODEL`. No key is required for `mock` or `ollama`.

## Quality and scope notes

- CI runs backend tests with at least 70% coverage for domain/application, plus `black`, `isort`, `flake8` and `mypy`; the frontend runs `eslint`, `prettier` and `next build`.
- In-memory sliding-window rate limits protect reservations, image uploads and promo generation.
- Alembic is the source of truth for the database schema. The API and both backend data scripts apply pending migrations before accessing the database.
- Images are stored through an S3-compatible adapter backed by **LocalStack** in Docker (MinIO was archived upstream in 2026). Set `MINIO_ENDPOINT`/`MINIO_PUBLIC_URL` to point at any S3-compatible service (MinIO, AWS S3, LocalStack...).

## Demo flow

Register a user from the UI, create a shop and product, publish a lot expiring within 48 hours (add a photo), open the vitrine, reserve a quantity, and generate promos from the lot detail page. Start the Celery worker with `docker compose up worker` to process promo jobs asynchronously.

### Resumen en español

SobraCero conecta comercios con personas que quieren rescatar alimentos próximos a vencer. Las cuentas de comercio pueden cargar 60 días de ventas de ejemplo y consultar una estimación explicable del riesgo de desperdicio por lote; esos datos solo son visibles para el comercio propietario. Las cuentas de cliente pueden reservar lotes y reciben un código único para recogerlos. El OCR de fechas y las cuentas para bancos de alimentos todavía no están implementados.