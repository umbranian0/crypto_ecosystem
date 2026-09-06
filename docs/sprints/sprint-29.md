# Sprint 29 — First-run browser setup wizard (Epic A, plus its two real prerequisites)

Sprint goal: replace today's manual bootstrap-script → `docker compose exec ... provision_tenant.py`
→ separately-started `dashboard-web` sequence with one command that lands an operator in a
browser-based setup wizard (tenant name in, API key shown once, straight into `/login`). This is
Epic A in full, plus the two prerequisites Epic A cannot function without.

Backlog source: `docs/product/backlog-first-run-setup-and-ops.md` — Epic A (SETUP-001/002/003/004),
plus `SETUP-030` (Epic D) and `SETUP-010` (Epic B), pulled forward per that backlog's own
"Sequencing note." None of `SETUP-*` has been started (confirmed against `docs/tickets/README.md` —
no `SETUP-*` section exists yet).

## Scope decision: what's in, what's deliberately not

**In scope (6 tickets):**

- **SETUP-001** — `gateway-api`: unauthenticated `GET /setup/status` fresh-install detection.
- **SETUP-002** — `gateway-api`: bootstrap-only `POST /setup/initialize` (409 once a tenant exists).
- **SETUP-003** — `dashboard-web`: the wizard itself (`/setup` form → key-shown-once → `/login`).
- **SETUP-004** — `infra`: bootstrap script brings up the full stack and opens the browser on the
  wizard.
- **SETUP-030** — `infra`: `dashboard-web` added to `docker-compose.yml` as a real service.
- **SETUP-010** — `gateway-api`: platform-operator authentication for cross-tenant admin endpoints.

**Out of scope, explicitly, for a future sprint ("next"):** `SETUP-011`/`012` (tenant-list/create/
revoke endpoints + the Settings → Tenants page — the actual *use* of `SETUP-010`'s operator
credential), `SETUP-015` (read-only Environment panel), Epic C in full (`SETUP-020`/`021`/`022` —
Monitoring visibility), and `SETUP-031`/`032`/`033` (portability audit, fresh-machine dry run,
CI smoke test). `SETUP-013`/`014`/`023` stay `Won't` per the backlog itself, untouched.

**Why SETUP-010 is in this sprint despite Epic A not strictly needing it:** the wizard's own flow
(`SETUP-001`→`004`) never calls an operator-authenticated endpoint — `/setup/status` is
deliberately unauthenticated (chicken-and-egg) and `/setup/initialize` is gated by the `409`-after-
first-tenant guard, not by any credential. So Epic A is buildable without `SETUP-010` existing at
all. It's included anyway because the backlog's own sequencing note calls it out by name as one of
"the two real unlocks everything else... sits on top of," and because leaving it for the Epic B
sprint means Epic B (`SETUP-011`/`012`, the actual tenant-management UI) can start immediately once
this sprint closes rather than opening with its own architecture ticket first. `SETUP-010` touches
`gateway-api` only and is file-disjoint from every other ticket this sprint (see File-overlap below)
— it costs nothing to run in parallel, and doing it now means the very next sprint's Epic B work
starts building the actual `/tenants` endpoints against a boundary that already exists, instead of
re-deriving it under time pressure once someone finally asks "what stops any tenant from listing
every other tenant?"

## What "configure the installation including the database" means in this sprint — and what it does not

The user's ask included configuring the database as part of first-run setup. **This sprint does not
add any UI for database credentials, connection strings, or DB configuration**, and that is by
design, not an oversight:

- `infra/docker-compose.yml` already brings up Postgres and Redis automatically as part of
  `docker compose up` — no manual DB setup step exists today, and `SETUP-030` (this sprint) is what
  makes `dashboard-web` join that same automatic stack instead of needing to be started separately.
- Migrations are already idempotent (`INF-016`, shipped) — the bootstrap script (`SETUP-004`,
  this sprint) runs them as part of the one-command path with no new migration UI needed.
- Exposing `DATABASE_URL`/connection strings/credentials in any UI is explicitly out of scope —
  that's `SETUP-015`'s territory (read-only Environment panel, **not scheduled this sprint**), and
  even `SETUP-015` itself is designed to never render a secret value at all, only non-secret
  connectivity facts. No story in this sprint renders, edits, or even reads a DB credential.
- So: "configure the database" in this sprint's actual deliverable means *the operator never has to
  think about the database at all* — Compose brings it up, migrations apply themselves, and the
  wizard's only input is a tenant name. It does **not** mean a settings form with a DB host/port/
  password field. If the user's mental model was the latter, that's `SETUP-015`'s (declined-scope-
  for-now) territory, not this sprint's — flag this back to the user explicitly before Tech Lead
  kickoff so expectations match what actually ships.

## Stories in scope, in execution order

