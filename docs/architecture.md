# SobraCero architecture

## System context

```mermaid
flowchart LR
    customer[Customer]
    business[Business]
    admin[Platform admin]
    browser[Browser]
    web[Next.js 15 frontend]
    api[FastAPI API]
    db[(PostgreSQL)]
    redis[(Redis)]
    objects[(Private S3-compatible object storage)]
    worker[Celery worker and Beat]
    ai[Configured AI provider]

    customer --> browser
    business --> browser
    admin --> browser
    browser --> web
    web -->|JSON API and HttpOnly refresh cookie| api
    api --> db
    api --> redis
    api --> objects
    api --> ai
    api -->|promotion and expiry tasks| redis
    worker --> redis
    worker --> db
    worker --> ai
```

Local development uses Docker Compose with PostgreSQL, Redis, LocalStack,
FastAPI, Celery worker/Beat, and Next.js. LocalStack implements the S3 API for
development; production storage must be configured separately.

## Main components

```mermaid
flowchart TB
    subgraph Client["Browser / Next.js"]
      pages["App Router pages and components"]
      providers["AppProviders: locale, theme, auth state"]
      client["lib/api.ts: API client and response validation"]
      pages --> providers
      pages --> client
    end
    subgraph Server["FastAPI application"]
      routes["main.py and auth router"]
      auth["Authentication and authorization"]
      usecases["Application use cases"]
      domain["Domain entities, rules, and ports"]
      services["Persistence-facing services"]
      adapters["SQLAlchemy repositories, Redis sessions, S3 storage, AI adapters"]
      routes --> auth
      routes --> usecases
      usecases --> domain
      routes --> services
      services --> adapters
    end
    subgraph Runtime["Runtime services"]
      postgres[(PostgreSQL)]
      redis[(Redis)]
      s3[(S3-compatible storage)]
      queue["Celery worker and scheduler"]
      provider["Mock, Anthropic, or OpenAI-compatible provider"]
    end
    client --> routes
    adapters --> postgres
    adapters --> redis
    adapters --> s3
    adapters --> provider
    routes --> redis
    queue --> redis
    queue --> postgres
```

The backend is layered in part, but not every route has been migrated to a
dedicated application use case. `main.py` remains the composition and HTTP
entry point for several workflows. SQLAlchemy models are persistence objects;
Alembic migrations are the source of truth for schema creation and evolution.

## Structured AI and expiry review

```mermaid
sequenceDiagram
    actor Business as Business user
    participant Web as Next.js
    participant API as FastAPI
    participant Store as Private object storage
    participant AI as Structured AI provider
    participant DB as PostgreSQL

    Business->>Web: Request date scan for an owned lot
    Web->>API: POST /api/v1/lots/{id}/expiry-scans
    API->>API: Authenticate, authorize owner/admin, enforce request limit
    API->>Store: Download private image
    Store-->>API: Image bytes and MIME type
    API->>API: Sanitize image and enforce size/pixel limits
    API->>AI: Request schema-constrained expiry-date result
    AI-->>API: Validate date and confidence with Pydantic
    API->>DB: Save awaiting_confirmation or unreadable suggestion
    API-->>Web: Return suggestion; never change lot expiry automatically
    Business->>Web: Explicitly confirm or reject suggestion
    Web->>API: POST confirm/reject endpoint
    API->>DB: Persist decision; confirmation applies accepted date
    API-->>Web: Return updated suggestion
```

AI recommendations are qualitative. Prices, stock, risk scores, and inventory
state are determined by application code or the forecast model rather than by
free-form AI output.

## Data model

```mermaid
erDiagram
    USER ||--o{ SHOP : owns
    SHOP ||--o{ PRODUCT : contains
    SHOP ||--o{ LOT : publishes
    PRODUCT ||--o{ LOT : describes
    USER ||--o{ RESERVATION : places
    LOT ||--o{ RESERVATION : receives
    LOT ||--o{ DONATION : records
    LOT ||--o{ PROMOTION : has
    LOT ||--o{ EXPIRY_SCAN_SUGGESTION : receives
    USER ||--o{ EXPIRY_SCAN_SUGGESTION : requests
    PRODUCT ||--o{ SALES_HISTORY : records
    PRODUCT ||--o{ WASTE_PREDICTION : informs
    LOT ||--o{ WASTE_PREDICTION : scores

    USER {
        int id PK
        string email
        string role
        boolean is_admin
    }
    SHOP {
        int id PK
        int owner_id FK
        string name
        string business_type
    }
    PRODUCT {
        int id PK
        int shop_id FK
        string name
        string category
    }
    LOT {
        int id PK
        int shop_id FK
        int product_id FK
        int quantity
        datetime expires_at
        string status
        string image_key
    }
    RESERVATION {
        int id PK
        int lot_id FK
        int user_id FK
        int quantity
        string pickup_code
        string status
    }
    SALES_HISTORY {
        int id PK
        int product_id FK
        date sales_date
        int units_sold
        boolean had_promotion
    }
    EXPIRY_SCAN_SUGGESTION {
        int id PK
        int lot_id FK
        int user_id FK
        date expires_on
        float confidence
        string status
    }
    SALES_FORECAST_MODEL {
        int id PK
        string version
        float baseline_mae
        float model_mae
        string status
        string active_slot
    }
```

`WASTE_PREDICTION` is a persisted result associated with a product and lot.
`SALES_FORECAST_MODEL` stores the JSON artifact, time-ordered evaluation
metrics, and the active-model marker. Some lifecycle details, such as promotion
variants, are omitted from the diagram for readability.

