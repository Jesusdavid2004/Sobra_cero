# ADR 0008: Live lot stock over WebSockets

- Status: Accepted

## Context

A customer looking at a lot should see its stock change when someone else reserves, and the owner
should see it too, without reloading. Reservations already change stock with conditional updates
that are safe under concurrency (see `tests/test_concurrency.py`); the open question was how to
tell browsers without creating a second implementation of the reservation rules.

## Decision

- **Changes stay on HTTPS.** Authentication, validation and the transaction remain in the existing
  endpoints. The socket only delivers public facts: lot id, version, quantity, status and
  discount, the same data `GET /lots/{id}` already exposes. It never carries pickup codes or
  personal data.
- **A version per lot** (`lots.version`, migration 0008) increases in the same statement that
  changes stock or price. A client applies an event only if its version is newer.
- **Publish after commit, best effort.** `notify_lot_changed` runs after the commit and swallows
  broker failures, so realtime can never fail a reservation. Delivery is at most once, so a client
  subscribes again after every reconnect and receives a snapshot read from PostgreSQL.
- **Broker is a setting.** `REALTIME_BROKER=memory` (default) delivers inside one process and is
  enough for a single replica. `redis` publishes on Redis Pub/Sub and every process forwards
  messages to its own connections, so several replicas work. Redis is only a hint that something
  changed; PostgreSQL stays the authority.
- **Hardening.** Origin must match `CORS_ORIGINS`, messages are size-limited and validated,
  subscriptions per connection and messages per window are capped, and the endpoint is public
  because the data is public.
- No new dependencies: `websockets` already ships with `uvicorn[standard]` and `redis` is already
  used.

## Consequences

- A lost event is repaired by the next event or the next snapshot; it is never trusted as state.
- A transactional outbox would make delivery reliable; it is not needed while the snapshot on
  reconnect covers the gap, and can be added later without changing the wire format.
- Owner-only events (new reservations, pickups) would need an authenticated channel; this ADR
  covers the public lot channel only.
- SSE would also fit a server-to-browser stream. WebSockets were chosen because they are part of
  the course material and leave room for authenticated, bidirectional features.
