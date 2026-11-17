# Security notes and operating controls

This document describes implemented controls and remaining deployment risks.
It is not a penetration-test report or a guarantee of production security.

## Identity, sessions, and authorization

- Passwords are hashed with bcrypt. Access JWTs are short-lived (15 minutes by
  default); browser code holds them in memory.
- Refresh tokens are HttpOnly cookies backed by Redis, rotated atomically, and
  revoked on logout. Production settings reject the development JWT secret,
  require a 32-character secret, require Secure refresh cookies, and reject the
  mock AI provider.
- Business and customer capabilities are checked by the API. Shop-scoped
  mutation and pickup paths check ownership; cross-role pickup tests verify
  that customers receive `403` and a non-owning business receives `404`.
- CORS origins are configured with `CORS_ORIGINS`; production must list only
  the trusted frontend origin(s).

## Uploaded images and AI data

- Lot-image upload validates the declared type against decoded JPEG, PNG, or
  WebP content; rejects animated/unsupported images; enforces a 5 MiB byte
  limit and pixel limit; applies EXIF orientation; and re-encodes to strip
  inherited metadata.
- Objects are written to private S3-compatible storage using random keys.
  Read access is returned as a short-lived signed URL. Images are sanitized
  again before a vision-provider request.
- AI requests are schema-validated, bounded by timeout/retry/token settings,
  cached, and subject to a per-user daily quota. User-provided image/text data
  is untrusted input. Provider retention and residency policies remain an
  operator responsibility.
- Pickup confirmation is rate-limited to five requests per minute per client
  IP and checks business role, shop ownership, reservation state, and code.

## Operational limitations and production requirements

- Rate limiting is an in-process sliding window keyed by client IP. It is not
  shared between replicas, is not a substitute for a distributed gateway
  limiter, and may use the proxy address unless trusted-proxy handling is
  configured. Place production throttling at a trusted edge and validate
  forwarded client addresses.
- The repository's Docker Compose stack is for local development: it exposes
  services on host ports and uses development credentials. It does not provide
  TLS termination, managed secret storage, network segmentation, or production
  backup/restore automation.
- The API does not yet apply a complete secure-header policy or a single
  structured error envelope across every route. Do not expose the local
  Compose API directly to the public internet.
- `/health` is liveness only. `/ready` performs a database query and Redis
  ping; it does not probe object storage or the AI provider.
- Account deletion and verified deletion of associated files are not exposed
  as a user-facing workflow.
- Database backups, Redis session recovery, private-object retention, key
  rotation, incident response, and audit-log retention must be designed and
  tested for the selected production platform.

## Release checklist

Before a public release, an operator should:

1. Deploy behind HTTPS with a trusted proxy/WAF and exact CORS origins.
2. Use managed PostgreSQL, Redis, and private S3-compatible storage; replace
   all Compose credentials and configure retention/backup policies.
3. Set a unique secret, enable Secure cookies, select a supported remote AI
   provider, and verify secrets are not present in logs or artifacts.
4. Validate the deployment's network, authorization, rate-limit, storage
   signature, dependency vulnerability, backup/restore, and account-deletion
   controls.
5. Run the full acceptance suite and a privacy-approved live AI evaluation.

No public HTTPS deployment or production penetration test has been performed
for this repository.