## Food-intelligence phase (2026-11)

This phase added a place directory and map, a data collection engine (the Scanner), donation
receivers, the daily shop diagnosis and declared waste. Dependencies keep pointing inward:
presentation, then application, then domain; infrastructure implements the interfaces declared
inside, and one composition root (`app/dependencies.py`) wires the concrete classes.

### System context with the new parts

```mermaid
flowchart LR
  Customer([Customer]) --> Web
  Owner([Shop owner]) --> Web
  Receiver([Receiving organization]) --> Web
  Admin([Administrator]) --> Web
  Web[Next.js frontend] -->|HTTPS + WebSocket| API[FastAPI backend]
  API --> DB[(PostgreSQL)]
  API --> Redis[(Redis)]
  API --> Storage[(S3-compatible storage)]
  API -->|structured output| LLM[Language model: Groq / Anthropic / OpenAI]
  API -->|gRPC, optional| Analysis[Analysis service]
  API -->|subprocess| Scraper[Scrapy engine]
  Scraper -->|polite requests| Sources[Public sources: OpenStreetMap, catalogs]
  API -->|1 req/s, cached| Nominatim[Geocoder]
  Worker[Celery worker and beat] --> DB
  Worker --> Scraper
```

### Components in the backend

```mermaid
flowchart TB
  subgraph presentation
    Routers[routers + schemas + error handlers]
  end
  subgraph application
    UseCases[use cases: one execute() each]
    Ports[ports: repositories, AI, geocoder, runner]
  end
  subgraph domain
    Rules[entities, value objects, rules, typed exceptions]
  end
  subgraph infrastructure
    Repos[SQLAlchemy repositories]
    Adapters[AI, geocoding and runner adapters]
  end
  Routers --> UseCases --> Rules
  UseCases --> Ports
  Repos -.implements.-> Ports
  Adapters -.implements.-> Ports
```

| Area | Domain rules | Notes |
| --- | --- | --- |
| Marketplace | `entities`, `rules`, `services.py` (first generation) | Atomic conditional updates; concurrency tests |
| Rescue | `rescue`, `simulation`, `timeline`, `impact` | Human approval, audit events, stale-plan protection |
| Discovery | `discovery`, `discovery_evaluation` | Feasibility by window, budget and distance |
| Donations | `receivers` | Hard rules first, then a fair order |
| Geography | `places`, `geocoding`, `opportunities` | Affiliation is never inferred |
| Collection (Scanner) | `external_data`, `collection`, `url_policy`, `source_policy` | Policy gate before any request |
| Intelligence | `diagnosis`, `waste` | Deterministic; the model only words |

### Daily diagnosis flow

```mermaid
sequenceDiagram
  participant O as Shop owner
  participant R as Router
  participant U as DiagnoseShop
  participant D as Domain (diagnose)
  participant P as AIProvider
  O->>R: GET /shops/{id}/diagnosis
  R->>U: execute(actor, shop, language)
  U->>D: snapshot -> facts, alerts, limitations
  U->>P: generate_structured(codes only)
  alt model answers
    P-->>U: narrative (no digits)
  else unavailable or quota
    P-->>U: error
    U-->>U: narrative = none
  end
  U-->>R: facts + alerts + limitations + narrative?
  R-->>O: JSON
```

### A Scanner run

```mermaid
sequenceDiagram
  participant A as Administrator
  participant API as RunSourceNow
  participant S as scraper.run (subprocess)
  participant G as Policy gate
  participant W as Source site
  A->>API: POST /admin/scanner/sources/{key}/run
  API->>S: python -m scraper.run --source key
  S->>G: enabled? terms reviewed? safe URL?
  alt refused
    G-->>S: reason
    S-->>API: stopped (not_allowed) recorded in history
  else allowed
    S->>W: robots.txt, then polite requests
    W-->>S: pages (stop on 401, 403, 429)
    S-->>API: counters, stop reason, rejected records
  end
  API-->>A: run summary
```

### Data model of the new tables

```mermaid
erDiagram
  external_sources ||--o{ external_businesses : finds
  external_sources ||--o{ external_products : lists
  external_products ||--o{ external_price_observations : "price history"
  external_sources ||--o{ scraping_executions : runs
  scraping_executions ||--o{ scraping_records : "rejected or pending"
  users ||--o| receivers : owns
  receivers ||--o{ donation_offers : receives
  lots ||--o{ donation_offers : "offered in"
  lots ||--o{ waste_records : "declared waste"
```

External data lives in its own tables and never becomes a lot, an offer or an affiliate.

### Frontend

Next.js App Router with next-intl (en/es), light/dark/system theme, Zod validation of every API
response and one module (`lib/api.ts`) that talks to the backend. Rendering per route is in the
frontend's `docs/rendering.md`: static, server-rendered, streaming, incremental regeneration and
client-rendered pages, each chosen for freshness and privacy.

### Deployment

Railway runs the backend, the frontend, PostgreSQL and Redis; a worker and a scheduler (Celery) are
optional services that run lot expiry and due Scanner sources. See `deployment.md`. The backend
image contains Scrapy so the same image can run the engine; the web process never imports it.

### Security

Argon2/bcrypt passwords, short-lived access tokens with a rotating refresh cookie, ownership checks
in use cases, per-client rate limits on authentication, AI, geocoding and pickup, SSRF protection for
source addresses, a terms-review gate for external data, and typed errors mapped centrally to
`{ code, message_key, details? }`. See `security.md`.
