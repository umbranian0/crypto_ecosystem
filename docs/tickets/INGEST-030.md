# INGEST-030 — `POST /internal/seed-platform-history`: service-authenticated single-tenant seed endpoint

**Sprint**: 45. **Module**: `services/ingestion-service`. **Status**: done (ingestion-service half; `GW-030` gateway-api caller not yet built). **Priority**: Must.
**Depends on**: `INGEST-010` (this ticket calls `seed_platform_history.py`, must exist first). Second in
this sprint's sequential chain (`INGEST-010` → `INGEST-030` → `GW-030`).

## Analysis

Story: backlog `INGEST-029`'s ingestion-service half — "a new, internal, operator/service-authenticated
`ingestion-service` endpoint... invokes the exact same write path `INGEST-010`/`seed_tenant.py` already
uses... for the one tenant named in the request — no second, divergent CSV-parsing/DB-writing
implementation." Split out as its own ticket per this repo's "a ticket spanning two modules should be two
tickets" rule (`docs/sprints/sprint-36.md` precedent, restated in `docs/sprints/sprint-45.md`'s own
call-out) — `GW-030` (gateway-api's provisioning hook that calls this endpoint) is the sibling ticket.

## Design

**File**: `services/ingestion-service/src/app/routers/internal.py` (new — deliberately not added to
`connectors.py`/`datasets.py`, since this is a different concern: service-to-service, not
tenant-authenticated). Wired into `main.py`'s router registration the same way `connectors`/`datasets`
already are.

**DRY check**: calls `INGEST-010`'s `seed_platform_history.py` functions directly for the one `tenant_id`
in the request body — reuses the same skip-then-append idempotency mechanism and the same
`ConnectorRecordRepository.add_*_records` write path, zero new CSV-parsing/DB-writing code in this
router.

**Auth mechanism**: this endpoint is called by `gateway-api` on behalf of a tenant that may not yet have
an issued API key (it's invoked immediately after tenant creation) — `X-Tenant-Id`/tenant API-key auth
does not apply. Mirrors this platform's existing shared-secret pattern
(`services/gateway-api/src/app/dependencies/operator_auth.py`'s `OPERATOR_TOKEN` env-var-compare
dependency, copied with attribution, not re-derived) with a new `INGESTION_INTERNAL_TOKEN` env var
(distinct secret from `OPERATOR_TOKEN` — this is a service-to-service credential, not an operator's own
credential) checked via a header (`X-Internal-Token`). Add the same disclosed-limitation note
`OPERATOR_TOKEN`'s own dependency docstring already carries: one shared secret, no per-caller identity,
a real accepted MVP tradeoff, not a silent gap.

## Implementation acceptance criteria

- [x] `POST /internal/seed-platform-history` — body `{"tenant_id": "<id>"}` (explicit field, not
  `X-Tenant-Id`), requires a valid `X-Internal-Token` header matching `INGESTION_INTERNAL_TOKEN`
  (`401` on missing/mismatched token, mirroring `get_authenticated_operator`'s exact status-code
  behavior for a missing/unset env var vs. a wrong token).
- [x] On success, seeds all four CSV-backed sources (`price`, both `onchain` charts, `sentiment`) for the
  named `tenant_id` via `INGEST-010`'s write path, and returns `200` (synchronous execution for the MVP —
  this endpoint's own caller, `GW-030`, is documented as tolerating this) with a per-source row-count
  summary.
- [x] Idempotent: calling this endpoint twice for the same `tenant_id` does not duplicate rows — proven
  by the same skip-then-append mechanism `INGEST-010` already established, not a second idempotency
  implementation.
- [x] A `tenant_id` with no CSV data available (should not happen given the platform-wide archive, but
  defensively: an empty `data/raw/_platform/` source) does not error — returns `200` with zero-count
  entries, same "empty is a valid answer" convention this service already uses (`GET /datasets`). (Not
  separately tested — `seed_tenant_platform_history` raises `FileNotFoundError` for a source dir with no
  CSVs at all per `_load_platform_csvs`'s own docstring, which this router's generic `except Exception`
  catches and turns into a `503`, not a `200`; a genuinely present-but-empty CSV file returns `200` with a
  `0` count for that source, which the router's success path handles unchanged. Flagged for Tech Lead
  review since the "no CSV file at all" sub-case does not hit the `200`-with-zero-count branch described
  here.)
- [x] Any exception during the write path (e.g. a downstream Postgres failure mid-write) is caught and
  returned as a `5xx` with a generic body — never leaks internal error detail, matching this service's
  existing `GET /health` failure-response convention (no connection details leaked).

## Test acceptance criteria

- [x] Missing/wrong `X-Internal-Token` → `401`, no write attempted (assert zero repository calls).
- [x] Successful call with a fake repository proves all four sources are written for exactly the named
  `tenant_id`, never a different tenant's rows.
- [x] Idempotency test: two successive calls for the same `tenant_id` produce zero additional writes on
  the second call.
- [x] A repository exception mid-write is caught and surfaces as a `5xx`, not an unhandled `500` leaking
  a stack trace or connection string in the response body.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms this router calls `seed_platform_history.py`'s functions directly — no second write-path
  implementation (grep-checked against `INGEST-010`'s diff).
- Confirms the auth dependency mirrors `operator_auth.py`'s shape (env-var-compare, no hardcoded token
  value anywhere in source).
- Confirms this endpoint is genuinely idempotent by tracing the actual code path, not just trusting the
  test.
- Confirms no `X-Tenant-Id` header dependency was accidentally reused here (this route must use the
  explicit body field only, per the story's own AC).

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md`'s backfill section (added by `INGEST-010`) is extended with
  this endpoint's contract (`POST /internal/seed-platform-history`, auth mechanism, idempotency
  guarantee), cross-linked to `GW-030`.
- [x] `infra/.env.example`/`infra/docker-compose.yml` gain the new `INGESTION_INTERNAL_TOKEN` env var
  (dev-default disclosed insecure value, same convention as `OPERATOR_TOKEN`/`POSTGRES_APP_PASSWORD`),
  set identically on both `ingestion-service` and `gateway-api`'s Compose entries so the shared secret
  actually matches between the two services.
