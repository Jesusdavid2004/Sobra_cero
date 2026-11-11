# Innovation plan: what is missing to make SobraCero stand out

Written on 2026-11-10 after reading the code of both repositories and running the
production build. It separates what exists, what is missing and what to build next, and it is
careful about claims: surplus-food sales, discounts and donations already exist elsewhere (Too
Good To Go, Flashfood, Olio, Wasteless, EatCloud). The proposal is **not** "first of its kind";
it is a bounded, explainable and verifiable rescue flow, with tests as evidence.

## Progress

| # | Feature | Status |
| --- | --- | --- |
| 1 | Concurrency and idempotency tests | Done: `tests/test_concurrency.py`; found and fixed a double pickup and double stock return. |
| 2 | Live stock over WebSockets | Done: ADR 0008, two-browser check, reconnect with snapshot. |
| 3 | Rescue timeline | Done: anonymous, inside each rescue plan. |
| 4 | Verified impact panel | Done: pickups counted once, estimates labelled. |
| 5 | What-if simulator | Done: always labelled hypothetical. |
| 6 | Pickup QR | Not started. |
| 7 | ISR shop profile | Done: `MISS` / `HIT` / `STALE` observed in a production build. |
| 8 | Worker and scheduler on Railway | Not started (the custom domain was dropped from scope). |

## 1. What exists today (verified)

| Area | State |
| --- | --- |
| Marketplace | Shops, products, lots, filters, reservation with pickup code, cancellation, pickup confirmation by the owner. |
| Analytics | Sales import, weekday forecast, waste-risk, promotion text, expiry-date reading with human confirmation. |
| Rescue plan | Deterministic rule, reasons, human approval, audit events, stale-plan protection, optional AI wording (Groq) with no numbers. |
| Architecture | Separate gRPC analysis service with local fallback, layered backend, CI green in both repositories. |
| Frontend | i18n (en/es), light/dark/system theme, SSG (`how-it-works`), SSR (`lots/{id}`), streaming SSR (`market`), CSR dashboard. |

## 2. Gaps against the goal

1. **No live updates.** Stock changes only after a reload; WebSockets are a course requirement.
2. **Concurrency is not proven.** No test for the last unit or for repeated pickup.
3. **ISR is missing** (needs a public shop-profile endpoint).
4. **Donation is only a recorded quantity**: no receiver, acceptance or proof of delivery.
5. **The rescue loop is not closed in the UI.** The audit trail exists but is not shown, and a
   plan is not linked to the reservations and pickups that followed it.
6. **No impact view.** Nothing separates sold, donated, cancelled and pending units.
7. **Deployment is partial**: no worker/scheduler service, and the cross-site session cookie
   depends on third-party-cookie settings.

## 3. Proposed work, in order

Effort: S ≈ a day, M ≈ 2–3 days, L ≈ a week. They are estimates, not commitments.

| # | Feature | Why it matters | Effort | Evidence to keep |
| --- | --- | --- | --- | --- |
| 1 | **Concurrency and idempotency tests** (last unit, repeated pickup, donation vs reservation) | Proves the claims in the demo; protects every later feature. | S | Tests against the real database. |
| 2 | **Live stock and reservations over WebSockets** (Redis Pub/Sub as a hint, PostgreSQL as the authority, version per lot, snapshot on reconnect) | Visible in a two-browser demo; meets the WebSocket requirement. | M | Two-session recording, reconnect test, no private codes on public channels. |
| 3 | **Rescue timeline per lot**: recommendation → approval → reservations → pickups, from existing events | Turns the plan into a traceable decision; the strongest "explainable" story. | S–M | Screen plus API test. |
| 4 | **Verified impact panel**: units actually picked up, savings against the shown reference price, sales vs donations vs cancellations vs pending | Honest metrics; no CO₂ or "meals" equivalences without a published method. | M | Calculation tests and a seeded demo dataset. |
| 5 | **What-if simulator** (keep / apply discount rule / separate for donation) with a user-entered response parameter, always labelled "hypothetical scenario, not a validated prediction" | Makes the reasoning visible without claiming elasticity we do not have. | M | Unit tests of the scenario maths. |
| 6 | **Pickup QR** as a server-validated credential, idempotent confirmation | Closes publish → reserve → pick up; repeated scans change nothing. | S–M | Replay test. |
| 7 | **ISR shop profile** (`/shops/{id}`) with a public, minimal shop endpoint | Completes the rendering matrix; never used for stock. | S | Build output and `revalidate` evidence. |
| 8 | **Worker + scheduler on Railway** and a custom domain (`app.` / `api.`) | Promotions and lot expiry run unattended; first-party session cookie. | S | Deployment notes. |

Choose **one** optional extension after the list, not several:

- **Receiver flow** (receiver account, accepted categories, capacity, pickup window,
  deterministic matching, manual acceptance, delivery proof). Use a demo receiver and say so.
- **Basket by budget and time** with a small catalog and verifiable rules. "Not informed" never
  means "does not contain" for allergens.

Out of scope for now: real payments, delivery, blockchain, sensors, Kafka, Kubernetes, and any
claim that the system certifies food safety.

## 4. What to show the professor

1. The shop owner opens a lot, reads the rescue plan and its reasons, asks for the plain-language
   explanation and approves.
2. A customer reserves from another browser; the stock changes in the first browser without a
   reload (feature 2).
3. The owner confirms the pickup; the timeline and the impact counters change exactly once
   (features 3, 4, 6).
4. Stop the analysis service: the plan still works and is marked as a local fallback.
5. Show the contract (`.proto`), the rendering matrix with its evidence, and the concurrency
   tests.

## 5. How to word the claims

| Say | Do not say |
| --- | --- |
| "Explainable rescue plan with human approval and an audit trail." | "The AI eliminates waste." |
| "Tested against concurrent reservations." | "gRPC makes it faster." |
| "Demo data and a demo receiver." | "Integrated with real foundations." |
| "Estimated surplus from past sales." | "Probability that the food spoils." |

Anything not implemented stays listed as future work in the presentation.
