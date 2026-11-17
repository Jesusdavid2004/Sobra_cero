# Where AI is used, and what it is not allowed to decide

SobraCero calls a language model in five places. In every one the model only reads or words
text; numbers, ordering, prices, eligibility and approvals come from code.

## The five uses

| Use | Endpoint | Model input | Model output | What code decides |
| --- | --- | --- | --- | --- |
| Promotion text | `POST /api/v1/lots/{id}/generate-promos` | Lot facts | Short promo copy (at most 25 words) | Discount, price, stock |
| Expiry date from a label photo | `POST /api/v1/lots/{id}/expiry-scans` | Image | Printed date, parsed date, confidence | Nothing is applied until the owner confirms it |
| Plain-words rescue explanation | `POST /api/v1/rescue-plans/{id}/explanation` | The plan's reason codes | Two sentences, no digits | The action, expected sales, surplus, approval |
| **Reading a pickup request** | `POST /api/v1/discovery/parse` | One sentence typed by the customer | Budget, pickup times, quantity, category (each null if absent) | Which lots are feasible, their order, the reasons. The customer reviews the values before searching |
| **Drafting a donation message** | `POST /api/v1/lots/{id}/donation-offers/draft` | Lot title and category, receiver name | A courteous message, no digits, no safety claims | Which receivers are compatible, quantities, acceptance. The owner edits the message before sending |

The two in bold were added with the discovery and donation features. Prompts live in versioned
files (`rescue_explanation_prompt.py`, `discovery_intent_prompt.py`, `donation_offer_prompt.py`,
and the promotion/expiry templates) and their version is part of the cache key.

## Guardrails applied to every call

All calls go through `StructuredAIProvider` (`app/llm.py`), which depends on the `AIProvider`
port, so use cases never import a vendor.

- Structured output validated with Pydantic. On a validation failure it retries once with the
  error, then raises `AIResponseInvalidError` (mapped to a generic response, never a stack trace).
- Provider errors retry once with backoff, then raise `AIProviderUnavailableError`.
- Per-user daily quota (`AI_DAILY_QUOTA`), response cache keyed by input, locale and prompt
  version (`AI_CACHE_TTL_SECONDS`), token cap (`AI_MAX_TOKENS`) and timeout
  (`AI_TIMEOUT_SECONDS`).
- Tokens and latency are logged; raw user text is not.
- Anything a person typed or a shop wrote (the pickup request, lot title, receiver name) is
  wrapped in delimiters and the prompt says to treat it as data. Forged closing tags are
  stripped (covered by a test).
- Output schemas for the explanation and the donation message reject any digit, so the model
  cannot introduce a number or a quantity.
- A deterministic `FakeAIProviderAdapter` (the default `LLM_PROVIDER=mock`) serves tests and
  offline demos, so the whole app works without a key.

## Provider configuration

`LLM_PROVIDER` is `mock`, `openai`, `anthropic` or an OpenAI-compatible endpoint such as Groq:

```
LLM_PROVIDER=groq
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-20b
LLM_API_KEY=<set in .env or the hosting variables, never committed>
```

Model names, token caps, timeouts and quotas are environment variables (see `.env.example`).

## What was verified, and what was not

- Automated tests use the deterministic provider; they check the contract, the validation, the
  prompt delimiters and that the model's output does not drive any decision.
- The browser walkthrough of the pickup-request reader and the donation-message draft also ran
  against the deterministic provider.
- A live call to Groq with these two new prompts has **not** been run yet. Until it is, the
  wording quality and the model's behaviour on real text are unverified.

## Limits worth stating

- The pickup-request reader copies what the text says. It can misread a sentence, which is why
  the form is filled in for the customer to review, not searched automatically.
- The donation message is a draft for the shop to edit; it makes no statement about food safety.
- Nothing here certifies that food is safe or that a receiver is authorized to receive it.
