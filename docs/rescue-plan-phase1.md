# Phase 1 audit and design: Rescue Plan

Read-only audit of the backend on 2026-11-10. Nothing was executed; findings
come from reading `services.py`, `main.py`, `models.py`, `domain/`,
`application/` and `dependencies.py`.

## What exists and can be reused

- `CalculateWasteRiskUseCase` + `PredictionModel` port: expected sales and
  units at risk per lot (weekday model or moving-average baseline). Reusable as
  the numeric source; the rescue plan must not duplicate that math.
- `lots.quantity` is already net of reservations (`reserve_lot` decrements it
  with a guarded `UPDATE`), so it is the uncommitted stock that may be
  discounted or offered for donation.
- `Batch`/`OfferType` in the domain and `DISCOUNT`/risk constants in
  `domain/rules.py` (`DONATION_SUGGEST_THRESHOLD = 85` is defined but unused).
- Ownership pattern (`lot.shop.owner_id`) and the typed-exception handlers.

## Gaps that shape the design

1. **No pickup window.** Horizon is `expires_at.date() - today` in whole days.
   The proposal needs a pickup deadline; `lots` has no such column.
2. **The risk endpoint has side effects.** `GET /shops/{id}/waste-risk` calls
   the AI provider per lot and writes `waste_predictions` on every read. The
   rescue plan must be an explicit action, not a GET with writes, and must not
   need the LLM to produce numbers or decisions.
3. **Insufficient history raises** (`< 14` days). The plan must return an
   explicit `insufficient_history` state instead of an error or a guess.
4. **Donation is immediate and unaudited.** `donate_lot` subtracts stock with
   no approval, receiver or status. Phase 1 must not change it; the receiver
   flow belongs to the later donation phase.
5. **No audit trail.** Nothing links recommendation, approval and outcome.
6. **`main.py` is a monolith.** New routes go in
   `presentation/routers/rescue.py` with use cases, not in `main.py`.
7. Next migration number is `0007`. Railway builds `app-backend/Dockerfile`
   and migrations run at API startup, so the migration must be additive and
   backward compatible (nullable column, new tables).

## Proposed design

**Domain** (`domain/rescue.py`, pure, no I/O)
- Enums: `RescueAction` (`keep_offer`, `apply_discount_rule`,
  `prepare_donation_offer`, `insufficient_history`), `RescuePlanStatus`
  (`pending_approval`, `approved`, `rejected`, `superseded`),
  `RescueReason` (stable codes translated by the frontend, e.g.
  `stock_exceeds_expected_sales`, `insufficient_history`,
  `pickup_window_short`).
- Rule function `decide_rescue(available, expected_sales, hours_left, ...)`
  using named constants: surplus ratio thresholds and a discount ladder capped
  by `MAX_DISCOUNT_PERCENT`. It is a configurable heuristic, not a trained
  price-elasticity model, and the plan says so.
- `RescuePlan` entity enforces legal status transitions.

**Application**
- `GenerateRescuePlan.execute(lot_id, actor)`: loads a snapshot (stock, history,
  horizon), calls the existing prediction port, applies the domain rule,
  supersedes any older pending plan, persists the plan with its input snapshot,
  rule version and model version. No AI call.
- `DecideRescuePlan.execute(plan_id, actor, decision)`: owner/admin only,
  idempotent (repeating the same decision returns the same result), rejects a
  plan whose lot stock changed since generation (`RescuePlanStaleError`).
  Approving `apply_discount_rule` applies the discount in the same
  transaction; approving `prepare_donation_offer` only records the approval
  (no stock change until the receiver phase).

**Infrastructure**: `rescue_plans` (snapshot JSON, quantities, action, reasons,
rule/model versions, status, decided_by/at) and append-only
`rescue_plan_events`; migration `0007`, plus nullable `lots.pickup_ends_at`.

**Presentation** (`/api/v1`, ~15 lines per handler)
- `POST /lots/{lot_id}/rescue-plan`
- `GET /shops/{shop_id}/rescue-plans`
- `POST /rescue-plans/{plan_id}/approve` and `/reject`
- Errors as `{code, message_key}` for the new routes; `lots` create/response
  accept optional `pickup_ends_at`.

**Tests** (SQLite for unit/integration as today, real Postgres run noted
separately): domain rule table, use cases with fakes, cross-shop access denied,
double approval does not apply the discount twice, stale stock rejected,
insufficient history, unauthenticated/customer denied.

## Explicitly out of scope for Phase 1

gRPC extraction (Phase 2), UI, WebSockets, receiver accounts and donation
matching, QR pickup, impact metrics, and any change to existing reservation or
donation behavior.

## Open decisions (defaults proposed)

- Add nullable `lots.pickup_ends_at` and use `min(expires_at, pickup_ends_at)`
  as the horizon (default: yes).
- Heuristic defaults: surplus ratio >= 0.5 of stock suggests donation prep,
  0.2-0.5 suggests a discount step, below 0.2 keeps the offer (default: yes).
