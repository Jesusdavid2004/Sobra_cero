# API guide

The FastAPI OpenAPI document is available at `http://localhost:8000/docs` when
running locally. JSON endpoints are rooted at `/api/v1`. The web client sends
the active locale in `Accept-Language`.

## Health and readiness

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness response; does not check dependencies. |
| `GET` | `/ready` | Checks database query and Redis ping; returns `503` if either fails. |

## Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Create an account and start a session. |
| `POST` | `/api/v1/auth/login` | Authenticate and start a session. |
| `POST` | `/api/v1/auth/refresh` | Rotate the refresh session cookie and issue an access token. |
| `POST` | `/api/v1/auth/logout` | Revoke the refresh session and clear its cookie. |
| `GET` | `/api/v1/auth/me` | Return the authenticated user and role. |

Access tokens are sent as bearer tokens and held in browser memory. Refresh
tokens are HttpOnly cookies; Redis is required for issuing, rotating, and
revoking sessions.

## Shops, products, and sales history

| Method | Path | Access |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/shops` | Authenticated; shop creation is for business accounts. |
| `GET`, `POST` | `/api/v1/shops/{shop_id}/products` | Authenticated; writes require business access and ownership. |
| `POST` | `/api/v1/products/{product_id}/sales-history` | Import historical rows for a product. |
| `POST` | `/api/v1/products/{product_id}/sales-history/csv` | Import UTF-8 CSV; owner/admin access. |
| `POST` | `/api/v1/shops/{shop_id}/sales-history/sample` | Load deterministic development data for an owned shop. |
| `GET` | `/api/v1/shops/{shop_id}/waste-risk` | Return shop-scoped risk results. |
| `GET` | `/api/v1/shops/{shop_id}/forecast` | Return the shop forecast series. |

Sales CSV columns are `sales_date,units_sold,had_promotion`. The date format is
`YYYY-MM-DD`; sales must be non-negative integers and promotion values must be
`true` or `false`. The upload is limited to 1 MiB and 90 data rows.

## Lots, reservations, and pickup

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/lots` | Public active-lot listing with optional expiry, discount, category, business-type, and geographic filters. |
| `POST` | `/api/v1/lots` | Create a lot for a shop/product owned by the authenticated business. |
| `GET` | `/api/v1/lots/{lot_id}` | Read a lot. |
| `POST` | `/api/v1/lots/{lot_id}/image` | Upload a validated image for the lot. |
| `POST` | `/api/v1/lots/{lot_id}/reserve` | Reserve available quantity as a customer. |
| `POST` | `/api/v1/lots/{lot_id}/donate` | Record a donation against a lot. |
| `POST` | `/api/v1/lots/{lot_id}/cancel` | Cancel an owned lot and its active reservations. |
| `POST` | `/api/v1/reservations/{reservation_id}/cancel` | Cancel the caller's active reservation. |
| `POST` | `/api/v1/reservations/{reservation_id}/pickup` | Confirm pickup for the owning business using the reservation ID and eight-character code. |

Reservations update stock transactionally, are unique per active
customer/lot pair, and return both a reservation reference and pickup code.
The shop confirms collection from the dashboard. Pickup confirmation is
limited to five requests per minute per client IP and is checked against the
owning shop and code.

## AI, image review, and administration

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/api/v1/lots/{lot_id}/expiry-scans` | Scan an owned lot image or review previous scan suggestions. |
| `POST` | `/api/v1/lots/{lot_id}/expiry-scans/{suggestion_id}/confirm` | Explicitly apply a suggested expiry date. |
| `POST` | `/api/v1/lots/{lot_id}/expiry-scans/{suggestion_id}/reject` | Reject an awaiting suggestion. |
| `POST` | `/api/v1/lots/{lot_id}/generate-promos` | Queue or generate promo text. |
| `GET` | `/api/v1/lots/{lot_id}/promos` | Read generated promo variants. |
| `POST` | `/api/v1/admin/models/sales-forecast/train` | Train/evaluate a sales model (admin only). |
| `GET` | `/api/v1/admin/report` | Read platform summary counts (admin only). |

Expiry suggestions do not change a lot until a business owner or admin confirms
them. See the API's generated OpenAPI schema for exact request/response models,
validation constraints, and status codes.

Errors currently use FastAPI's `detail` field and selected machine-readable
`code` values. Error responses have not all been migrated to a single
`message_key` contract.