1. **SETUP-010** — `gateway-api`: operator auth (`OPERATOR_TOKEN`, `get_authenticated_operator`
   dependency). No dependency on anything else this sprint. Runs from the start, in parallel with
   Track 2 below — touches only `gateway-api`'s auth/dependencies layer, no `/tenants` endpoints are
   built this sprint to guard (that's `SETUP-011`, next sprint), so this ticket's own scope is the
   mechanism and its test proving a tenant's own API key gets `403` against it, not a real consumer
   yet.
2. **SETUP-030** — `infra`: `dashboard-web` Dockerfile + Compose entry. No dependency on anything
   else this sprint. Runs from the start, in parallel with Track 1 and Track 3 — pure infra/
   packaging, zero `services/dashboard-web/src/` changes.
3. **SETUP-001** — `gateway-api`: `GET /setup/status`. No dependency. Can start immediately,
   alongside `SETUP-010`, since both touch `gateway-api` but in disjoint areas (a new router vs. a
   new auth dependency) — see File-overlap note below on why these two are still sequenced with care.
4. **SETUP-002** — `gateway-api`: `POST /setup/initialize`. Depends on `SETUP-001` (same new
   `setup` router file). Sequential after `SETUP-001`.
5. **SETUP-003** — `dashboard-web`: the wizard UI. Depends on `SETUP-002` (calls it) and practically
   wants `SETUP-030`'s Compose wiring in place to test realistically against a real `gateway-api`
   container rather than a stub. Sequenced after both.
6. **SETUP-004** — `infra`: bootstrap script opens the browser on the wizard. Depends on `SETUP-003`
   (the thing it opens) and `SETUP-030` (the thing that starts `dashboard-web` via Compose). Runs
   last — it is the integration point the whole sprint closes on.

## Parallelization

- **Track 1 (`gateway-api`, setup-status/initialize chain)**: `SETUP-001` → `SETUP-002`.
- **Track 2 (`gateway-api`, operator auth)**: `SETUP-010`, standalone.
- **Track 3 (`infra`, Compose wiring)**: `SETUP-030`, standalone.
- Tracks 1, 2, and 3 can all start simultaneously — three different concerns even though two land in
  the same service. Recommended sequencing to avoid same-file collisions within `gateway-api`:
  either assign `SETUP-001`/`002` and `SETUP-010` to different implementers working in genuinely
  disjoint files (a new `routers/setup.py` vs. a new/edited `dependencies/auth.py`), or run them
  sequentially if the Tech Lead wants one implementer carrying both — either is safe, but confirm
  `main.py`'s router-registration line isn't a collision point if both land the same day.
- **SETUP-003** (`dashboard-web`) starts once `SETUP-002` and `SETUP-030` are both done — it is the
  first ticket requiring two other tracks to have already landed.
- **SETUP-004** (`infra`) runs last, after `SETUP-003` and `SETUP-030` are both confirmed done.
- Net shape: three parallel tracks converge into `SETUP-003`, which then feeds `SETUP-004` as the
  sprint's closing integration ticket.

## File-overlap / concurrent-work risk

- `services/gateway-api/src/app/main.py` — both `SETUP-001`/`002` (new `setup` router registration)
  and `SETUP-010` (new operator-auth dependency, likely imported but not necessarily registered here
  unless it gates a route in this sprint) may touch this file's import/registration lines. Low risk
  since `SETUP-010` guards no route yet this sprint (that's `SETUP-011`, next sprint) — but flag it
  to whoever picks up `SETUP-010` so they don't wire it onto `/setup/*` by mistake: `/setup/status`
  and `/setup/initialize` are deliberately *not* operator-gated (chicken-and-egg, no credential
  exists yet on a fresh install).
- `services/gateway-api/README.md` — `SETUP-001`, `SETUP-002`, and `SETUP-010` each add their own
  documentation section (the one unauthenticated endpoint; the narrow bootstrap-only exception; the
  second, narrower operator-auth mechanism). Three edits to one file — sequence the actual doc edits
  or merge carefully; no code-level collision either way.
- `infra/docker-compose.yml` and `infra/README.md` — touched by `SETUP-030` (adds `dashboard-web`
  service, updates the "not yet wired into compose" list) and `SETUP-004` (bootstrap script's final
  step). `SETUP-004` depends on `SETUP-030` already being done, so this is naturally sequential, not
  a real collision risk.
- `services/dashboard-web/` — `SETUP-003` is the only ticket touching this service's `src/` this
  sprint; `SETUP-030` touches only its `Dockerfile` (new file) and leaves `src/` untouched per its
  own acceptance criteria. No overlap.
- No ticket this sprint touches `libs/naive_first_engine`, `libs/common`, `services/validation-service`,
  or `services/reporting-service` — confirm via `git status` scoped to those paths before and after,
  same discipline every prior sprint has held to.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

- `gateway-api` gains one new unauthenticated endpoint (`SETUP-001`), one new bootstrap-only endpoint
  guarded by a `409`-after-first-tenant check rather than a credential (`SETUP-002`), and one new,
  narrower auth mechanism that no route actually uses yet this sprint (`SETUP-010` — its real
  consumer, `/tenants`, is `SETUP-011`, next sprint). `SETUP-002` must call the exact same
  `provision()` function `provision_tenant.py` already uses — no second tenant-creation code path.
- `dashboard-web` gains its first pre-authentication route (`/setup`) and a root-route branch
  (`initialized: false` → `/setup`, else → `/login`) — no change to any existing authenticated route.
- `infra` gains `dashboard-web` as a sixth Compose service (`SETUP-030`) and a bootstrap-script final
  step that opens/prints the wizard URL (`SETUP-004`) — the existing "print the `provision_tenant.py`
  invocation" step is kept underneath as the non-interactive/CI-friendly alternative, not deleted.
- No service imports another service's code; `dashboard-web` continues to reach `gateway-api` only
  over HTTP, never touching a database directly (unchanged trust boundary, consistent with
  `SETUP-030`'s own port-binding note in the backlog).
- No trigger is crossed and no leakage-aware protocol code (`naive_first_engine`, DM-test computation)
  is touched by any ticket this sprint.

## Definition of done for this sprint

- `SETUP-001`: `GET /setup/status` returns only `{"initialized": bool}`, no tenant-enumeration
  side channel; both zero-tenant and ≥1-tenant states tested; README documents it as the one
  deliberate unauthenticated endpoint and why.
- `SETUP-002`: `POST /setup/initialize` creates exactly one tenant via the shared `provision()`
  function; a second call (any tenant name) returns `409` with zero additional rows; raw key
  returned once, never logged; README documents the tradeoff explicitly.
- `SETUP-003`: fresh install redirects `/` → `/setup`; successful submission shows the raw key once
  with a "copy this now" warning, then links to `/login`; visiting `/setup` post-initialization
  redirects straight to `/login` with no error surfaced; Selenium E2E extended for the full flow;
  wizard copy says "tenant" and "API key for validation runs" only — no trading/prediction framing.
- `SETUP-004`: bootstrap script's final step starts `dashboard-web` via Compose and opens/prints the
  wizard URL; running the full script twice against an already-initialized stack produces exactly one
  tenant and no non-zero exit; the `provision_tenant.py`-invocation print step is kept, not deleted.
- `SETUP-030`: `dashboard-web` has a working Dockerfile and a Compose entry on `127.0.0.1`-only
  binding, `GATEWAY_API_URL` pointed at the internal Compose hostname; `infra/README.md`'s "not yet
  wired into compose" list no longer names `dashboard-web`; full `docker compose up` brings up all
  six services; zero changes under `services/dashboard-web/src/` beyond wiring.
- `SETUP-010`: a real `OPERATOR_TOKEN`-based dependency exists, structurally separate from
  `get_authenticated_tenant`; a test proves a real tenant's own API key gets `403` when presented to
  it (even with no `/tenants` route yet to protect, the dependency itself is directly testable);
  README documents it as a disclosed, narrow, single-shared-secret stopgap with a named revisit
  trigger (a second real human operator needing their own credential).
- No new DB-configuration UI anywhere in this sprint's diff — confirmed via review, not merely
  asserted (see "What 'configure the database' means" above).
- `services/gateway-api/README.md`, `services/dashboard-web/README.md`, and `infra/README.md` all
  updated as part of the same tickets that change their respective services' behavior.
- Full test suites for `gateway-api`, `dashboard-web`, and a Compose-level smoke test all re-run with
  zero regressions.
- `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-001/002/003/004/010/030` entries marked
  done with acceptance-criteria boxes checked; `SETUP-011/012/015` and Epic C left unchanged, noted
  here as "next" for the Epic B/C sprint that follows.

## Next (explicitly not this sprint)

- **Epic B, remainder**: `SETUP-011` (`/tenants` list/create/revoke endpoints, now unblocked by this
  sprint's `SETUP-010`) → `SETUP-012` (Settings → Tenants page) → `SETUP-015` (read-only Environment
  panel, no hard dependency, can slot in alongside).
- **Epic C in full**: `SETUP-020` (per-service health) → `SETUP-021` (recent-errors ring buffer,
  depends on `SETUP-010`, now available) → `SETUP-022` (run throughput/failure rate).
- **Epic D, remainder**: `SETUP-031` (portability audit) → `SETUP-032` (fresh-machine single-command
  dry run, depends on `SETUP-004`/`SETUP-030` from this sprint plus `SETUP-031`) → `SETUP-033`
  (CI smoke test, Could, depends on `OPS-001` already shipped plus `SETUP-032`).
