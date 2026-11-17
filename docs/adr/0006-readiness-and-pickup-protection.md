# ADR 0006: Dependency readiness and pickup-attempt protection

- Status: Accepted

## Context

The API's liveness endpoint was returning success without showing whether
critical state services were usable. Reservation pickup also verifies an
eight-character code, so repeated attempts should be bounded at the route.

## Decision

- Keep `GET /health` as a liveness-only response.
- Add `GET /ready` that executes a database query and pings Redis; return
  `503` on dependency errors without exposing dependency details.
- Apply the existing sliding-window limiter to pickup confirmation at five
  requests per minute per client IP.
- Preserve API-level business-role, ownership, reservation-state, and pickup
  code checks; test customer and non-owning-business failures.

## Consequences

- Orchestrators can use liveness and readiness for different purposes.
- Local and single-process deployments have a basic pickup-guessing control.
- The limiter remains in memory and is neither distributed nor per-user. A
  production multi-replica deployment must add trusted-proxy handling and a
  shared edge or gateway limiter.
- Readiness does not currently probe S3-compatible storage or the AI provider.
