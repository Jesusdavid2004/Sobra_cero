# Deployment and operations

## Local Docker Compose

Prerequisites: Docker Desktop (or Docker Engine with Compose) and a local copy
of this repository. Do not replace an existing `.env`.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
docker compose exec backend python seed_data.py
Invoke-WebRequest http://localhost:8000/health
Invoke-WebRequest http://localhost:8000/ready
```

Open the application at `http://localhost:3000/en` or `http://localhost:3000/es`,
API documentation at `http://localhost:8000/docs`, and PostgreSQL at host port
5433. The Compose stack starts PostgreSQL, Redis, LocalStack, API, Celery
worker, Celery scheduler, and frontend. The API applies Alembic migrations on
startup. The demo account is documented in the root README and must remain
development-only.

Useful operational commands:

```powershell
docker compose ps
docker compose logs --tail 100 backend worker scheduler
docker compose logs -f backend
docker compose down
```

`docker compose down` preserves named data volumes. To discard local
development data, remove volumes only after verifying the target project and
obtaining approval; this is intentionally not part of the normal stop command.

## Configuration

| Variable | Purpose | Local default / guidance |
| --- | --- | --- |
| `APP_ENVIRONMENT` | Settings and production safety validation. | `development`; use `production` only with production secrets and dependencies. |
| `DATABASE_URL` | SQLAlchemy connection URL. | Compose overrides the host URL to reach its PostgreSQL service. |
| `REDIS_URL` | Refresh sessions, AI cache/quota, and Celery broker/backend. | Compose uses `redis://redis:6379/0`. |
| `JWT_SECRET` | Signs access and refresh JWTs. | Example value is development-only; production requires a unique value of at least 32 characters. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime. | `15`. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-session lifetime. | `30`. |
| `REFRESH_COOKIE_NAME` | Refresh cookie name. | `sc_refresh`. |
| `REFRESH_COOKIE_SECURE` | Restrict refresh cookie to HTTPS. | `false` locally; required in production. |
| `REFRESH_COOKIE_SAMESITE` | SameSite policy for refresh cookie. | `lax`; `none` requires Secure. |
| `CORS_ORIGINS` | Comma-separated trusted browser origins. | `http://localhost:3000`; set exact HTTPS origin(s) in production. |
| `MINIO_ENDPOINT`, `MINIO_PUBLIC_URL` | S3-compatible API and browser-reachable signing endpoint. | LocalStack in Compose; public URL must be reachable by the browser. |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Object-storage credentials. | Local-only example credentials; replace in production. |
| `MINIO_BUCKET`, `MINIO_SECURE` | Private image bucket and TLS selection. | `lots`, `false` locally. |
| `LLM_PROVIDER` | AI adapter selection. | `mock` locally; production rejects mock. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LLM_API_KEY` | Provider credentials. | Leave blank for mock; store production values in a secret manager. |
| `LLM_BASE_URL`, `LLM_MODEL` | OpenAI-compatible provider configuration. | Configure only for selected provider. |
| `AI_MODEL_FAST`, `AI_MODEL_SMART` | Anthropic model tiers. | `claude-haiku-5-5`, `claude-sonnet-5-5`. |
| `AI_MAX_TOKENS`, `AI_TIMEOUT_SECONDS` | Bound provider output and duration. | `512`, `20`. |
| `AI_DAILY_QUOTA`, `AI_CACHE_TTL_SECONDS` | Per-user request quota and cached result lifetime. | `25`, `900`. |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base URL compiled into Next.js. | `http://localhost:8000/api/v1`; it must resolve from the user's browser. |

Never commit `.env` or put credentials in frontend `NEXT_PUBLIC_*` variables.
Keep `.env.example` free of real secrets.

## Schema, seed data, and scheduled work

- Alembic owns the schema. API startup upgrades to `head`; run
  `docker compose exec backend alembic current` to inspect the database
  revision.
- `docker compose exec backend python seed_data.py` creates/updates local demo
  data and is safe to rerun.
- Celery worker processes promotion jobs. Celery Beat schedules due-lot and
  reservation expiry every 60 seconds. Monitor both `worker` and `scheduler`
  logs; a running API alone does not execute scheduled work.
- `/health` is a liveness check. `/ready` checks PostgreSQL and Redis only.

## Backups and recovery

For a local logical database backup:

```powershell
docker compose exec -T postgres pg_dump -U sobracero sobracero > sobracero-backup.sql
```

Object images and database records are separate state. A production backup plan
must cover the database, private image bucket, Redis/session behavior, key
management, retention, encryption, restore order, and a regularly tested
recovery procedure. The Compose stack is not that plan.

## Production deployment status

This repository contains local Compose build files, but no production
environment, domain, TLS termination, managed-service provisioning, secret
manager, or deployment pipeline has been verified. No cloud resources were
created during this phase. Do not expose the development Compose stack as a
production deployment. Complete the security release checklist in
[`security.md`](./security.md) and validate a selected hosting platform before
publishing a production release.
