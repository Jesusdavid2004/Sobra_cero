# SobraCero audit

## Scope and method

This is a source-level audit for Phase 0 of the project prompt. It describes
the current repository and compares it with `CLAUDE.md` and the supplied
product/build prompt. No application code, database, or runtime state was
changed. Tests and runtime behavior were not executed as part of this
read-only phase.

## Current structure

- `app-frontend/`: Next.js 15 App Router, React 19, TypeScript (`strict`),
  Tailwind CSS, ESLint, and Prettier. Routes currently cover the home/market,
  login, registration, business shop dashboard, lot creation/detail, and admin
  report. Locale dictionaries exist in `i18n/en.json` and `i18n/es.json`.
- `app-backend/`: Python 3.12, FastAPI, Pydantic, SQLAlchemy, and Alembic.
  A partial layered structure exists under `app/domain`,
  `app/application`, and `app/infrastructure`; most HTTP routes and much of
  the business/persistence logic remain in `app/main.py` and `app/services.py`.
- `docker-compose.yml`: PostgreSQL 16, Redis 7, LocalStack S3, API, Celery
  worker, and frontend.
- `scripts/`: PowerShell and shell smoke-test scripts.
- `.github/workflows/ci.yml`: backend tests/coverage/format/type checks and
  frontend build/format checks.
- `README.md` and `CHANGELOG.md` document the MVP. Before this audit there was
  no `docs/` directory; this document creates its initial contents.
  `CLAUDE.md` and `design/` were already untracked when this audit began and
  are not included in the audit commit.

## Existing API surface

