# Backlog — First-run setup, in-UI configuration, monitoring visibility, and portability

Source: `CLAUDE.md` (root — non-negotiable positioning: validation/audit infrastructure, never a
trading/prediction product); `docs/implementation-plan.md` sections 2 (module boundary map), 4
(inter-service communication), 6 (trigger-based build order), 7 (design patterns), 9 (DRY/engineering
conventions); `docs/adr/0003-disclosed-trigger-override-pattern.md`; `docs/product/backlog-infra.md`
(full text, including the INF-014/015/016/017/018 additions — non-superuser app role, bootstrap
script, migration script, the DB-backed-config decline, and `reporting-service`'s Compose wiring
precedent); `docs/product/backlog-technical-upgrades.md` (ARCH-001–008, DRY/DI/pattern conventions
already audited and either confirmed solid or already ticketed); `docs/product/backlog-operability.md`
(OPS-001–007 — CI, coverage, dependency cadence, Dockerfile/port-binding verification, `/health`
depth, structured logging, and the explicit decline of a metrics/alerting stack); `infra/docker-compose.yml`,
`infra/README.md`, `infra/bootstrap.ps1`, `infra/.env.example` (read directly — confirmed
`dashboard-web` is not yet a Compose service, and the bootstrap script's own final step is "print
the `provision_tenant.py` invocation," not run it); `services/gateway-api/README.md`,
`services/gateway-api/scripts/provision_tenant.py`, `services/gateway-api/scripts/revoke_api_key.py`
(read in full — CLI-only, operator-host-access-gated, one-time-reveal API key contract);
`libs/common/src/naive_first_common/logging.py` (OPS-006 — structured JSON logging + correlation id,
already shipped); `services/dashboard-web/README.md` (read in full — current scope is
login/session, run detail, submit-a-run, runs list, logout, health check, Selenium E2E; no config or
monitoring screens exist yet; the OneDrive-sync `.venv` workaround is already disclosed there).

## Scope

**In scope**: four themes, each its own epic — (1) collapsing today's multi-step, partly-manual
first-run sequence (bootstrap script → manual `docker compose exec ... provision_tenant.py` →
separately-started `dashboard-web`) into one command landing an operator in a browser-based setup
wizard; (2) an authenticated Settings area in `dashboard-web` for tenant/API-key lifecycle
management (replacing the exec-into-container scripts) and a read-only view of non-secret
configuration; (3) read-only operational visibility (per-service health, recent errors, run
throughput/failure rate) in `dashboard-web`, explicitly not an alerting/paging system; (4) making the
Compose stack (including `dashboard-web`, not currently a Compose service) genuinely portable to a
fresh machine, auditing hardcoded/OS-specific assumptions along the way.

**Out of scope, stated explicitly, per this backlog's own instruction not to propose stories for a
module whose trigger hasn't fired**: any configuration surface for `ingestion-service` connectors
(trigger #6 has not fired — no such service exists as code yet; see `SETUP-013`), any feature-flag UI
(no real per-tenant/per-operator behavior difference exists in the platform today to flag — same
YAGNI reasoning `backlog-infra.md`'s `INF-017` already applied and declined; see `SETUP-014`), and any
metrics/alerting/paging stack (`backlog-operability.md`'s `OPS-007` already declined this explicitly;
see `SETUP-023`).

**Trigger-override disclosure (per ADR-0003), stated plainly rather than assumed:**
- `dashboard-web` itself is not a new override introduced by this backlog — it was already built
  ahead of its own trigger #8 as a disclosed override in an earlier sprint (see
  `docs/product/backlog-infra.md`'s `INF-010` note: "trigger #8 (`dashboard-web`) has since fired as
  its own disclosed override"). This backlog adds features to an already-triggered, already-existing
  module (Settings, Monitoring) — that is ordinary roadmap work on a module that exists, not a fresh
  trigger override, and needs no new disclosure of that specific kind.
- **`SETUP-030` (wiring `dashboard-web` into `infra/docker-compose.yml`) *is* explicitly the same
  category of follow-up `INF-018` was for `reporting-service`**: a module that was already built ahead
  of its trigger gets its remaining infra-wiring gap closed in a later, separately-disclosed ticket.
  `infra/README.md` currently states `dashboard-web` is "not yet wired into compose... deliberate, not
  an oversight" because its trigger (#8) "hasn't fired" — that wording is now stale in exactly the way
  `INF-018`'s own opening paragraph found `reporting-service`'s wording to be stale (the module *has*
  already been built as a disclosed override; only the Compose-wiring half was left undone). `SETUP-030`
  closes that gap and updates `infra/README.md` accordingly, the same way `INF-018` did for
  `reporting-service`.
- No story in this backlog proposes building `ingestion-service`, `reporting-service`'s remaining gaps
  (that's `GW-018`'s territory, not this backlog's), or `economic-service` ahead of their own triggers.

**No story in this backlog authorizes skipping the leakage-aware protocol.** None of the four themes
touch splitting, baselines, metrics, or DM-test computation — this is entirely setup/ops/UI scope
around an engine (`naive_first_engine`) and its wrapping services that this backlog does not modify.

## Prioritization scheme

MoSCoW, same convention `backlog-infra.md`/`backlog-technical-upgrades.md` already use. Each story's
one-line rationale ties back to what it unlocks and its module's owns/does-not-own boundary.

---

## Epic A — First-run automatic setup

### SETUP-001 — `gateway-api`: fresh-install detection endpoint [Must]

**As** `dashboard-web`'s setup flow **I want** an unauthenticated `GET /setup/status` endpoint that
reports whether any tenant exists yet **so that** the UI can decide whether to show the setup wizard
or the ordinary login page, without needing any credential to ask the question in the first place
(there is, by definition, no credential yet on a fresh install).

Acceptance criteria:
- [ ] `GET /setup/status` (no auth) returns `{"initialized": true|false}` — `true` once at least one
  row exists in the `tenants` table, `false` otherwise.
- [ ] The response contains **only** this boolean — no tenant names, counts, ids, or any other
  identifying detail — so this endpoint cannot become a tenant-enumeration side channel for anything
  that can merely reach `gateway-api`'s public port.
- [ ] A test covers both the zero-tenant and the ≥1-tenant state.
- [ ] `gateway-api`'s README documents this as the one deliberate, narrow unauthenticated endpoint on
  the service, and states why (chicken-and-egg: no credential can exist to gate a check for "does a
  credential exist yet") — the same reasoning `provision_tenant.py`'s own docstring already applies to
  itself, now given a network-safe read-only counterpart.

Rationale for priority: Must — every other story in this epic needs this signal to decide what to
render; nothing else in the epic is buildable without it.
Depends on: none

### SETUP-002 — `gateway-api`: bootstrap-only tenant + admin-key creation endpoint [Must]

**As** the setup wizard **I want** a `POST /setup/initialize` endpoint that creates the first tenant
and mints its first API key, but only while `SETUP-001`'s check reports `initialized: false` **so
that** the browser flow can replace today's `docker compose exec ... provision_tenant.py` step
without opening a general-purpose, permanently-available public tenant-signup endpoint.

Acceptance criteria:
- [ ] `POST /setup/initialize` accepts `{"tenant_name": str}` and internally calls the **exact same**
  `provision()` function `provision_tenant.py` already uses (no second, parallel tenant-creation code
  path — DRY per implementation-plan.md section 9).
- [ ] If a tenant already exists (`initialized: true`), the endpoint returns `409 Conflict` and
  creates nothing — this is what makes re-running the golden path against an already-initialized
  system a safe no-op instead of a duplicate-tenant bug.
- [ ] The raw API key is returned in the response body exactly once, matching `provision_tenant.py`'s
  existing one-time-reveal contract; it is never logged (the shared `provision()` function's existing
  `extra=` discipline — `tenant_id` only, never the raw key — already guarantees this without change).
- [ ] `gateway-api`'s README documents this endpoint explicitly as a narrow, deliberate exception to
  "no public tenant-creation surface exists" elsewhere in that same README — the `409`-after-first-tenant
  guard is the entire thing standing between "first-run convenience" and "an open public signup form,"
  and that tradeoff is stated in writing, not left implicit.
- [ ] A test proves: first call succeeds and creates exactly one tenant + one key; a second call
  (even with a different `tenant_name`) returns `409` and the tenant table still has exactly one row.

Rationale for priority: Must — this is the one genuinely new piece of network-reachable scope the
whole epic depends on; every other story here is UI/orchestration wrapped around it.
Depends on: SETUP-001

### SETUP-003 — `dashboard-web`: browser-based setup wizard [Must]

**As** an operator standing up the platform for the first time **I want** `dashboard-web` to detect a
fresh install and show me a setup form (tenant name → submit → API key shown once) instead of a login
page **so that** I no longer need a terminal/`docker exec` step to get a usable tenant and key.

Acceptance criteria:
- [ ] `dashboard-web`'s root route checks `SETUP-001`'s `/setup/status`; if `initialized: false`, it
  redirects to `/setup` instead of `/login`.
- [ ] `GET /setup` renders a tenant-name form; `POST /setup` calls `SETUP-002`'s `/setup/initialize`.
- [ ] On success, the raw API key is shown exactly once on a confirmation page with an explicit
  "copy this now — it cannot be recovered" warning, mirroring `provision_tenant.py`'s own one-time-reveal
  discipline, followed by a link to `/login`.
- [ ] If `/setup` is visited after initialization (`initialized: true`), it redirects straight to
  `/login` rather than re-rendering the form or surfacing `SETUP-002`'s `409` as an error — no path in
  the UI can trigger that conflict by accident.
- [ ] Extends `dashboard-web`'s existing Selenium E2E suite (`DASH-009`) with a flow covering: fresh
  stub `gateway-api` (zero tenants) → wizard shown → submit → key displayed once → `/login` succeeds
  with that key.
- [ ] Positioning check: the wizard's copy describes what's being created as a "tenant" and an "API
  key for validation runs" — never anything implying trading/prediction capability (CLAUDE.md).

Rationale for priority: Must — the actual user-facing deliverable this epic exists to produce; without
it the "browser-based, not a CLI script" promise is just an API, not a real flow.
Depends on: SETUP-002

### SETUP-004 — `infra`: bootstrap script brings up the full stack and lands the operator in the wizard [Must]

**As** a developer standing up this platform for the first time **I want**
`infra/bootstrap.sh`/`.ps1` to bring up every service (including `dashboard-web`, per `SETUP-030`) and
open my browser at `dashboard-web`'s root **so that** "one command → a working setup wizard" is real,
not a partial sequence that still ends in a manual step.

Acceptance criteria:
- [ ] The bootstrap script's final step starts `dashboard-web` via Compose (depends on `SETUP-030`)
  and opens the default browser at `http://localhost:<dashboard-port>/` — or, if the environment has
  no way to launch a browser (e.g. a headless CI runner), prints that same URL instead of failing.
- [ ] The current final step ("print the `provision_tenant.py` invocation") is **kept, not deleted**,
  documented underneath as the non-interactive/CI-friendly alternative — same "demote, don't delete"
  convention `infra/README.md` already applies to its own hand-run sequences.
- [ ] Running the full script twice in a row against an already-initialized stack produces **no
  duplicate tenant and no non-zero exit** — Compose `up` is already idempotent, migrations are already
  idempotent (`INF-016`), and the wizard itself now redirects to `/login` instead of erroring
  (`SETUP-003`'s own AC) — this story's own Definition of Done is running the script twice and
  confirming exactly one tenant exists afterward.

Rationale for priority: Must — closes the loop the whole epic exists to close: one command, not "one
command plus a manual `docker exec` plus a separately-started `dashboard-web`."
Depends on: SETUP-003, SETUP-030

---

## Epic B — In-UI system configuration

**Explicit architectural gap this epic surfaces (not silently decided around):** every existing auth
mechanism in this platform is per-tenant (a tenant's own API key, or `dashboard-web`'s session cookie
derived from one). Tenant lifecycle management (create/list/revoke *other* tenants) is a cross-tenant,
platform-operator action — no tenant's own credential should ever be able to perform it. Today that
boundary is enforced only by `provision_tenant.py`/`revoke_api_key.py` requiring host/container access
to run at all. Moving this into a network-reachable UI requires a **distinct operator-level credential**,
which does not exist anywhere in this codebase yet. `SETUP-010` names and resolves this gap explicitly,
choosing the smallest correct mechanism rather than a multi-admin-user system nobody has asked for yet.

### SETUP-010 — `gateway-api`: platform-operator authentication for cross-tenant admin endpoints [Must]

**As** `dashboard-web`'s Settings area **I want** a distinct operator-level authentication mechanism,
separate from any tenant's own API key **so that** no tenant's ordinary credential can list, create,
or revoke any tenant (including itself, or another tenant it should have no visibility into).

Acceptance criteria:
- [ ] A new operator credential exists out of band from tenant API keys (e.g. a single
  `OPERATOR_TOKEN` env var, hashed with the same `hashlib.sha256` convention tenant keys already use,
  checked by a new `get_authenticated_operator` FastAPI dependency, structurally separate from
  `get_authenticated_tenant`).
- [ ] Every endpoint under `/tenants` (list/create/revoke, `SETUP-011`) requires the operator
  dependency — never `get_authenticated_tenant`.
- [ ] A test proves a real tenant's own API key, presented to any `/tenants` endpoint, is rejected
  (`403`) — the cross-boundary case this story exists to close.
- [ ] `gateway-api`'s README documents this as a second, narrower auth mechanism, states plainly it is
  a deliberate stopgap (one shared operator secret, not a multi-admin-user system), and names the
  concrete trigger for revisiting it (a second real human operator who needs their own distinguishable
  credential) — same "disclosed interim, not silent" convention this platform already applies elsewhere
  (e.g. `dashboard-web`'s in-memory `SessionStore`).

Rationale for priority: Must — every other story in this epic depends on this boundary existing;
without it, "Settings area" would either go unbuilt or would accidentally let any tenant manage any
other tenant, which would be a real tenant-isolation regression, not a hypothetical one.
Depends on: none

### SETUP-011 — `gateway-api`: tenant list/create/revoke admin endpoints [Must]

**As** `dashboard-web`'s Settings area **I want** `GET /tenants`, `POST /tenants`, and a revoke
endpoint exposed as operator-authenticated HTTP endpoints **so that** the same lifecycle actions
`provision_tenant.py`/`revoke_api_key.py` already perform via `docker compose exec` become reachable
over the network instead.

Acceptance criteria:
- [ ] `GET /tenants` (operator-auth) returns each tenant's `id`/`name`/`created_at` and its API keys'
  `id`/`created_at`/`revoked_at` — **never** `key_hash` or any recoverable form of a raw key (raw keys
  were never persisted in the first place, per `GW-004`/`GW-005`'s existing design).
- [ ] `POST /tenants` (operator-auth) creates a tenant + first key via the **same** `provision()`
  function `SETUP-002` and `provision_tenant.py` already share — one function, three callers (CLI,
  bootstrap wizard, this endpoint), never three copies (DRY per implementation-plan.md section 9).
- [ ] `POST /tenants/{id}/api-keys/{key_id}/revoke` (operator-auth) wraps `revoke_api_key.py`'s
  `revoke()` the same way — one shared function, not a duplicate revocation code path.
- [ ] Existing CLI scripts are kept, not deleted or deprecated — documented explicitly as "two front
  doors to the same function," useful for an operator with host access and no browser open.
- [ ] Tests cover list/create/revoke through the new endpoints and the existing
  already-revoked-is-a-no-op guarantee `revoke()` already provides.

Rationale for priority: Must — the concrete backend half of "replacing the exec-into-container flow,"
the task's own named ask.
Depends on: SETUP-010

### SETUP-012 — `dashboard-web`: Settings → Tenants page [Must]

**As** an operator **I want** a Settings area in `dashboard-web` listing tenants and their API keys,
with actions to create a tenant (showing its key once) and revoke a key **so that** I never need a
terminal for routine tenant management.

Acceptance criteria:
- [ ] `/settings/tenants` requires the new operator credential (`SETUP-010`) — **not** an ordinary
  tenant session cookie; a tenant's own logged-in session must not be able to reach this page.
- [ ] Lists tenants + their keys, keys shown only as metadata (id, created/revoked timestamps) —
  never a raw or partially-masked key value once creation is past.
- [ ] "Create tenant" shows the new raw key exactly once on a confirmation page, using the same
  one-time-reveal template/partial `SETUP-003`'s wizard already introduced (extracted into one shared
  component rather than a second near-identical page — DRY within this module, per implementation-plan.md
  section 9).
- [ ] "Revoke" re-renders the list showing the key's new `revoked_at` with no manual page refresh
  required.
- [ ] Positioning check: no copy on this page implies trading/prediction capability (CLAUDE.md).

Rationale for priority: Must — the actual UI deliverable for the task's named tenant-management ask.
Depends on: SETUP-011

### SETUP-013 — Connector schedule/credential configuration in Settings [Won't, this backlog]

**Superseded by `DASH-112`** (Sprint 18): `ingestion-service` (trigger #6) has since fired and shipped,
and `DASH-112` added a read-only, per-tenant connector credential-status view at
`services/dashboard-web`'s `/settings/connectors` (view-only: whether a credential is stored + its
last-set timestamp, never the value; no write form — see that service's README). The rationale below
(written before trigger #6 fired) is kept for the historical record, not because it still fully
applies — `DASH-112`'s read-only scope is a deliberate subset of what this story originally described,
not the full view/edit story: connector *schedule* configuration and credential *editing* remain
unbuilt (credential writes stay CLI-only via `set_connector_credentials.py`), and a real tenant
directory (`SETUP-011`) is still the named prerequisite for a non-manual `tenant_id` lookup on that
page.

**As** an operator **I want** to view/edit `ingestion-service` connector schedules and credentials
from Settings.

Rationale (historical — see supersession note above): **Won't, this backlog.** `ingestion-service`
(trigger #6) has not fired — no such service exists as code yet. This backlog's own governing
instruction is explicit: never propose stories for a module whose trigger hasn't fired. Revisit the
moment `ingestion-service` is scaffolded; its own backlog is the right place for its first
Settings-surfaced config, not this one, invented ahead of the service existing.
Depends on: none (blocked on trigger #6, not on anything in this backlog)

### SETUP-014 — Feature flags in Settings [Won't, this backlog]

**As** an operator **I want** a feature-flags panel in Settings.

Rationale: **Won't, this backlog** — same reasoning `backlog-infra.md`'s `INF-017` already applied and
declined for DB-backed configuration generally: no real per-tenant or per-operator behavior difference
exists anywhere in the running platform today for a flag to gate. Building a flags UI with nothing
real to flip would be exactly the speculative scaffolding `libs/common`'s own README rules out
(YAGNI — move on second real use). Revisit the first time a real optional behavior needs toggling
without a redeploy.
Depends on: none

### SETUP-015 — Settings: read-only "Environment" panel [Should]

**As** an operator **I want** a read-only panel in Settings showing which service URLs/ports the
running stack is configured with (no secrets, no edit capability) **so that** I have one place to see
what's live without SSHing in or reading `.env` files, while staying honest that these values need a
restart/redeploy to change, not a form submission.

Acceptance criteria:
- [ ] Shows non-secret connectivity facts (which services exist, their configured hostnames/ports,
  links into the Monitoring page for live status) — explicitly labeled "read-only — change via
  `infra/.env` and restart the stack, not this page."
- [ ] No secret value (`DATABASE_URL`, passwords, API keys, `OPERATOR_TOKEN`) is ever rendered, even in
  a redacted-looking form — only the non-secret facts named above. This is not a "hide it behind a
  toggle" pattern; the data is never sent to the template at all.
- [ ] This page has **no** POST/edit route — read-only is enforced structurally (no route exists to
  change any of it), not merely by omitting a button from the template.

Rationale for priority: Should — real operator value (the task's own "view... configuration" ask), but
scoped strictly to display so it can't become an accidental channel for editing bootstrap-order values
that `INF-017` already established can't be safely live-edited (`DATABASE_URL`, `REDIS_URL`, etc. are
needed before any DB/Redis connection exists — moving them into a live-editable UI would recreate the
same chicken-and-egg problem `INF-017` named and declined to solve).
Depends on: none

---

## Epic C — Monitoring visibility

Scoped deliberately to **read-only visibility**, per the task's own instruction: no
alerting/paging subsystem is introduced (`backlog-operability.md`'s `OPS-007` already declined a full
metrics/alerting stack; nothing here reopens that).

### SETUP-020 — Per-service health status surfaced in `dashboard-web` [Must]

**As** an operator **I want** a Monitoring page showing the live `/health` status of `gateway-api`,
`validation-service`, and `reporting-service` **so that** I can see which services are up without
`docker compose logs` or manual `curl`.

Acceptance criteria:
- [ ] `gateway-api` exposes an aggregate endpoint (e.g. `GET /system/health`) that runs its own health
  check plus proxies a call to `validation-service`'s and `reporting-service`'s existing `/health`
  endpoints (internal Compose network calls, reusing `GW-009`'s existing downstream-failure-to-status-code
  handling — no new transport-error-handling pattern invented).
- [ ] `dashboard-web`'s `/monitoring` page renders one row per service: name, status
  (ok/degraded/unreachable) — reusing the existing 502/504-to-`error.html` convention (`DASH-004`'s
  `_render_error_for_status` helper) for the case where the aggregate call itself fails entirely.
- [ ] This reuses `OPS-005`'s existing real dependency-connectivity checks (Postgres/Redis reachability
  per service) rather than re-implementing a second shallow probe.
- [ ] A test mocks `gateway-api`'s aggregate response for all-healthy / one-degraded /
  unreachable-transport cases.

Rationale for priority: Must — the single most basic "don't need `docker compose logs`" ask in the
task, built entirely on health-check work (`OPS-005`) that already exists — the cheapest, highest-value
story in this epic.
Depends on: none (`OPS-005` already shipped)

### SETUP-021 — Recent-errors visibility (in-process ring buffer, not a log aggregator) [Should]

**As** an operator **I want** to see the last N warning/error-level log events from each service on
the Monitoring page **so that** I have some visibility into recent failures without
`docker compose logs`, while explicitly not standing up a log-aggregation backend
(`OPS-007` already declined that as out of scope for now).

Acceptance criteria:
- [ ] Each FastAPI service adds a small in-process `logging.Handler` keeping the last N (e.g. 50)
  `WARNING`+ records in an in-memory ring buffer — the **same** log records `OPS-006`'s existing JSON
  formatter/correlation-id convention already produces, via one additional handler, not a second
  logging system.
- [ ] A new endpoint (e.g. `GET /diagnostics/recent-errors`, operator-authenticated per `SETUP-010`)
  returns the buffer's contents (`timestamp`, `level`, `logger`, `message`, `correlation_id`) — never a
  raw exception traceback containing a request body or secret value, matching the discipline this
  platform already applies to every error message shown to any caller.
- [ ] Explicitly out of scope, stated in this story itself: no persistence across a restart (a real,
  disclosed limitation, same category as `dashboard-web`'s own `SessionStore`), and no cross-service
  log-search/correlation UI beyond "list these N events per service, one column is the correlation id
  you can then grep manually" — a real log-aggregation backend is `OPS-007`'s territory, not this
  story's.
- [ ] `dashboard-web`'s `/monitoring` page renders these events per service, most-recent first.

Rationale for priority: Should — real, asked-for visibility, deliberately built as the cheapest correct
version (an in-memory ring buffer, no new infra dependency) so it can't quietly reopen `OPS-007`'s
already-declined scope.
Depends on: SETUP-010, OPS-006 (already shipped)

### SETUP-022 — Basic operational signal: run throughput and failure rate [Should]

**As** an operator **I want** the Monitoring page to show a simple count of runs submitted and their
status breakdown (completed/failed/running) over a recent window **so that** I have a basic read on
whether the validation pipeline itself is healthy, not just whether each process is up.

Acceptance criteria:
- [ ] Reuses `validation-service`'s/`gateway-api`'s existing `GET /runs` list endpoint (`VS-022`/`GW-016`)
  and its existing `status` field. If that endpoint cannot yet answer "count by status" cheaply, extend
  it minimally (e.g. an optional summary parameter) rather than inventing a new parallel endpoint — DRY
  per implementation-plan.md section 9.
- [ ] The Monitoring page shows: total runs (window), % failed, % completed, % still running —
  labeled explicitly as **"validation-run throughput"**, never as "model performance" or anything
  implying a trading/prediction signal (CLAUDE.md's core positioning constraint: this is operability
  signal about the platform's own pipeline, never a claim about any model's accuracy).
- [ ] No alerting/threshold/paging behavior is added anywhere in this story — this is a number on a
  page, not a trigger for a notification.

Rationale for priority: Should — genuinely useful "is the pipeline healthy" signal, built on data
(`status`) that already exists; the only real risk is mislabeling it as a model-quality metric, which
this story's AC guards against explicitly.
Depends on: SETUP-020

### SETUP-023 — Alerting/paging on monitoring signals [Won't, this backlog]

**As** an operator **I want** alerts/pages when a monitoring signal crosses a threshold.

Rationale: **Won't, this backlog.** `backlog-operability.md`'s `OPS-007` already declined a full
metrics/alerting stack explicitly, and the task brief itself instructs against inventing one unless a
story explicitly earns it — none here does. `SETUP-020`/`021`/`022` are the full, deliberate scope of
this epic. Revisit only if `OPS-007`'s own stated trigger fires (a real incident visibility alone
didn't prevent, or a real pilot client requiring an SLA).
Depends on: none

---

## Epic D — Portability ("run on any computer")

### SETUP-030 — `dashboard-web` added to `docker-compose.yml` as a real service [Must]

**As** a developer running this stack locally **I want** `dashboard-web` to have a working `Dockerfile`
and a `docker-compose.yml` entry connected to `gateway-api` over the internal Compose network **so
that** `docker compose up` runs the entire platform (`postgres`/`redis`/`validation-service`/
`gateway-api`/`reporting-service`/`dashboard-web`) instead of requiring `dashboard-web` to be started
manually outside Compose.

**Explicit disclosure (per ADR-0003 pattern, same category as `INF-018`'s follow-up for
`reporting-service`)**: `dashboard-web` was already built ahead of its own trigger #8 as a disclosed
override (`backlog-infra.md`'s `INF-010` note). `infra/README.md` currently still lists it as "not yet
wired into compose... deliberate, not an oversight" because trigger #8 "hasn't fired" — that wording is
stale in exactly the way `INF-018` found `reporting-service`'s equivalent wording to be stale before
its own Compose-wiring follow-up. This story is that same category of follow-up for `dashboard-web`.

Acceptance criteria:
- [ ] `services/dashboard-web/Dockerfile` exists, builds via its own `pyproject.toml` (`uv`-managed),
  matching the `OPS-004`-verified non-root/port-binding precedent already established for
  `validation-service`/`gateway-api`/`reporting-service`.
- [ ] `infra/docker-compose.yml` defines a `dashboard-web` entry (`build: ../services/dashboard-web`)
  on a documented host port (e.g. `8003`), with `GATEWAY_API_URL` set to the internal Compose hostname
  (`http://gateway-api:8000`), not `localhost`.
- [ ] Port binding: for this local-first phase, bind `127.0.0.1`-only, consistent with the existing
  "`gateway-api` is the only internet-facing service" convention (`dashboard-web` itself never talks
  directly to a database, only to `gateway-api`, so this doesn't change its trust boundary) — **explicitly
  flagged in `infra/README.md` as a decision to revisit** the day a non-localhost operator needs to
  reach this UI directly (e.g. a real remote pilot deployment), since a human operator reaching a UI is
  a different exposure shape than a service-to-service call.
- [ ] `infra/README.md`'s "not yet wired into compose" list is updated to remove `dashboard-web`,
  cross-referencing this story the same way `INF-018`'s section cross-references `RS-GAP`.
- [ ] Full-stack smoke test: `docker compose up` brings up all six services; `dashboard-web`'s own
  `/health` (`DASH-008`) returns `200` reflecting `gateway-api`'s real health, proving Compose-network
  reachability end to end.
- [ ] No change to any file under `services/dashboard-web/src/` beyond what's needed for the
  Dockerfile/env wiring itself — packaging/wiring only, same non-goal `INF-003`/`INF-004`/`INF-018`
  already hold themselves to.

Rationale for priority: Must — the task's own named example of what "not genuinely portable" looks
like today; without this, no other story in this backlog (setup wizard, Settings, Monitoring) can run
inside the one-command golden path at all, since `dashboard-web` isn't even part of `docker compose up`
yet.
Depends on: none

### SETUP-031 — Audit and remove hardcoded/Windows-specific/absolute-path assumptions [Must]

**As** a developer bringing this stack up on a different OS or a machine with no prior local state
**I want** every path/config assumption currently baked into this repo (hardcoded absolute paths,
OneDrive-sync workarounds, a script that only has a Windows or only a POSIX variant) audited and fixed
**so that** the platform doesn't silently work only on the original developer's machine.

Acceptance criteria:
- [ ] A real audit (a checklist with findings, not a re-derivation each time) covers: every literal
  filesystem path, drive letter, or OS-specific assumption across `infra/`, every service's `README.md`,
  and any setup docs — e.g. `dashboard-web`'s already-disclosed OneDrive-sync `.venv`-creation-failure
  workaround (`UV_PROJECT_ENVIRONMENT`), and any script that assumes a specific shell with no
  cross-platform equivalent.
- [ ] Every dual-OS script pair (`infra/bootstrap.sh` vs `.ps1`, `infra/migrate.sh` vs `.ps1`) is
  confirmed to have **real parity** — same steps, same exit codes, same idempotency guarantees — not
  just "a file exists for each OS" with silently drifted behavior; any drift found is fixed as part of
  this story, not merely documented.
- [ ] No script or Dockerfile assumes a specific drive letter, a specific absolute path outside the
  repo, or a specific username/home-directory shape.
- [ ] Findings (what was found, what was fixed, what's an accepted, disclosed limitation — e.g. "OneDrive
  sync can still cause intermittent `.venv` write failures; workaround documented") are written
  into a new "Portability" section of `infra/README.md`, not left scattered across individual service
  READMEs with no single point of reference.

Rationale for priority: Must — this is the literal thing the task calls "audit-by-story the
assumptions that currently tie this to one developer's machine"; without doing the audit as real work,
the "genuinely portable" claim is unverified, not proven.
Depends on: none

### SETUP-032 — Single documented command brings up the full stack on a genuinely fresh machine [Must]

**As** a developer on a machine that has never run this repo before (different OS, no prior Docker
state, no prior `.env`) **I want** `infra/bootstrap.sh`/`.ps1` (post `SETUP-004`/`SETUP-030`) to be the
one documented command that gets me to a working setup wizard **so that** "clone, run one command,
open browser" is a tested claim, not an aspirational one.

Acceptance criteria:
- [ ] This story's own Definition of Done is a real, described dry run on an environment without any of
  this repo's prior state (fresh clone, no cached `.venv`, no already-running containers, no
  pre-existing `.env`) — not a read-through of the script's source alone.
- [ ] No step in the documented golden path requires `docker compose exec ... <script>.py` — the
  wizard (`SETUP-003`/`SETUP-004`) replaces that for first-tenant creation; the CLI scripts remain
  documented as power-user/CI alternatives, not the primary path.
- [ ] `infra/README.md`'s top-level instructions lead with this single command, matching the
  "demote, don't delete" convention that file already follows for its own `INF-015` section.
- [ ] If `infra/.env` is missing, the bootstrap script either creates it from `.env.example` with
  working defaults, or fails loudly with a clear "copy this file first" instruction — never a silent
  "works because a `.env` from three sprints ago happens to already be sitting there" assumption.

Rationale for priority: Must — this is the literal target state named in the task ("the whole stack
coming up via a single documented command on a genuinely fresh machine... with no manual
script-in-container steps required for the golden path").
Depends on: SETUP-004, SETUP-030, SETUP-031

### SETUP-033 — Cross-platform CI smoke test of the bootstrap golden path [Could]

**As** the platform owner **I want** CI (once `OPS-001` exists) to run the bootstrap sequence against
a clean checkout on every push **so that** "genuinely portable" is continuously verified rather than
asserted once and left to drift.

Acceptance criteria:
- [ ] A CI job runs the full bootstrap sequence against ephemeral Compose services and asserts
  `SETUP-001`'s `/setup/status` endpoint is reachable and reports `initialized: false` before any
  tenant is created.
- [ ] Runs on at least a Linux runner (the bash path); a Windows-runner leg for the `.ps1` path is
  explicitly marked optional/best-effort in this story's own AC, since Windows CI runners are
  slower/costlier and `OPS-001` (the CI pipeline itself) hasn't shipped yet.

Rationale for priority: Could — real value (continuous portability verification), but depends on
`OPS-001` existing first, which is itself still open per `backlog-operability.md`; not worth blocking
this backlog's Must scope on a dependency this backlog doesn't control.
Depends on: SETUP-032, OPS-001 (external — not yet shipped)

---

## Summary

| Priority | Count | IDs |
|---|---|---|
| Must | 11 | SETUP-001, 002, 003, 004, 010, 011, 012, 020, 030, 031, 032 |
| Should | 3 | SETUP-015, 021, 022 |
| Could | 1 | SETUP-033 |
| Won't | 3 | SETUP-013, 014, 023 |

Sequencing note for the PM/Tech Lead: `SETUP-030` (dashboard-web in Compose) and `SETUP-010` (operator
auth) are the two real unlocks everything else in Epics A/B/C sits on top of — schedule those two
first, in parallel with each other (they touch different services), then the rest of each epic can
proceed largely independently.
