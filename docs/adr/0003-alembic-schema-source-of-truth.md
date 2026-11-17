# ADR 0003: Alembic owns the database schema

- Status: Accepted

## Context

The API previously called SQLAlchemy `metadata.create_all()` before applying
Alembic migrations. The initial Alembic revision was empty, so a fresh database
depended on ORM metadata to create its schema while later migrations altered it.
That left the migration history unable to reproduce a fresh installation.

## Decision

- Make `0001_initial` create the original account, shop, product, lot,
  reservation, donation, and promotion schema.
- Keep the initial revision safe to apply to legacy installations whose tables
  were already created by `metadata.create_all()`; it creates only missing
  tables and ensures the initial indexes exist.
- Apply later revisions for sales history, waste predictions, account/catalog
  attributes, and pickup codes.
- Remove `metadata.create_all()` from API startup. Alembic upgrades are the
  production schema creation and evolution path.
- Refuse to downgrade the baseline revision because it cannot distinguish
  tables it created from pre-existing tables adopted by the revision.

## Consequences

- Fresh and legacy databases converge on the same Alembic head without
  recreating existing tables.
- New schema changes must be represented by versioned migrations instead of
  relying on application startup metadata.
- The initial migration is intentionally not reversible; this avoids deleting
  legacy application data during a downgrade.
