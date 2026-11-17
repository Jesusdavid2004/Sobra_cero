# ADR 0004: Train and register a weekday sales forecast

## Status

Accepted

## Context

The waste-risk workflow needs a measurable trained predictor, a time-ordered
evaluation against a baseline, persisted model provenance, and safe behavior
before any model has passed evaluation. Imported and generated sales histories
are small, daily, and may contain date gaps.

## Decision

- Train a weekday-seasonal ratio model from continuous seven-day history
  windows. Normalize promotional sales consistently with the existing
  predictor.
- Split samples chronologically: the earliest 80% of target dates are training
  data and the latest 20% are a holdout. Compare mean absolute error against a
  trailing-seven-day-average baseline.
- Activate a candidate only when its holdout MAE is strictly lower than the
  baseline. Keep rejected candidates and their metrics in the model registry.
- Store the compact JSON artifact, evaluation metrics, and active-model marker
  in PostgreSQL/SQLite through Alembic-managed tables.
- Use the existing weighted moving average when no trained model is active.
  Return and persist the model version with each waste-risk prediction so this
  fallback is visible rather than implicit.
- Restrict model training to platform admins, rate-limit it, and bound the
  training dataset to the latest 365 days.

## Consequences

The training pipeline has no separate model-serving process or binary artifact
dependency, and the model remains available across application restarts when
the database is durable. The model learns shared weekday seasonality across
products, so the current training metrics do not claim product-specific
accuracy. The chronological holdout prevents future sales from influencing
the trained weekday factors.
