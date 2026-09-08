# SETUP-001 — `gateway-api`: fresh-install detection endpoint

**Sprint**: 29. **Module**: `services/gateway-api`. **Status**: done. **Priority**: Must.
**Depends on**: none. **Blocks**: `SETUP-002` (same new router file), `SETUP-003` (calls this route).
**Can run in parallel with**: `SETUP-010` (disjoint areas of `gateway-api` — a new router vs. a new
auth dependency; see the sprint's own File-overlap note on `main.py`'s router-registration line).

## Analysis

Per `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-001` story: `dashboard-web`'s setup
flow needs an unauthenticated way to ask "does any tenant exist yet" — by definition no credential can
exist to gate that question on a genuinely fresh install (the same chicken-and-egg reasoning
`provision_tenant.py`'s own docstring already applies to itself). This is the one deliberate,
narrow unauthenticated endpoint this service will carry.

## Design

**Pattern**: none of implementation-plan.md section 7's patterns are newly introduced — this is a
plain read-only query behind a new router, following the same DI/repository shape every other route in
this service already uses.

**Files touched** (scoped to `services/gateway-api` only):
- `src/app/routers/setup.py` (new) — `GET /setup/status`, no `Depends(get_authenticated_tenant)`/
  `get_authenticated_operator` on this route at all (the entire point). Uses the existing
  `TenantRepositoryDep` (`app.dependencies.repositories`) to check whether any tenant exists.
- `src/app/main.py` — registers `app.include_router(setup.router)` — **no** `tags=["<service-name>"]`
  per `ARCH-007`'s convention, since this router doesn't proxy to a downstream service (same reasoning
  `system.router`'s `GET /system/health` registration already uses, unmodified).

**DRY check note** (grepped `src/app/repositories/interfaces.py` and `dependencies/repositories.py`
before writing this ticket): `TenantRepository` has no existing "does at least one tenant exist" method
— `get_tenant(tenant_id)` requires an id, `create_tenant` doesn't answer the question. Add
`TenantRepository.tenant_exists() -> bool` as a new Protocol method, implemented on **both** the SQLite
(`SQLiteTenantRepository`) and Postgres (`PostgresTenantRepository`) backends (this service runs
either, selected by `DATABASE_URL`, per `GW-004`/`GW-012`) — a cheap `SELECT 1 FROM tenants LIMIT 1`
equivalent (`session.query(...).first() is not None` / `SELECT EXISTS(...)`), not a `COUNT(*)` (no
need to count past one row). This is the single new repository method both this ticket and `SETUP-002`
need — do not add a second, differently-named existence check.

## Implementation acceptance criteria

- [x] `GET /setup/status` (no auth) returns `{"initialized": true|false}` — `true` once at least one
  row exists in `tenants`, `false` otherwise.
- [x] The response body contains **only** this boolean field — no tenant name/count/id or any other
  identifying detail (grep-verifiable: the route's return type has exactly one field).
- [x] `TenantRepository.tenant_exists() -> bool` is the single new repository method backing this
  route, implemented identically in shape on both `SQLiteTenantRepository` and
  `PostgresTenantRepository` (the latter respecting RLS the same way every other Postgres-backend
  method already does — this is a tenant-agnostic read, the same documented exception category as
  `get_by_hash`/`get_user_by_email`, since a fresh-install check must work with `app.tenant_id` unset).

## Test acceptance criteria

- [x] A test covers the zero-tenant state (`{"initialized": false}`).
- [x] A test covers the ≥1-tenant state (`{"initialized": true}`) after provisioning a tenant via the
  existing test fixture/`provision()` path.
- [x] A test asserts the response body has exactly the `initialized` key — no side-channel field.
- [x] `uv run pytest -q` (`.venv\Scripts\python.exe -m pytest -q`) run in full, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms no auth dependency of any kind is attached to this route (reads the route decorator
  directly, not just the test suite).
- Confirms the response model has exactly one field (`initialized: bool`) — no tenant-enumeration
  side channel, by reading the Pydantic model, not just the happy-path test.
- Confirms `tenant_exists()` is implemented on both repository backends and neither duplicates a
  `COUNT(*)`-based existing method under a new name.
- Re-runs `gateway-api`'s full suite, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/gateway-api/README.md` documents `GET /setup/status` as the one deliberate, narrow
  unauthenticated endpoint on this service, and states why (chicken-and-egg — no credential can exist
  yet to gate a check for "does a credential exist yet"), placed alongside the existing Contract
  section's route list.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-001` entry's acceptance-criteria
  boxes are checked and its status marked done.
