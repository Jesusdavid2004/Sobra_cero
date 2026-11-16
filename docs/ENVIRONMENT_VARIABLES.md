# Environment variables

Read from the environment (or a `.env` file that is never committed). Secrets belong only in
`.env` or in the hosting provider's variables. Names match `app-backend/app/config.py`.

## Backend

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development` | `development`, `test` or `production`. Production refuses a weak JWT secret and insecure cookies. |
| `DATABASE_URL` | `sqlite:///./sobracero.db` | SQLAlchemy URL. PostgreSQL in production. |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery, sessions and the optional realtime broker. |
| `JWT_SECRET` | development value | At least 32 characters in production. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lifetime of the rotating refresh token. |
| `REFRESH_COOKIE_SECURE`, `REFRESH_COOKIE_SAMESITE`, `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_PATH` | see config | `SameSite=None` requires `Secure`. Frontend and API on different sites need `none`. |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origins, comma separated. |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_PUBLIC_URL`, `MINIO_SECURE`, `MINIO_REGION` | local defaults | S3-compatible storage for lot images. Placeholders make uploads fail with 503. |

### AI

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `mock` | `mock`, `openai`, `anthropic` or an OpenAI-compatible endpoint such as `groq`. |
| `LLM_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | empty | Provider key. Never commit or paste it in a chat. |
| `LLM_BASE_URL`, `LLM_MODEL` | empty, `gpt-4o-mini` | For OpenAI-compatible providers, for example `https://api.groq.com/openai/v1` and `openai/gpt-oss-20b`. |
| `AI_MODEL_FAST`, `AI_MODEL_SMART` | Claude names | Model per tier. |
| `AI_MAX_TOKENS` | `512` | Cap per response. |
| `AI_TIMEOUT_SECONDS` | `20` | Per request. |
| `AI_DAILY_QUOTA` | `25` | Requests per user per day. |
| `AI_CACHE_TTL_SECONDS` | `900` | Response cache keyed by input, locale and prompt version. |

### Map, geocoding and the Scanner

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEOCODER_PROVIDER` | `nominatim` | `nominatim` or `fake` (deterministic, no network). |
| `GEOCODER_USER_AGENT` | project name | Must identify the application; add real contact details in production. |
| `GEOCODER_BASE_URL` | public Nominatim | Point to your own instance or a paid provider if traffic grows. |
| `SCRAPER_ALLOWED_DOMAINS` | `overpass-api.de,exito.com,alkosto.com,jumbocolombia.com` | Domains a source may use. Subdomains are included. |
| `SCRAPER_DISABLE_URL_POLICY` | `false` | Skips the address safety policy outside production. For local test sites only. |
| `SCRAPER_USER_AGENT` | `SobraCeroBot/1.0 (...)` | Identifies the collector to the sites it reads. |
| `SCRAPER_DOWNLOAD_DELAY` | `2` | Seconds between requests to one site. |
| `SCRAPER_MAX_PAGES` | `50` | Page cap per run. |
| `SCRAPER_CACHE_DIR` | system temp | Where Scrapy caches responses. |
| `SCRAPER_LOG_LEVEL` | `INFO` | Scrapy log level. |

### Realtime and analysis

| Variable | Default | Purpose |
| --- | --- | --- |
| `REALTIME_BROKER` | `memory` | `memory` works with one backend process; use `redis` with several. |
| `REALTIME_MAX_SUBSCRIPTIONS`, `REALTIME_MAX_MESSAGE_BYTES`, `REALTIME_MESSAGES_PER_WINDOW` | `20`, `2048`, `30` | WebSocket limits. |
| `ANALYSIS_GRPC_TARGET`, `ANALYSIS_GRPC_TIMEOUT_SECONDS`, `ANALYSIS_SHARED_TOKEN` | empty, `2`, empty | Optional gRPC analysis service. A target requires the token. |

## Frontend

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Backend base URL, fixed at build time. |
| `NEXT_PUBLIC_MAP_TILE_URL` | public OpenStreetMap tiles | Tile URL template. Use a hosted provider before real traffic. |
| `NEXT_PUBLIC_MAP_ATTRIBUTION` | `© OpenStreetMap contributors` | Attribution shown on the map; keep it in line with the tile provider. |

`NEXT_PUBLIC_*` values are public: never put a secret in them.
