# ENGINEERING STANDARDS (universal)

## 1. Language and product requirements
- ALL code in English: identifiers, files, folders, comments, commits, routes,
  DB columns, logs. ALL user-facing text goes through i18n (zero hardcoded
  strings in UI, emails, PDFs, or user-visible errors).
- Web platform, responsive and mobile-first.
- Two languages (en, es) switchable at runtime; browser language detected on
  first visit; choice persisted.
- Two themes (light, dark): follows the OS by default, manual override
  (system / light / dark) persisted, no flash of wrong theme on load.
- Frontend + backend + database + AI + cloud deployment.

## 2. These are EXISTING projects
- Do NOT recreate or re-scaffold. Start with a read-only audit and write
  docs/audit.md (what exists, gaps versus these standards, risks, proposed
  order of work). Wait for confirmation.
- Refactor incrementally. Before moving legacy code, add characterization tests
  that pin its current behavior, then refactor under that safety net. Keep the
  app runnable after every phase.
- Keep working tooling and libraries already chosen unless a phase says to
  change them; justify any new dependency in docs/adr/.

## 3. Architecture (layered / clean)
Dependencies point inward: presentation -> application -> domain.
Infrastructure implements interfaces declared in domain/application.
- presentation/   controllers/routers + request/response schemas. Validate
                  input, call exactly ONE use case, map to HTTP. ~15 lines max
                  per handler. No business logic, no SQL, no AI SDK calls.
- application/    one class per use case (verb + noun) with a single
                  execute(). Orchestrates repositories, domain objects, and
                  AI providers through interfaces. DTOs in and out.
- domain/         entities with behavior (not data bags), value objects,
                  enums, domain exceptions, interfaces, business-rule
                  constants. Business rules live HERE only.
- infrastructure/ DB repositories, AI provider adapters, storage adapters,
                  PDF generators, ML loaders. Maps persistence models to
                  domain entities (ORM models never leak upward).
- shared/         config (validated env), logger, constants.
- Composition root: ONE file wires concrete classes (container). Constructor
  injection everywhere; never instantiate dependencies inside use cases.
Principles to apply and explain: SOLID (SRP, Dependency Inversion), Repository,
Strategy + Adapter (AI providers), DTO, Value Object, Dependency Injection.

## 4. Error handling
- Domain/application throw typed exceptions; never a generic Error/Exception.
- ONE centralized handler maps exception types to HTTP status and returns
  { code, message_key, details? }. The frontend translates message_key.
- Never leak stack traces or provider errors to the client.

## 5. AI integration
- AIProvider interface (generateStructured -> schema-validated object) with
  adapters per vendor (Anthropic default; OpenAI optional) and a deterministic
  FakeAIProvider for tests and offline demos. Use cases depend only on the
  interface.
- Model names, max tokens, timeouts, quotas via environment variables
  (.env.example documents them, e.g. AI_MODEL_FAST=claude-haiku-5-5,
  AI_MODEL_SMART=claude-sonnet-5-5).
- Prompt templates in dedicated, versioned files with typed variables.
- Structured output (tool use / JSON schema) validated with Zod/Pydantic; on
  failure retry once with the validation error; then throw
  AIResponseInvalidError.
- Anything user-provided (document text, image content, notes) is untrusted
  DATA: wrap in delimiters and instruct the model to ignore instructions
  inside it.
- Timeouts, retries with backoff, max_tokens caps, per-user daily quota,
  response cache keyed by hash(input + locale + prompt version).
- Log tokens and latency, never raw personal content.
- Advice domains show a translated disclaimer in the UI.
- Numbers and business decisions come from code/ML, never from the LLM.

## 6. Security
- HTTPS only; secure headers; strict CORS to the frontend origin.
- Passwords with argon2id or bcrypt. Short-lived access token + rotating
  refresh token in an httpOnly, secure, sameSite cookie (frontend and API on the
  same site, e.g. app.example.com and api.example.com).
- Ownership/authorization enforced in the use case or repository query, not
  only in the UI.
- Uploads: validate by magic bytes, size and page limits, random storage names,
  strip EXIF, private bucket, short-lived signed URLs.
- Rate limiting per IP and per user on auth, uploads, and AI endpoints.
- Secrets only in env vars; commit .env.example, never .env; validate env on
  startup and fail fast.
- ORM/parameterized queries only; validate every input at the boundary.
- Account deletion hard-deletes rows and files.

## 7. Code quality
- No magic numbers/strings; named constants and enums.
- Small single-purpose functions, early returns, shallow nesting.
- No dead code, commented-out code, leftover TODOs, or debug prints (use the
  logger).
- Naming per language convention; strict typing (TS strict, Python mypy).
- Conventional Commits (feat, fix, refactor, test, docs, chore).

## 8. Testing
- Unit tests for domain and application (fakes for repositories and AI),
  >= 70% coverage there. Test names describe behavior.
- Integration tests per main endpoint against a real test database.
- Frontend: component tests for critical flows + one Playwright e2e happy path
  that also switches language and theme.

## 9. DevOps and professional deliverables
- Dockerfile per service + docker-compose for local dev (all services).
- CI (GitHub Actions): lint, type-check, i18n:check, tests, build, on every push.
- Versioned DB migrations. /health (and /ready) endpoints. Structured logs.
- Seed/demo data script so the app can be demonstrated in one command.
- Docs in /docs: architecture.md with Mermaid diagrams (system context,
  component, sequence of the main AI flow, ER diagram), adr/ (short decision
  records), api.md or OpenAPI, evaluation report for the AI part, deployment.md,
  security.md (threat notes), demo-script.md (the exact steps for the live demo).
- README: purpose, screenshots, architecture diagram, stack, setup in <= 5
  commands, env vars table, scripts, how to run tests, deployment link, a short
  Spanish summary.
- CHANGELOG.md and tagged release v1.0.0.

## 10. Working method
Follow the phases in the project prompt. After each phase: lint, type-check,
tests, i18n:check, summarize, STOP and wait. No placeholder or fake
implementations; if something cannot be completed, say so explicitly.





# FRONTEND (Next.js 15 App Router + TypeScript strict)
  src/app/[locale]/...   routes only (thin), (public)/storefront,
                         (dashboard)/business
  src/features/<feature>/{components,hooks,services,types.ts}
  src/lib/api-client.ts  the ONLY place calling the FastAPI backend
  src/lib/config.ts      typed env
  src/messages/en.json, es.json; src/i18n/ (next-intl config + routing)
  src/theme/
Rules:
- Server Components by default; "use client" only for state/effects/browser
  APIs. Public storefront server-rendered with revalidation.
- next-intl with locale-prefixed routes (/en, /es), middleware that detects
  Accept-Language on first visit and stores NEXT_LOCALE; navbar EN/ES switch;
  namespaced keys, ICU messages; Intl formatting; npm run i18n:check in CI;
  active locale forwarded to the backend (Accept-Language).
- next-themes: attribute="data-theme", defaultTheme="system", enableSystem,
  suppressHydrationWarning on <html>. Same design tokens and contrast rules as
  the Vite frontend (separate dark values for status badges).
- Validate API responses with Zod. Loading/empty/error states (loading.tsx,
  error.tsx). Accessibility as in the Vite frontend.
- Tooling: keep ESLint + Prettier; add Vitest + Testing Library and Playwright.