# SETUP-011 — `gateway-api`: tenant list/create/revoke admin endpoints

**Sprint**: 32. **Module**: `services/gateway-api`. **Status**: done. **Priority**: Must.
**Depends on**: `SETUP-010` (done, `get_authenticated_operator`). **Blocks**: `SETUP-012`.
**Can run in parallel with**: `SETUP-015` (disjoint module). Sequence before `SETUP-021` (both touch
`src/app/main.py`'s router registrations — land this one first to avoid a same-file collision).

## Analysis

Backlog `SETUP-011` (`docs/product/backlog-first-run-setup-and-ops.md`): `GET /tenants`,
`POST /tenants`, and a revoke endpoint, all operator-authenticated, replacing the
`docker compose exec ... provision_tenant.py`/`revoke_api_key.py` flow with a network-reachable
surface `dashboard-web`'s Settings area (`SETUP-012`) can call. Constraint from
`implementation-plan.md` section 9 (DRY): `POST /tenants` must call the same `provision()` function
`SETUP-002`/`provision_tenant.py` already share — one function, three callers, never a third
implementation.

**Read directly before writing code** (grepped, not assumed): `app/repositories/interfaces.py`,
`app/repositories/sqlite_repository.py`, `app/repositories/postgres_repository.py` have no
`list_tenants()`/`list_api_keys(tenant_id)` method today — only single-record lookups
(`get_tenant`, `get_by_hash`) and single-row mutations (`create_tenant`, `create_key`, `revoke_key`)
exist. `GET /tenants` needs a real list, so this ticket adds those two read methods to the interface
and both storage backends — this is new repository surface, not a gap in a prior ticket.

**Revoke granularity mismatch, resolved explicitly (do not silently paper over)**: the backlog's own
wording says this endpoint "wraps `revoke_api_key.py`'s `revoke()`", but `revoke()`
(`scripts/revoke_api_key.py`) takes a **raw API key** as input — the only credential a CLI operator
has on hand. A `dashboard-web`/HTTP caller has no raw key after issuance (it is shown once and never
persisted, per `GW-005`'s one-time-reveal contract) — it only has the key's `id` (metadata, from
`GET /tenants`). The correct shared call for `POST /tenants/{id}/api-keys/{key_id}/revoke` is
therefore `ApiKeyRepository.revoke_key(tenant_id, key_id)` directly — the same repository method
`revoke_api_key.py`'s own `revoke()` calls internally after it resolves a raw key to a `key_id`. This
is still "one shared function, not a duplicate revocation code path" (the DRY requirement the backlog
names) — the shared function is `revoke_key` at the repository layer, one level lower than
`revoke_api_key.py`'s own CLI-specific `revoke()` wrapper, which is the correct level to share at
here since the two callers start from different inputs (raw key vs. key id). Document this decision
in the README rather than leaving it implicit.

## Design

**Pattern**: Repository (existing, extended with two new read methods) + DI (`Depends()`, reusing
`TenantRepositoryDep`/`ApiKeyRepositoryDep`) + the already-existing `get_authenticated_operator`
dependency (`SETUP-010`) as the auth gate on every route in this ticket. No new pattern introduced.

**Files touched** (scoped to `services/gateway-api` only):
- `src/app/repositories/interfaces.py` — add `TenantRepository.list_tenants() -> list[TenantRecord]`
  (no `tenant_id` param — a cross-tenant listing is inherently an operator-only, tenant-agnostic
  read, document as a fifth exception to the `tenant_id`-first convention already documented in this
  file's own module docstring) and `ApiKeyRepository.list_api_keys(tenant_id: str) -> list[ApiKeyRecord]`
  (tenant_id-first, ordinary case).
- `src/app/repositories/sqlite_repository.py` — implement both new methods.
- `src/app/repositories/postgres_repository.py` — implement both new methods. `list_tenants()` is a
  cross-tenant read like `tenant_exists()` (`SETUP-001`) — it must not call `_set_tenant_scope`, and
  needs the same RLS `USING`-clause tenant-agnostic fallback `0005_add_tenants_rls_read_fallback.py`
  already added to `tenants`. Confirm this migration's existing fallback already covers a `SELECT *`
  (not just the single-row read `tenant_exists()` needed) before assuming no new migration is needed —
  state the finding either way in the ticket's Outcome, don't just assume.
- `src/app/routers/tenants.py` (new module — same "one disjoint module per distinct concern"
  precedent `setup.py`/`system.py`/`operator.py` already established) — declares:
  - `GET /tenants` (operator-auth): returns `TenantListResponse` — one entry per tenant, each
    `{id, name, created_at, api_keys: [{id, created_at, revoked_at}]}` — **never** `key_hash` or any
    recoverable key value.
  - `POST /tenants` (operator-auth): body `{tenant_name: str}`, calls `app.provisioning.provision()`
    (imported directly, not reimplemented — the exact function `SETUP-002`/`provision_tenant.py`
    already use), returns `{tenant_id, tenant_name, api_key}`, `201`, raw key shown once (same
    contract shape as `SETUP-002`'s `SetupInitializeResponse`, but this route has no `409`-on-already-
    initialized guard — this is a genuine ongoing multi-tenant creation surface, gated by operator auth
    instead of the fresh-install check).
  - `POST /tenants/{tenant_id}/api-keys/{key_id}/revoke` (operator-auth): calls
    `ApiKeyRepository.revoke_key(tenant_id, key_id)` directly (see Analysis section's resolved
    granularity decision above) after confirming the key exists and belongs to `tenant_id` (404 if
    not — resolve via `list_api_keys(tenant_id)` and match `key_id`, no new lookup-by-id repository
    method needed for this). Already-revoked is a no-op (mirrors `revoke_api_key.py`'s own
    idempotency guard: check `revoked_at` before calling `revoke_key`, never re-stamp). Returns
    `{tenant_id, key_id, revoked_at}`, `200`.
- `src/app/main.py` — `app.include_router(tenants.router)`, no `tags=` (same `ARCH-007` reasoning as
  `setup.router`/`system.router` — this router doesn't proxy to a single downstream service).
- `services/gateway-api/README.md` — new "Tenant admin endpoints (SETUP-011)" section.

**DRY check note** (grepped `src/app/routers/`, `src/app/provisioning.py`,
`scripts/revoke_api_key.py` before writing this ticket): `provision()` already exists and is reused
directly for `POST /tenants`, no second tenant-creation code path. `revoke_key` (repository layer)
already exists and is reused directly for the revoke endpoint, per the resolved granularity decision
above — no new revocation logic invented, only a new caller of an existing method.

## Implementation acceptance criteria

- [x] `GET /tenants` (operator-auth via `get_authenticated_operator`) returns every tenant's
  `id`/`name`/`created_at` and its keys' `id`/`created_at`/`revoked_at` — never `key_hash` or a raw
  key.
- [x] `POST /tenants` (operator-auth) creates a tenant + first key via `provision()`, returns the raw
  key exactly once, `201`.
- [x] `POST /tenants/{tenant_id}/api-keys/{key_id}/revoke` (operator-auth) revokes via
  `ApiKeyRepository.revoke_key`; a second call against an already-revoked key is a no-op (unchanged
  `revoked_at`), not an error and not a re-stamp.
- [x] A `key_id` that does not belong to `tenant_id` (or does not exist) returns `404`, not a silent
  no-op and not a cross-tenant revoke.
- [x] `scripts/provision_tenant.py`/`scripts/revoke_api_key.py` are unchanged and still work — kept as
  "two front doors to the same underlying operation," documented as such in the README.

## Test acceptance criteria

- [x] `tests/test_tenants_router.py` (new): list (empty, one tenant, multiple tenants with mixed
  active/revoked keys), create (asserts raw key present exactly once, tenant persisted via the
  fake/sqlite repository), revoke (fresh key → revoked; already-revoked key → no-op, unchanged
  `revoked_at`; unknown `key_id` → `404`; `key_id` belonging to a different tenant → `404`).
- [x] A test proves a real tenant's own API key, presented to any `/tenants` route, is rejected
  (`403`, per `SETUP-010`'s existing behavior) — the cross-boundary case this whole epic exists to
  guard.
- [x] `tests/test_sqlite_repository.py`/`tests/test_postgres_repository.py` gain coverage for the two
  new `list_tenants`/`list_api_keys` methods.
- [x] `uv run pytest -q` (or `.venv\Scripts\python.exe -m pytest -q`) run in full from
  `services/gateway-api`, zero regressions. 197 passed.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads `tenants.py` directly: confirms `key_hash`/raw key never appears in any response model.
- Confirms `POST /tenants` calls `app.provisioning.provision()` — no second tenant-creation code path.
- Confirms the revoke route calls the repository's `revoke_key` and correctly scopes the 404 to
  "key exists but wrong tenant" vs. "key doesn't exist at all" without leaking which case occurred in
  the response body (a generic 404, not a distinguishing detail).
- Confirms `list_tenants()`'s Postgres RLS behavior is correct (either the existing fallback already
  covers it, or a new migration was added and is Postgres-only-guarded like `0005`) — read the
  migration/query directly, don't trust a passing sqlite-only test suite as proof of Postgres
  correctness.
- Re-runs the full `gateway-api` suite, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/gateway-api/README.md` gets a new "Tenant admin endpoints (SETUP-011)" section:
  documents all three routes, the never-expose-`key_hash` guarantee, the "two front doors" framing
  for the CLI scripts, and the resolved revoke-granularity decision (repository-level `revoke_key`
  reuse, not `revoke_api_key.py`'s CLI-specific `revoke()` wrapper) so a future reader isn't confused
  by the backlog's own looser wording.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-011` acceptance boxes checked, status
  marked done, citing this ticket.

## Outcome

Implemented as designed: `src/app/repositories/interfaces.py` gained `TenantRepository.list_tenants()`
(fifth documented `tenant_id`-not-first exception) and `ApiKeyRepository.list_api_keys(tenant_id)`
(ordinary `tenant_id`-first case); both implemented on `sqlite_repository.py` and
`postgres_repository.py`. `src/app/routers/tenants.py` (new) declares the three operator-gated routes;
`main.py` registers it with no `tags=` (ARCH-007, matches `setup.router`/`system.router`).

**Postgres RLS finding (Review AC, stated explicitly, not assumed)**: `list_tenants()` deliberately
does not call `_set_tenant_scope` (a fourth tenant-agnostic read, alongside `get_by_hash`/
`get_user_by_email`/`tenant_exists`). Migration `0005_add_tenants_rls_read_fallback.py`'s existing
`USING (id = current_setting('app.tenant_id', true) OR NULLIF(current_setting('app.tenant_id', true),
'') IS NULL)` clause on `tenants` already covers a multi-row `SELECT *`, not just `tenant_exists()`'s
single-row `LIMIT 1` read — a `USING` clause is a per-row filter applied to every `SELECT` against the
table regardless of how many rows the query would otherwise return. No new migration was needed; this
is confirmed by `test_list_tenants_resolves_across_tenants_despite_rls_via_restricted_role` in
`tests/test_postgres_repository.py`, run against a real non-superuser/non-`BYPASSRLS` Postgres role
(`restricted_role_engine`), not just a passing sqlite-only suite.

`list_api_keys(tenant_id)` is an ordinary tenant-scoped read (calls `_set_tenant_scope` like every
other tenant-known method on `PostgresApiKeyRepository`) — no RLS policy change needed there either.

Full suite: `.venv\Scripts\python.exe -m pytest -q` from `services/gateway-api` → 197 passed, 0
regressions (Postgres integration tests ran against a real reachable local Postgres, not skipped).
