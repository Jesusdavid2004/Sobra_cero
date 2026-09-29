# SobraCero MVP

SobraCero is a food-rescue marketplace: shops publish lots close to expiry and neighbors reserve or donate them. The repository is a two-application monorepo with FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL, LocalStack (S3-compatible storage), Next.js and Tailwind.

## Run locally

1. Copy `.env.example` to `.env` (secrets stay local, never committed).
2. Run `docker compose up --build`.
3. In another terminal run `docker compose exec backend python seed_data.py`.
4. Open `http://localhost:3000` and API documentation at `http://localhost:8000/docs`.

> Note: PostgreSQL is published on host port **5433** to avoid clashing with a local PostgreSQL service. The local S3 endpoint is `http://localhost:4566` (LocalStack).

The demo account is `demo@sobracero.local` with password `password123`. Do not use it outside local development.

For a no-Docker backend test run, create a Python 3.12 virtual environment, install `app-backend/requirements.txt`, set `PYTHONPATH=app-backend`, and run `pytest app-backend/tests`.

## MVP endpoints

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/shops`, `GET/POST /api/v1/shops/{id}/products`
- `GET/POST /api/v1/lots`, `GET /api/v1/lots/{id}`, `POST /api/v1/lots/{id}/image`
- `POST /api/v1/lots/{id}/reserve`, `POST /api/v1/lots/{id}/donate`
- `POST /api/v1/lots/{id}/generate-promos`, `GET /api/v1/lots/{id}/promos`
- `GET /api/v1/shops/{id}/forecast`, `GET /api/v1/admin/report`

The public listing supports `expires_in`, `min_discount` and a geographic bounding box (`lat_min`, `lat_max`, `lng_min`, `lng_max`).

## Connected flow (v0.2.0)

The full demo flow is wired end-to-end:

1. Register/login from the UI (`/login`, `/register`) → JWT stored locally.
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

- CI runs `pytest`, `black`, `isort`, `flake8` and `mypy` for the backend and `eslint`, `prettier` and `next build` for the frontend on pushes/PRs to `develop`.
- Rate limiting (in-memory sliding window) protects image uploads and promo generation.
- Alembic is included for migration workflows; the MVP also creates tables on startup so a fresh Docker environment is immediately usable.
- Images are stored through an S3-compatible adapter backed by **LocalStack** in Docker (MinIO was archived upstream in 2026). Set `MINIO_ENDPOINT`/`MINIO_PUBLIC_URL` to point at any S3-compatible service (MinIO, AWS S3, LocalStack...).

## Demo flow

Register a user from the UI, create a shop and product, publish a lot expiring within 48 hours (add a photo), open the vitrine, reserve a quantity, and generate promos from the lot detail page. Start the Celery worker with `docker compose up worker` to process promo jobs asynchronously.