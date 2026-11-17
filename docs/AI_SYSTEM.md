# AI system

The rule that shapes everything: **code decides, the model words.** Numbers, ordering, eligibility,
prices and approvals come from deterministic code that has tests. The language model reads or
rephrases text, and the product keeps working when it is unavailable.

See also `ai-usage.md` (the five original uses and guardrails). This page adds the diagnosis and
describes the architecture.

## Where the model is used

| Use | Endpoint | Model sees | Model returns | Never decides |
| --- | --- | --- | --- | --- |
| Promotion text | `POST /lots/{id}/generate-promos` | Lot facts | Up to 25 words | Discount, price |
| Expiry date from a photo | `POST /lots/{id}/expiry-scans` | Image | Date and confidence | Nothing is applied until the owner confirms |
| Rescue plan explanation | `POST /rescue-plans/{id}/explanation` | Reason codes | Two sentences, no digits | Action, numbers, approval |
| Reading a pickup request | `POST /discovery/parse` | One typed sentence | Budget, times, quantity, category | Which lots fit, their order |
| Donation message draft | `POST /lots/{id}/donation-offers/draft` | Lot title, category, receiver name | A courteous message, no digits | Who is compatible, quantities |
| **Daily shop diagnosis** | `GET /shops/{id}/diagnosis` | Alert and limitation codes | Up to three sentences, no digits | Every number and alert |

## The daily diagnosis (the food-intelligence centre)

`domain/diagnosis.py` builds the diagnosis from records the platform already holds and returns:

- **facts**: lots on sale, units available, units expiring within a day or closing within six hours,
  units picked up, donated and delivered, cancelled and wasted in the last seven days, units awaiting
  pickup;
- **alerts**: nothing published, expiring soon, stock closing soon, waste recorded, pending pickups;
- **limitations**: what the summary cannot know (no lots on sale, no pickup confirmed so the sell-through
  is unknown, no waste ever recorded, no demand forecast included);
- **data used**: lots, reservations, delivered donations and waste the shop recorded.

The model receives only the alert and limitation descriptions, never a number, and writes a short
summary. If it is unavailable or the daily quota is used, the response still carries every number,
alert and limitation, with `narrative_status` saying `unavailable` or `quota_exceeded`.

What it does not do: it does not infer waste from sales or prices, does not read external catalog
prices as stock, does not forecast (rescue plans do, per lot) and does not claim anything about food
safety.

## Waste

Waste is **declared by the shop** (`POST /lots/{id}/waste`) with a reason (expired, damaged, unsold,
other) and an optional note. Units leave the lot atomically and only once; the quantity cannot exceed
what the lot holds. Units of an expired lot can still be recorded. Nothing estimates waste.

## Architecture

- `application/ports.AIProvider` is the only interface use cases know. `llm.StructuredAIProvider`
  implements it with schema validation, one retry that feeds the error back, a per-user daily quota,
  a cache keyed by input, locale and prompt version, token caps, timeouts and logs of tokens and
  latency (never raw text).
- Adapters: Anthropic, OpenAI-compatible (Groq and others) and a deterministic fake used by tests and
  offline demos (`LLM_PROVIDER=mock`).
- Prompts live in versioned files (`*_prompt.py`) and treat anything a person typed as data inside
  delimiters; forged delimiters are stripped.
- Output schemas that must stay qualitative reject any digit, so the model cannot introduce a number.

## Configuration

`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` and the `AI_*` limits; see
`ENVIRONMENT_VARIABLES.md`. Example for Groq:
`LLM_PROVIDER=groq`, `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=openai/gpt-oss-20b`.
Never commit a key and never paste it in a chat.

## What was and was not verified

- Every use is covered by automated tests with the deterministic provider, including the outage and
  quota fallbacks of the diagnosis.
- The browser walkthroughs also used the deterministic provider.
- **A live call to Groq with the newer prompts has not been run.** Until it is, wording quality and
  behaviour on real text are unverified.

## Not implemented

Photo recognition of food, OCR of invoices, barcode reading, POS integrations and a demand model
beyond the weekday forecast are not implemented. They need data or hardware this project does not
have, and they are listed as future work, not promised.