- Health: `GET /health`.
- Authentication: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`,
  `GET /api/v1/auth/me`.
- Shops/products: `GET/POST /api/v1/shops`,
  `GET/POST /api/v1/shops/{shop_id}/products`,
  `POST /api/v1/products/{product_id}/sales-history`,
  `POST /api/v1/shops/{shop_id}/sales-history/sample`.
- Risk: `GET /api/v1/shops/{shop_id}/waste-risk`.
- Lots: `GET/POST /api/v1/lots`, `GET /api/v1/lots/{lot_id}`,
  `POST /api/v1/lots/{lot_id}/image`,
  `POST /api/v1/lots/{lot_id}/reserve`,
  `POST /api/v1/lots/{lot_id}/donate`,
  `POST /api/v1/lots/{lot_id}/generate-promos`,
  `GET /api/v1/lots/{lot_id}/promos`.
- Reporting: `GET /api/v1/shops/{shop_id}/forecast`,
  `GET /api/v1/admin/report`.

There are no refresh/logout, business-onboarding, CSV-import, batch
publish/update, photo-expiration OCR, structured promo suggestion, reservation
history/cancel/pickup confirmation, donation-request, or admin model-training
endpoints yet.

## Data and behavior currently present

The ORM models are `User`, `Shop`, `Product`, `Lot`, `Reservation`, `Donation`,
`Promotion`, `SalesHistory`, and `WastePrediction`. Roles are business/customer;
there is no food-bank role or `Business`, `Batch`, `SalesRecord`, reservation
lifecycle, or ML model registry entity. Sales history is private through the
owner-checked business risk endpoint, and the public lot response does not
include it.

There is a `RiskScore` value object, a prediction port, a sales-history
repository, a `CalculateWasteRiskUseCase`, and a weighted moving-average
predictor. It uses recent sales and weekday averages, not a trained model,
time-series evaluation, baseline comparison, model artifact, or active model
registry. The shop forecast endpoint currently derives a seven-day series
directly from the lot count rather than a forecasting model.

The LLM supports a deterministic mock and OpenAI-compatible text completion.
It is invoked for plain-text promotional copy and risk recommendations. There
is no structured/schema-validated output, Anthropic adapter, retry/cache/quota
policy, vision/OCR provider, or enforceable recommendation DTO/domain clamp.
Celery is used for promotion generation; no periodic expiry task or Celery Beat
configuration was found.

Alembic migrations exist, but `0001_initial.py` is empty and initial tables are
created with `Base.metadata.create_all()` on API startup. Later migrations add
sales/prediction tables and role/category/pickup-code fields. This makes
migration history an incomplete source of truth for a fresh production
database.

## Authentication and security findings

- Authentication currently uses `python-jose[cryptography]==3.3.0` and
  `passlib[bcrypt]==1.7.4`; `bcrypt==4.0.1` is pinned for Passlib
  compatibility. Password hashing is configured for bcrypt and access tokens
  are HS256 JWTs with a configurable 60-minute expiry.
- There is no refresh token, token rotation, or logout/revocation flow.
  The frontend stores the bearer token in `localStorage`, rather than an
  `httpOnly`, `secure`, `sameSite` cookie. This falls short of the session
  security requirement in `CLAUDE.md`.
- `Settings` supplies a development JWT secret as its default and does not
  reject it at startup. Production configuration should fail fast if secrets
  are missing or unsafe.
- Rate limiting is an in-memory IP/path bucket, so it is not shared across
  workers/replicas and is not per-user. Only selected routes have the
  dependency attached.
- Image upload trusts the declared content type (not file magic bytes), has a
  5 MiB limit, uses the client filename in the object key, and returns a
  public URL. The prompt instead requires random object names, content
  validation, private storage, and short-lived signed URLs.
- Donation creation is authenticated but does not check a food-bank/customer
  role or shop ownership. Promotion listing is public and includes the stored
  prompt text. These endpoints need authorization/privacy decisions during
  the corresponding persistence and feature phases.
- Error handling is not yet centralized in the required `{code,
  message_key, details?}` shape. Several handlers raise `HTTPException`
  directly, and the frontend displays backend error text directly.

These are source-review observations, not a dependency vulnerability scan or
penetration test. The versions above should be assessed against current
security advisories before production.

## Frontend gaps

- Locale selection is implemented in a client-side provider using local
  storage/browser language, with dictionaries in JSON. Routes are not
  locale-prefixed, `next-intl` middleware/cookie detection is absent, and
  several visible strings are hardcoded in components/pages instead of using
  message keys.
- Theme state supports a light/dark toggle and checks the OS preference on
  initial client mount. There is no persisted `system/light/dark` choice,
  `next-themes` integration, or pre-hydration application of the theme, so the
  initial render may flash the wrong theme.
- `lib/api.ts` centralizes API calls, but response types are TypeScript-only;
  runtime response validation with Zod is absent.
- Vitest, Testing Library, Playwright, loading/error route files, and an
  `i18n:check` script are absent. The current public marketplace is
  client-rendered rather than server-rendered with revalidation.

## Quality, tests, and delivery gaps

- Backend test coverage includes API/integration, services, migrations,
  promotions, seed data, and risk behavior. CI enforces 70% coverage for the
  domain/application packages, plus Black, isort, Flake8, and mypy; mypy is
  not configured as strict for the specified layers.
- CI does not explicitly run frontend lint, frontend type-check, i18n
  validation, Vitest, or Playwright. There is no requirement-coverage test for
  a concurrent reservation race.
- `/ready`, structured logging, model evaluation documentation, architecture
  diagrams, ADRs, API/deployment/security/demo documentation, and the
  requested complete setup/test/deployment README material are absent or
  incomplete.
- No public HTTPS deployment or `v1.0.0` release/tag was verified during this
  source-only audit.

## Recommended implementation order

Follow the prompt's phase gates and keep the application runnable:

1. **Phase 1 — Tooling and frontend foundations:** add frontend test/i18n
   tooling and CI gates; implement locale-prefixed routing and persistent
   system/light/dark theme behavior; expand smoke coverage. Avoid mixing the
   broader backend refactor into this phase.
2. **Phase 2 — Backend domain/application/auth:** define business/batch domain
   behavior, typed errors and use cases; add characterization tests before
   moving legacy behavior; adopt maintained auth libraries and secure
   refresh-session handling.
3. **Phases 3–4 — Persistence and catalog/sales:** make migrations the schema
   source of truth; add roles, ownership, storage boundaries, sales import,
   and deterministic demo data.
4. **Phase 5 — Trained ML pipeline:** build features, time-based evaluation,
   baseline comparison, model registry/artifacts and explicit no-model
   behavior. Keep arithmetic/risk rules out of the LLM.
5. **Phase 6 — Batches/reservations/expiry:** implement lifecycle rules,
   concurrency-safe stock changes and a simultaneous-reservation test,
   scheduled expiry, and photo storage controls.
6. **Phase 7 — AI and vision:** structured provider interface/adapters,
   validated outputs, retry/cache/quota, bounded suggestions, and
   confirmation-required expiration reads.
7. **Phase 8 — Product frontend:** storefront, dashboard, workflows and all
   loading/empty/error states with server rendering where specified.
8. **Phase 9 — Hardening and end-to-end validation:** security controls,
   cross-role ownership tests, and Playwright publish-to-pickup flow with
   locale/theme changes.
9. **Phase 10 — Delivery documentation/deployment:** architecture/ADRs,
   evaluation and operations docs, deployment, changelog, and release only
   after acceptance criteria pass.

After each phase, run its applicable lint, type-check, tests, build, and
internationalization checks; report the evidence and stop for confirmation
before starting the next phase, as required by `CLAUDE.md`.
