# Model and AI evaluation

## Waste-risk forecast

The trained weekday-seasonal model is evaluated against the existing
trailing-average baseline using chronological holdout data. The trainer uses
continuous seven-day history windows, splits target dates chronologically
(earliest 80% for training and latest 20% for evaluation), and compares mean
absolute error (MAE). It considers at most 365 recent days. A candidate becomes
active only when its holdout MAE is strictly lower than the baseline MAE;
otherwise the baseline remains active.

Training samples, evaluation samples, both MAE values, artifact JSON, model
version, and active status are stored in `sales_forecast_models`. Risk
predictions retain the model version used. When no candidate has passed the
comparison, the application explicitly uses
`baseline-weighted-moving-average`.

### Running a local evaluation

1. Start the application and load/import sales history for one or more products.
2. Authenticate as a platform admin.
3. Send `POST /api/v1/admin/models/sales-forecast/train`.
4. Inspect the returned evaluation and the persisted model record; verify that
   the active marker changes only when candidate MAE is lower.
5. Request `GET /api/v1/shops/{shop_id}/waste-risk` and record the reported
   `prediction_model`.

Synthetic demo history is useful for exercising the pipeline, not for judging
real-world forecasting quality. The repository does not include a
representative production data set or a published measured model-quality
benchmark. Any production acceptance threshold must be chosen with the data
owner and evaluated on representative, time-separated data.

## Structured AI features

The AI adapter asks for schema-constrained output and validates it with
Pydantic. The shared orchestration applies bounded retries, a request timeout,
per-user daily quota, and a cache keyed by input, locale, schema, prompt version,
and model tier. The fake provider is deterministic and is used for automated
tests and offline demonstrations.

Automated tests cover response validation, invalid outputs, cache/quota
behavior, provider errors, and expiry-date confirmation. They do not establish
accuracy or latency for a live Anthropic/OpenAI account. No production
benchmark, human-label evaluation, or measured hallucination rate is included
in this repository.

Expiry-date OCR is a suggestion workflow: unreadable/low-confidence outputs
remain unreadable, and readable dates still require an explicit human
confirmation. Do not use the feature as the sole food-safety control. Review
the provider's image-processing and retention terms before sending real
customer or business images.

## Evidence and limitations

- Backend unit/integration tests use deterministic fixtures and a fake AI
  provider; they are regression evidence, not production model validation.
- The registered forecast model records MAE metrics, but the project does not
  ship a precomputed evaluation report from a real historical data set.
- No live-provider E2E run is required by local CI. Before enabling a remote
  provider in production, run a privacy-approved acceptance set and record
  provider/model version, locale, prompt version, label source, accuracy,
  failure cases, latency, and cost.
