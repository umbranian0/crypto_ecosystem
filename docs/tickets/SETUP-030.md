# SETUP-030 — `dashboard-web` added to `docker-compose.yml` as a real service

**Sprint**: 29. **Module**: `infra` (+ new `services/dashboard-web/Dockerfile`). **Status**: done.
**Priority**: Must, and elevated to build-and-land-first in this sprint (see below).
**Depends on**: none. **Blocks**: `SETUP-003` (wants a real container to test against),
`SETUP-004` (its final step starts `dashboard-web` via Compose).
**Can run in parallel with**: `SETUP-001`/`SETUP-002` (Track 1) and `SETUP-010` (Track 2) — disjoint
files (`infra/`, a new `services/dashboard-web/Dockerfile`) vs. `services/gateway-api/`.

## Analysis

Per `docs/sprints/sprint-29.md`'s "Priority bump" section: this ticket is built, reviewed, and merged
**before** `SETUP-003`/`SETUP-004` start meaningful work, per an explicit user decision after a live
incident (DASH-119) where `dashboard-web` running as a bare local process outside Compose — sometimes
from a stale checkout — directly slowed down diagnosing a production bug. This is `backlog-first-run-
setup-and-ops.md`'s `SETUP-030` story, the same category of follow-up `INF-018` was for
`reporting-service`: `dashboard-web` was already built ahead of its own trigger #8 as a disclosed
override (`backlog-infra.md`'s `INF-010` note); `infra/README.md` still says it's "not yet wired into
compose... deliberate, not an oversight," which is now stale wording, exactly the way `INF-018` found
`reporting-service`'s equivalent wording stale.

## Design

**Pattern**: none of implementation-plan.md section 7's patterns apply — pure packaging/wiring, same
non-goal `INF-003`/`INF-004`/`INF-018` already held themselves to.

**Files touched** (scoped to `infra/` and one new file under `services/dashboard-web/`):
- `services/dashboard-web/Dockerfile` (new) — mirrors `services/gateway-api/Dockerfile` exactly in
  shape (builds via `uv sync --frozen --no-dev` against `pyproject.toml`, non-root `appuser`, `libs/
  common` pulled in via an `additional_contexts: {libs: ../libs}` build context since `dashboard-web`
  depends on `naive_first_common` for its shared contract models). `dashboard-web` has no `scripts/`
  directory to copy (unlike `gateway-api`'s `provision_tenant.py`/`revoke_api_key.py`) — omit that
  `COPY` line, don't invent an empty one.
- `infra/docker-compose.yml` — new `dashboard-web` service entry: `build.context: ../services/
  dashboard-web`, `additional_contexts: {libs: ../libs}`, host port `8004` (`DASHBOARD_WEB_PORT`,
  first free port after `minio`'s `9001` isn't used — following the established `8000`/`8001`/`8002`/
  `8003` sequence for app services, `8004` is next), bound `127.0.0.1`-only (same convention every
  other app-service port binding in this file already uses), `GATEWAY_API_URL` set to `http://
  gateway-api:8000` (the internal Compose hostname, not `localhost` — this service's existing env var,
  already read by `dependencies/downstream.py`/`dependencies/http_client.py`, needs zero code change,
  only a Compose-level override, same pattern `GATEWAY_API_VALIDATION_SERVICE_URL` already uses for
  `gateway-api` → `validation-service`). `depends_on: gateway-api` is **not** a hard `condition:
  service_healthy` dependency — `dashboard-web`'s own downstream HTTP calls already degrade to
  `error.html`/`GatewayApiUrlDep`'s existing transport-failure handling on an unreachable `gateway-api`
  (same rationale `gateway-api`'s own compose entry gives for not hard-depending on `validation-
  service`).
- `infra/.env.example` — new `DASHBOARD_WEB_PORT`/`DASHBOARD_WEB_GATEWAY_API_URL` documented entries,
  same two-value-forms convention (Compose-network vs. local non-Compose-dev) every other service's
  block in this file already follows.
- `infra/README.md` — remove `dashboard-web` from the "not yet wired into compose" sentence; add a new
  "dashboard-web (SETUP-030)" section mirroring the "reporting-service (INF-018)" section's shape
  (compose-entry description, env vars, start/verify commands, explicit statement that this is
  packaging/wiring only with zero `services/dashboard-web/src/` changes) — cross-referencing this
  ticket the same way `INF-018`'s section cross-references `RS-GAP`. Also add the disclosed,
  revisit-triggered note the ticket's own AC requires: `127.0.0.1`-only binding is a decision to
  revisit the day a non-localhost operator needs to reach this UI directly (a human operator reaching
  a UI is a different exposure shape than a service-to-service call — flag this explicitly, don't bury
  it in the generic port-binding rationale the other services share).

**DRY check note**: grepped `infra/docker-compose.yml` before writing this ticket — every existing app
service (`validation-service`/`gateway-api`/`reporting-service`/`ingestion-service`) already follows
one shared shape (`build.context` + `additional_contexts: {libs: ...}` + env-var-driven port + a
`depends_on: postgres: condition: service_healthy` where relevant). This ticket's new entry reuses that
exact shape — no second Compose service pattern invented. `services/gateway-api/Dockerfile` is the
direct template for the new `services/dashboard-web/Dockerfile` (same non-root/`uv sync`/`EXPOSE`/`CMD`
shape), not re-derived from scratch.

## Implementation acceptance criteria

- [x] `services/dashboard-web/Dockerfile` exists, builds via its own `pyproject.toml` (`uv`-managed),
  runs as non-root `appuser`, matches the `OPS-004`-verified non-root/port-binding precedent.
- [x] `infra/docker-compose.yml` defines a `dashboard-web` entry (`build: ../services/dashboard-web`)
  on host port `8004` (`DASHBOARD_WEB_PORT`), with `GATEWAY_API_URL` set to `http://gateway-api:8000`
  (internal Compose hostname), bound `127.0.0.1`-only.
- [x] `infra/README.md`'s "not yet wired into compose" list is updated to remove `dashboard-web`,
  cross-referencing this ticket.
- [x] Zero changes under `services/dashboard-web/src/` — packaging/wiring only.

## Test acceptance criteria

- [x] Full-stack smoke test: `docker compose up` (or targeted `up -d --build dashboard-web`) brings up
  `dashboard-web` alongside the other five services; `dashboard-web`'s own `GET /health` (`DASH-008`)
  returns `200`, reflecting `gateway-api`'s real health over the Compose network — proof of
  Compose-network reachability end to end, not just "the container starts."

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms `git status` scoped to `services/dashboard-web/src/` shows zero changes before and after.
- Confirms the Dockerfile mirrors `gateway-api`'s non-root/`uv sync --frozen --no-dev` shape (no drift
  invented for this one service).
- Live-verifies `docker compose up -d --build dashboard-web` (with the rest of the stack already up)
  succeeds and `curl http://localhost:8004/health` returns `200` from the host.
- Confirms `infra/README.md`'s new section states the `127.0.0.1`-only binding as an explicitly
  flagged decision to revisit, not silently folded into the generic port-binding paragraph.

## Documentation acceptance criteria

- [x] `infra/README.md` gains a "dashboard-web (SETUP-030)" section (compose entry, env vars,
  start/verify commands, revisit-trigger note) and no longer lists `dashboard-web` under "not yet
  wired into compose."
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-030` entry's acceptance-criteria
  boxes are checked and its status marked done.
