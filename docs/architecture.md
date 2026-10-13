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
