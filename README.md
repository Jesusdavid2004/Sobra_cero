# SobraCero MVP

SobraCero is a food-rescue marketplace: shops publish lots close to expiry and neighbors reserve or donate them. The repository is a two-application monorepo with FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL, MinIO, Next.js and Tailwind.

## Run locally

1. Copy `.env.example` to `.env`.
2. Run `docker-compose up --build`.
3. In another terminal run `docker-compose exec backend python seed_data.py`.
4. Open `http://localhost:3000` and API documentation at `http://localhost:8000/docs`.

The demo account is `demo@sobracero.local` with password `password123`. Do not use it outside local development.

For a no-Docker backend test run, create a Python 3.12 virtual environment, install `app-backend/requirements.txt`, set `PYTHONPATH=app-backend`, and run `pytest app-backend/tests`.

## MVP endpoints

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/shops`, `POST /api/v1/shops/{id}/products`
- `GET/POST /api/v1/lots`, `POST /api/v1/lots/{id}/image`
- `POST /api/v1/lots/{id}/reserve`, `POST /api/v1/lots/{id}/donate`
- `POST /api/v1/lots/{id}/generate-promos`, `GET /api/v1/lots/{id}/promos`
- `GET /api/v1/shops/{id}/forecast`, `GET /api/v1/admin/report`

Promo generation uses Celery when Redis is available and a deterministic local fallback otherwise. The generated prompt is persisted for auditability. The OpenAI key is intentionally optional and never committed.

## Quality and scope notes

CI runs backend tests/format checks and frontend build on pushes and pull requests to `develop`. Alembic is included for migration workflows; the MVP also creates tables on startup so a fresh Docker environment is immediately usable. MinIO upload wiring is represented by validated upload metadata in this first release; replacing the local URL assignment with the S3 adapter is the next production-hardening step.

## Demo flow

Register a user through Swagger, create a shop and product, create a lot expiring within 48 hours, open the vitrine, reserve a quantity, and call `generate-promos`. Start the Celery worker with `docker-compose up worker` to process the asynchronous job.
