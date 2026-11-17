# ADR 0002: Short-lived access tokens and Redis-backed refresh sessions

- Status: Accepted

## Context

The application needs short-lived API access tokens and revocable, rotating refresh
tokens without storing credentials in browser local storage or adding a database
migration for session records.

## Decision

- Use PyJWT for signed access and refresh tokens, and bcrypt directly for password
  hashing and verification. Existing bcrypt hashes remain verifiable.
- Keep access tokens in frontend memory and return them in the authentication
  response body. Use a 15-minute access-token lifetime.
- Store refresh-token identifiers in Redis with a 30-day TTL. Rotate tokens
  atomically with a Redis Lua script so an identifier can be consumed only once;
  revoke the identifier on logout.
- Send refresh tokens only in an HttpOnly cookie scoped to `/api/v1/auth`, with
  SameSite=Lax locally and Secure enabled in production.
- Restore sessions through the refresh endpoint and include credentials in API
  requests. Retry an unauthorized request once after a successful refresh.

## Consequences

- Redis is required for login, registration, refresh, and logout session
  operations. If it is unavailable, authentication returns a service-unavailable
  response rather than issuing an untracked refresh token.
- The frontend no longer persists access tokens across page loads; it restores
  the session from the HttpOnly refresh cookie instead.
- Refresh tokens are one-time-use. Replays are rejected, and the refresh cookie
  is cleared during logout.
- Production deployments must provide a unique JWT secret of at least 32
  characters and enable Secure cookies.
