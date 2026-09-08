# SETUP-002 — `gateway-api`: bootstrap-only tenant + admin-key creation endpoint

**Sprint**: 29. **Module**: `services/gateway-api`. **Status**: done. **Priority**: Must.
**Depends on**: `SETUP-001` (same new `src/app/routers/setup.py` file, same
`TenantRepository.tenant_exists()` method). **Blocks**: `SETUP-003` (calls this route).
**Can run in parallel with**: nothing this sprint (sequential after `SETUP-001`, same file).

## Analysis

Per `backlog-first-run-setup-and-ops.md`'s `SETUP-002` story: the wizard's actual creation step needs a
network-reachable equivalent of `docker compose exec ... provision_tenant.py`, but only while the
system is uninitialized — otherwise this would be an open public tenant-signup endpoint, which this
platform's positioning explicitly does not want. Sprint DoD is explicit: this endpoint must call the
**exact same** `provision()` function `provision_tenant.py` already uses — no second tenant-creation
code path (implementation-plan.md section 9, DRY).

## Design

**Pattern**: none newly introduced. Reuses `scripts/provision_tenant.py`'s existing `provision(name,
tenant_repo, api_key_repo) -> tuple[TenantRecord, str]` function directly, imported into the router —
the same "one function, multiple callers" shape `SETUP-011` (next sprint, `/tenants` POST) will later
extend to a third caller.

**Files touched** (scoped to `services/gateway-api` only):
- `src/app/routers/setup.py` (same file `SETUP-001` created) — adds `POST /setup/initialize`, no auth
  dependency (gated by the `409` check instead, per the story). Body: `{"tenant_name": str}` (a
  `SetupInitializeRequest` Pydantic model, minimal — no reuse of `provision_tenant.py`'s CLI
  `argparse` surface, which is a different entry point shape). Imports `provision` from
  `scripts.provision_tenant` — **confirm this import path resolves inside the FastAPI app process**
  (this script has historically been invoked as a standalone CLI, never imported by `app.main`; if
  `scripts/` isn't on the app's import path in the installed package layout, extract `provision()`'s
  body into a location both the CLI script and this router can import from — e.g. keep the CLI script
  as the thin wrapper, move the function itself to `app/provisioning.py` — rather than duplicating its
  ~15 lines. This is a real design decision to make during implementation, not assumed here; whichever
  shape is chosen, `provision_tenant.py`'s own CLI behavior and this ticket's own README-documented
  "no second code path" claim must both remain true).
- `src/app/main.py` — no additional router registration (same `setup.router` `SETUP-001` already
  registered covers this new route too, since both live in the same router module).

**DRY check note**: grepped `src/app/routers/` and `scripts/` before writing this ticket — `provision()`
is the only tenant-creation function in this codebase (confirmed, `SETUP-011`'s own backlog text
independently confirms the same "one function, three eventual callers" framing). This ticket is the
second caller (CLI script is the first); it must not become a second implementation.

## Implementation acceptance criteria

- [x] `POST /setup/initialize` accepts `{"tenant_name": str}` and internally calls the exact same
  `provision()` function `provision_tenant.py` uses (verified by import, not by re-implementing its
  body).
- [x] If `TenantRepository.tenant_exists()` (`SETUP-001`) is already `true`, returns `409 Conflict` and
  creates nothing — checked **before** calling `provision()`, not via a caught unique-constraint error.
- [x] The raw API key is returned in the response body exactly once (`{"tenant_id": str, "tenant_name":
  str, "api_key": str}`), matching `provision_tenant.py`'s one-time-reveal contract; never logged
  (`provision()`'s existing `extra=` discipline — `tenant.id` only, never `raw_key` — already covers
  this without change).

## Test acceptance criteria

- [x] First call with a fresh (zero-tenant) system succeeds (`201`), creates exactly one `tenants` row
  and one `api_keys` row, and returns the raw key.
- [x] A second call (any `tenant_name`, including a different one) returns `409`, and the tenant table
  still has exactly one row afterward (not two).
- [x] A test asserts the raw key never appears in any captured log line across both the success and the
  `409` path (`caplog`, mirroring `GW-014`'s/`test_operator_auth.py`'s non-tautological log-capture
  discipline).
- [x] `uv run pytest -q` run in full, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms, by reading the diff, that `provision()` is imported and called, not reimplemented —
  the single biggest DRY risk this ticket carries.
- Confirms the `409` check runs before any write, not via catching a database-level uniqueness
  violation as a side effect.
- Confirms the raw key is present in the response exactly once and absent from every log call on
  both the success and conflict paths.
- Re-runs `gateway-api`'s full suite, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/gateway-api/README.md` documents `POST /setup/initialize` as a narrow, deliberate
  exception to "no public tenant-creation surface exists" elsewhere in the same README, stating the
  `409`-after-first-tenant guard as the entire boundary between "first-run convenience" and "an open
  public signup form."
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-002` entry's acceptance-criteria
  boxes are checked and its status marked done.
