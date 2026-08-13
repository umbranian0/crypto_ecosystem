# Backlog — gateway-api

Source: `docs/da-tese-ao-produto.md` (section 2.3.6, "bring your own model" / API-SDK framing), `docs/solution-design.md` (section 1 principles, section 3.6 frontend/API/auth design, section 4 data model, section 6 build order), `docs/implementation-plan.md` (sections 2, 4, 5, 6, 7, 9 — module boundary map, trigger table, design patterns, DRY rules), `services/gateway-api/README.md`, `services/validation-service/README.md` + `src/app/routers/runs.py` + `src/app/routers/splits.py` (its real, current endpoint set and tenant-header contract), `libs/common/src/naive_first_common/tenant_context.py` + `libs/common/README.md`, `docs/product/backlog-libs-common.md` (LC-009 entry), `docs/product/backlog-validation-service.md` (SQLite-interim precedent, decision 2), `docs/sprints/sprint-04.md`.

Scope: `services/gateway-api` only — auth (JWT/API keys), the `identity` schema (`tenants`, `users`, `api_keys`), tenant-context resolution and issuance, and HTTP routing/orchestration to `validation-service`'s real endpoints (`POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`). Out of scope, not touched by any story below: the validation algorithm (`libs/naive_first_engine`), `validation-service`'s own schema/business logic (done, not reopened here), dataset storage/upload (`services/ingestion-service`, trigger #6, not fired), report rendering (`services/reporting-service`, trigger #7, not fired), the dashboard UI itself (`services/dashboard-web`, trigger #8, not fired — only its *future* auth consumer is anticipated here), `libs/sdk` (trigger #9, not fired), and any change to `libs/common`'s `get_tenant_context`/`_extract_tenant_id` internals (that is LC-009's own backlog, see decision 3 below).

**Four explicit scope/trigger/dependency decisions made for this backlog** (per the instruction not to assume silently):

1. **Trigger #5 has not actually fired — this backlog exists as an explicit user override, not because the trigger condition is true.** Implementation-plan.md section 6 states trigger #5 fires "as soon as more than one external caller needs access — i.e. the first pilot client." `services/gateway-api/README.md`'s own status line still reads "planned (trigger #5 — create when a second external party needs access, i.e. the first pilot client...)," and `docs/product/backlog-libs-common.md`'s LC-009 entry independently confirms "trigger #5 ... has not fired" as of the last backlog round. No pilot client, letter of intent, or second external caller exists anywhere in this repo's docs (solution-design.md section 7's open question "Pilot client count and expected data volume" is still unresolved). Per this task's explicit instruction, this backlog is written anyway because the instruction-giver asked to move to this module next — the same category of judgment call as `validation-service`'s decision 2 (building against an interim SQLite store ahead of trigger #4 actually firing) and as `libs/common`'s LC-009 note that pulling `gateway-api` forward would itself trigger a follow-up round. Consequence for the stories below: Must-have stories build the auth/routing mechanism and its own tests, but nothing here should be read as "a pilot client now exists" — there is still no real tenant to onboard, and no story authorizes fabricating one as anything other than an internally-provisioned test fixture (see GW-005).
2. **No `infra/docker-compose.yml` + Postgres yet (trigger #4 still not fired), so the `identity` schema starts on an interim SQLite-backed store, mirroring `validation-service`'s VS-004 precedent.** The Repository pattern (implementation-plan.md section 7) is used for exactly the reason `validation-service`'s own README states it: "schema-per-service can later become DB-per-service without touching call sites." Must-have stories (GW-002–GW-005) build `TenantRepository`/`UserRepository`/`ApiKeyRepository` as interfaces with an interim SQLite implementation; the Postgres-backed implementation plus row-level security (solution-design.md section 3.6's "defense in depth") is written as a Should (GW-012), explicitly blocked on the infra trigger, not built now.
3. **Division of labor with `libs/common`'s deferred LC-009, made explicit rather than left to guesswork.** `libs/common/src/naive_first_common/tenant_context.py`'s `get_tenant_context` currently extracts `tenant_id` from a bare, unverified `X-Tenant-Id` request header (interim, LC-003) — anyone who can reach `validation-service` directly can claim any tenant. LC-009 was already scoped (and deferred) in `libs/common`'s own backlog as "gateway-api issues real JWT/API-key-verified TenantContext, swapping validation-service's header-based interim resolver for the real thing." Building real JWT/API-key auth inside `gateway-api` now does **not** duplicate LC-009 and does **not** require reopening it: this backlog's boundary is —
   - `gateway-api` **owns**: the `identity` schema, issuing and verifying JWTs/API keys, resolving a caller's *verified* `TenantContext` at the edge, and forwarding it downstream. The forwarding mechanism deliberately reuses `validation-service`'s **existing, already-shipped** contract — the `X-Tenant-Id` header — so no line of `validation-service` code changes as part of this backlog (GW-007's acceptance criteria say so explicitly).
   - `libs/common`'s LC-009 (still Won't/deferred, not reopened here) **owns**: changing `_extract_tenant_id`'s internals so a downstream service like `validation-service` stops *trusting* a bare header from any caller and starts requiring proof the header was set by `gateway-api` specifically (e.g. a signed internal token, mTLS, or network-topology enforcement once `infra/docker-compose.yml` exists to define a private network). That hardening step is written below as GW-015, explicitly **Won't (this backlog)**, to keep the boundary visible rather than silently assumed — flagged for the PM/Tech Lead to sequence as the LC-009 follow-up round `libs/common`'s own backlog already anticipated.
4. **JWT session auth is scoped Should, not Must, because its only named consumer (`dashboard-web`) doesn't exist yet (trigger #8, not fired) and `libs/sdk` doesn't either (trigger #9, not fired).** API-key auth is scoped Must because it is the mechanism solution-design.md section 3.6 names for "programmatic access" — the closer match to how a first pilot client (or, in the interim, an internally-provisioned test client) would actually call the platform "bring your own model"-style, and the mechanism the routing/orchestration stories (GW-007–GW-009) need to exist to be exercised end-to-end at all. This mirrors the same "build what today's one real caller needs, defer the rest behind the same interface" logic used throughout `validation-service`'s backlog.

## Stories

### GW-001 — Service scaffolding [Must]
**As a** Tech Lead standing up `gateway-api` **I want** a proper `uv`-managed FastAPI service skeleton (routers, dependencies, repositories packages, matching the layout implementation-plan.md section 3 implies for every service) **so that** every other story in this backlog has a place to live and a working test runner from day one.

Acceptance criteria:
- [ ] `services/gateway-api/pyproject.toml` exists, declares the FastAPI app, depends on `naive_first_common` (path/workspace dependency) — not on `naive_first_engine` (this service never touches the validation algorithm directly).
- [ ] `src/app/` skeleton exists (`routers/`, `dependencies/`, `repositories/` packages).
- [ ] `tests/` exists with a working `pytest` config; `uv run pytest` passes with zero tests collected as a baseline.
- [ ] `services/gateway-api/README.md`'s status line is updated from "planned" to "scaffolded," and its opening line is updated to note this backlog was built ahead of trigger #5 actually firing, per decision 1 above — so a future reader doesn't mistake this for "a pilot client exists."

Rationale for priority: nothing else in this backlog can be built or tested without a package/app skeleton to put it in.
Depends on: none

### GW-002 — `identity` schema definition (`tenants`, `users`, `api_keys`) [Must]
**As** `gateway-api` **I want** typed schema definitions for `tenants`, `users`, and `api_keys` matching solution-design.md section 4 field-for-field **so that** the service's own data model is correct and tenant-scoped from the first commit, independent of whether the Postgres-backed implementation (GW-012) exists yet.

Acceptance criteria:
- [ ] `tenants(id, name, created_at)`, `users(id, tenant_id, email, role, ...)`, `api_keys(id, tenant_id, key_hash, created_at, revoked_at)` are defined as typed models (ORM or dataclass, per whatever GW-004 needs), matching solution-design.md section 4.
- [ ] `users` and `api_keys` carry `tenant_id` — no row in either table is created without one, matching solution-design.md section 1 principle 3.
- [ ] `api_keys` stores only `key_hash`, never the raw key — the raw key is returned exactly once, at creation time (GW-005), and is unrecoverable afterward.
- [ ] The schema is defined once and reused by both the interim SQLite (GW-004) and future Postgres-backed (GW-012) implementations — no duplicate model definitions per backend.
- [ ] Migration source (e.g. Alembic revision files) exists under this service's own migration path even though it isn't run against a live Postgres yet, so GW-012 is "point Alembic at a real DB," not "write the migration."

Rationale for priority: every other identity story (repositories, provisioning, auth) needs an agreed shape for `tenants`/`users`/`api_keys` first — this is the `identity` schema named in this service's own "owns" boundary, made concrete.
Depends on: GW-001

### GW-003 — Identity repository interfaces (`TenantRepository`, `UserRepository`, `ApiKeyRepository`) [Must]
**As** `gateway-api` **I want** the three repositories implied by GW-002's schema defined as typed interfaces, not tied to any storage backend **so that** business logic (auth, provisioning, routing) never talks to storage directly, and the interim-to-Postgres swap (decision 2) is a new implementation class, not a rewrite of call sites — the same binding decision `validation-service`'s VS-003 made for its own repositories.

Acceptance criteria:
- [ ] Interfaces declared as `typing.Protocol` (no ABC, matching VS-003's own precedent unless a concrete reason to diverge surfaces), each method's first parameter after `self` is `tenant_id` where applicable (all `users`/`api_keys` operations; `tenants` creation is the one exception since a tenant doesn't yet have an id to scope by).
- [ ] Method sets cover at minimum: `TenantRepository.create_tenant(name) -> TenantRecord`, `get_tenant(tenant_id) -> TenantRecord | None`; `ApiKeyRepository.create_key(tenant_id, key_hash) -> ApiKeyRecord`, `get_by_hash(key_hash) -> ApiKeyRecord | None`, `revoke_key(tenant_id, key_id) -> None`; `UserRepository.create_user(tenant_id, email, role) -> UserRecord`, `get_user_by_email(email) -> UserRecord | None`.
- [ ] Interfaces return/accept plain `@dataclass(frozen=True)` record types, not SQLAlchemy models directly — `interfaces.py` stays free of any `sqlalchemy` import, mechanically checked by a test mirroring `validation-service`'s `test_repository_interfaces.py`.
- [ ] DI seam: `src/app/dependencies/repositories.py` declares provider stubs plus `Annotated[..., Depends(...)]` aliases for route handlers.

Rationale for priority: same reasoning as VS-003 — this is the extension point every downstream Must (GW-004–GW-009) is written against; getting it wrong here means rewriting call sites later.
Depends on: GW-002

### GW-004 — SQLite-backed repository implementation (interim) [Must]
**As** `gateway-api` **I want** concrete `SQLite*Repository` implementations of GW-003's interfaces, backed by a file-based SQLite database (path from an env var, defaulting to `./gateway.db`, mirroring `VALIDATION_SERVICE_DB_PATH`'s precedent) **so that** identity state survives a process restart without waiting on trigger #4 (`infra/docker-compose.yml` + Postgres) to fire.

Acceptance criteria:
- [ ] `src/app/repositories/sqlite_repository.py` implements all three interfaces from GW-003.
- [ ] Only `src/app/dependencies/repositories.py` imports `sqlite_repository` directly; route/business-logic code depends on the interfaces only.
- [ ] `services/gateway-api/README.md` states plainly (mirroring `validation-service`'s README wording) that this is a deliberately interim storage backend, not the final design, and names GW-012 as its Postgres-backed replacement behind the same DI seam.
- [ ] `key_hash` lookups (`get_by_hash`) are covered by a test proving a revoked key's hash still resolves to a record with `revoked_at` set (revocation is a flag, not a delete — GW-010 needs this).

Rationale for priority: nothing above the storage layer (provisioning, auth) is testable end-to-end without a concrete repository — same "interim now, Postgres later, purely a DI swap" logic as `validation-service`'s decision 2.
Depends on: GW-003

### GW-005 — Tenant + API-key provisioning (operator-facing) [Must]
**As an** operator running this platform pre-pilot **I want** a way to create a tenant and issue it an API key **so that** the auth and routing stories below (GW-006–GW-009) have something real to authenticate against, given no self-serve signup flow exists or is justified yet (no real pilot client — decision 1).

Acceptance criteria:
- [ ] A provisioning path exists (CLI script or an operator-only endpoint gated separately from tenant-facing auth — implementer's choice, documented in the README) that creates a `tenants` row and one `api_keys` row for it, returning the raw (unhashed) key exactly once.
- [ ] The raw key is never logged, persisted, or returned again after creation — only `key_hash` is stored (GW-002).
- [ ] This path is explicitly documented as an operator/test-fixture tool, not a public "sign up" flow — the README states this so a future contributor doesn't mistake it for pilot-facing self-service (which would misrepresent decision 1's "no real pilot exists yet").

Rationale for priority: without this, GW-006 (API-key auth) and everything downstream of it has no valid key to test against — this is the fixture-creation step decision 1 flags as necessary despite there being no real tenant yet.
Depends on: GW-004

### GW-006 — API-key authentication [Must]
**As** `gateway-api` **I want** to verify an `Authorization`/`X-Api-Key`-supplied key against `api_keys.key_hash` before any routed request proceeds **so that** tenant identity is cryptographically authenticated at the edge, not merely asserted — the exact gap LC-009's rationale names as the reason header-based trust downstream isn't the final design.

Acceptance criteria:
- [ ] A missing, malformed, unknown, or revoked (`revoked_at IS NOT NULL`) API key returns `401` before any downstream routing call is made.
- [ ] A valid key resolves to a `TenantContext`-equivalent value carrying the key's `tenant_id`, available to GW-007.
- [ ] Key comparison is done against the stored hash (never a plaintext comparison, never logging the presented key).
- [ ] Test coverage includes: valid key succeeds; revoked key is rejected; key from tenant A cannot be used to access tenant B's resources (proven at the routing layer, GW-008, not just here).

Rationale for priority: this is the literal auth mechanism named in this service's "owns" boundary and solution-design.md section 3.6 ("API keys for programmatic access") — nothing routes safely without it.
Depends on: GW-005

### GW-007 — Verified `TenantContext` resolution + downstream forwarding [Must]
**As** `gateway-api` **I want** the tenant identity resolved by GW-006 to be forwarded to internal services using their existing, already-shipped `X-Tenant-Id` header contract **so that** `validation-service` (and any future internal service using `naive_first_common.get_tenant_context`) requires zero code changes to consume gateway-verified identity — matching decision 3's division of labor with LC-009.

Acceptance criteria:
- [ ] Every routed downstream HTTP call (GW-008) carries `X-Tenant-Id` set to the *verified* tenant_id from GW-006 — never a client-supplied value, never trusted from the inbound request's own headers.
- [ ] This story makes **no change** to `libs/common/src/naive_first_common/tenant_context.py` or to any `validation-service` file — verified explicitly by a test/CI check that the diff touches only `services/gateway-api/`.
- [ ] `services/gateway-api/README.md`'s design notes are updated to state plainly that this is an interim forwarding mechanism relying on network topology (internal services not being reachable except through `gateway-api`) rather than a cryptographically verified internal channel, and that hardening that boundary is LC-009's/GW-015's job, not this story's.
- [ ] Resolution happens once per request and is injected via FastAPI `Depends()` into every downstream call, per this service's own README design note and implementation-plan.md section 7's DI pattern.

Rationale for priority: this is the literal seam the README's design notes already commit to ("Tenant context is resolved once per request and injected via `Depends()`") — without it GW-008's routing has no verified identity to forward.
Depends on: GW-006

### GW-008 — Request routing to `validation-service`'s real endpoints [Must]
**As a** pilot client (or, pre-pilot, an internally-provisioned test client) **I want** to call `gateway-api` and have it transparently proxy to `validation-service`'s actual contract **so that** I have one stable, internet-facing API surface regardless of how many internal services exist behind it.

Acceptance criteria:
- [ ] `gateway-api` exposes `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits` with request/response shapes matching `validation-service`'s current, real `RunRequest`/`RunResponse`/`RunDetailResponse`/`SplitResultResponse` models (`src/app/routers/runs.py`, `src/app/routers/splits.py`) exactly — not a guessed or aspirational shape.
- [ ] No business logic is reimplemented here (matching this service's "does not own any business logic" boundary) — the handler's only job is: resolve verified tenant (GW-007), forward the request body/path params to `validation-service` over `httpx`, forward the response back unmodified.
- [ ] Cross-tenant access is proven impossible at this layer by a test: a request authenticated as tenant A for a `run_id` belonging to tenant B gets the same `404` `validation-service` already returns (GW-007 forwards the correct header; this story does not add or remove any tenant-isolation branching — that logic stays in `validation-service`, per DRY across service boundaries, implementation-plan.md section 9).
- [ ] `validation-service`'s hostname/port is configured via env var (e.g. `VALIDATION_SERVICE_URL`), not hardcoded — matches the Docker-network hostname pattern implementation-plan.md section 4 describes (`http://validation-service:8000/...`) without requiring `infra/docker-compose.yml` to exist yet for local dev (defaults to `localhost` equivalent).

Rationale for priority: this is the literal reason `gateway-api` exists per its own README ("request routing to internal services over HTTP") and the concrete trigger-#5 justification ("more than one external caller needs access") — without it, auth (GW-006/007) has nothing to protect.
Depends on: GW-007

### GW-009 — Downstream failure handling (timeouts, connection errors) [Must]
**As a** caller of `gateway-api` **I want** a clear, non-leaking error when `validation-service` is unreachable or times out **so that** a downstream outage doesn't surface as a confusing `500` or an indefinitely hanging request.

Acceptance criteria:
- [ ] A connection failure to `validation-service` returns `502` with a generic body (no internal hostnames/stack traces leaked to the client).
- [ ] A request that exceeds a configured timeout (env var, sane default) returns `504`.
- [ ] `validation-service`'s own `201`-with-`status:"failed"` response (its documented failure-handling contract, VS-012) is passed through unmodified — this story does not reinterpret a *validation run* failure as a *gateway* failure; those are different failure modes and must stay distinguishable to the caller.
- [ ] Test coverage: simulated downstream timeout → `504`; simulated downstream connection refused → `502`; simulated downstream `201`/`status:"failed"` → passed through as-is.

Rationale for priority: `validation-service`'s `POST /runs` is synchronous and can hold a connection open for a full run duration (per its own README) — a proxy in front of it without timeout/error handling turns a slow run into a gateway-level failure mode nobody designed for.
Depends on: GW-008

### GW-016 — Proxy route for validation-service's `GET /runs` list endpoint [Must]
**As a** pilot client (or, pre-pilot, `dashboard-web`/an internally-provisioned test client) **I want** `gateway-api` to proxy `validation-service`'s new tenant-scoped `GET /runs` list endpoint (VS-022) **so that** `dashboard-web`'s `DASH-005` runs-list page — and any future caller needing to enumerate runs — has a real endpoint to call through this platform's one public-facing surface, matching GW-008's already-established routing pattern exactly.

Acceptance criteria:
- [ ] `gateway-api` exposes `GET /runs` (query params `limit`/`offset` forwarded unmodified) with request/response shapes matching `validation-service`'s real `GET /runs` (VS-022, `docs/product/backlog-validation-service.md`) exactly — reusing the same `RunSummaryResponse` list-envelope model from `naive_first_common.contracts` VS-022 adds there, not a locally redefined shape (same DRY precedent GW-008/ARCH-003 already established for `RunDetailResponse`/`SplitResultResponse`).
- [ ] Handler body does nothing but: resolve verified tenant (GW-006/GW-007) → forward `limit`/`offset` + the verified `X-Tenant-Id` header via `httpx` to `VALIDATION_SERVICE_URL` → return the response unmodified — no new business logic, no pagination/ordering reimplemented at this layer (matches GW-008's "does not own any business logic" boundary).
- [ ] Cross-tenant isolation is proven the same way GW-008 already proves it for `GET /runs/{id}`: a request authenticated as tenant A returns only tenant A's runs — no branch/filter is added in this router beyond forwarding the verified tenant header; the isolation guarantee comes entirely from `validation-service`'s own tenant-scoped `list_runs` (VS-022).
- [ ] GW-009's existing timeout/connection-failure handling (`502`/`504`) applies to this new route with no special-casing — reuses the same downstream-failure dependency already wired for `POST /runs`/`GET /runs/{id}`/`GET /runs/{id}/splits`, not a new error-handling path.
- [ ] Tests (mirroring `tests/test_runs_routing.py`'s existing `httpx.MockTransport` approach): forwards correctly and returns validation-service's response shape unmodified; `limit`/`offset` pass through; tenant A's authenticated request never sees tenant B's runs (seeded into the mock backend, same non-tautological pattern GW-008's own cross-tenant test already uses); a downstream `422` (bad `limit`) passes through unmodified.
- [ ] `services/gateway-api/README.md`'s Contract section documents this fourth proxied endpoint alongside the existing three, cross-referencing `DASH-005`/`DASH-005-GAP` as the reason it exists.

Rationale for priority: Must — this is the second, symmetric half of closing `DASH-005-GAP` (VS-022 is the first); without both, `dashboard-web`'s own Must-priority `DASH-005` story stays blocked and `DASH-009`'s E2E suite keeps relying on its documented redirect-id fallback instead of exercising the real list page. Matches this service's stated "owns: ... HTTP routing/orchestration to validation-service's real endpoints" boundary, extended by the one endpoint VS-022 adds.
Depends on: VS-022 (validation-service must expose the real endpoint before this proxy has anything to forward to), GW-007 (verified tenant forwarding), GW-009 (failure handling)

### GW-010 — API-key revocation [Should]
**As a** tenant admin (or operator, pre-self-service) **I want** to revoke an API key **so that** a leaked or rotated key stops working immediately without needing to delete/recreate the tenant.

Acceptance criteria:
- [ ] An endpoint or operator path sets `api_keys.revoked_at`, using GW-004's already-tested revocation semantics.
- [ ] A revoked key fails GW-006's auth check on the very next request (no caching window that would keep a revoked key valid).

Rationale for priority: important operational hygiene, but not required to prove the core auth/routing path works end-to-end for the first (still-hypothetical) pilot client — deferred behind the Musts above.
Depends on: GW-006

### GW-011 — JWT-based session auth [Should]
**As a** future `dashboard-web` (trigger #8, not fired) **I want** `gateway-api` to issue and verify JWT sessions carrying `tenant_id` (per solution-design.md section 3.6) **so that** a logged-in dashboard user's requests are tenant-scoped the same way API-key requests are.

Acceptance criteria:
- [ ] A login endpoint accepts `email`/credential and returns a signed JWT embedding `tenant_id` and `user_id`, matching solution-design.md section 3.6.
- [ ] JWT verification resolves to the same internal `TenantContext`-equivalent shape GW-006/GW-007 use, so GW-008's routing logic doesn't need two separate code paths for "authenticated via API key" vs. "authenticated via JWT" beyond the initial verification step.
- [ ] No password-storage/credential-management scheme is invented beyond what's needed to issue a session — this story does not scope a full user-management product, only the token mechanics named in the "owns" boundary.

Rationale for priority: named in this service's "owns" boundary and solution-design.md section 3.6, but its only real consumer (`dashboard-web`) doesn't exist yet (trigger #8, not fired) and `libs/sdk` doesn't either (trigger #9) — API-key auth (GW-006, Must) is the mechanism with an actual near-term caller. Build the mechanism now since it's cheap alongside GW-006's shared verification shape, but don't gate anything on it.
Depends on: GW-007

### GW-012 — Postgres-backed identity repository + row-level security [Should]
**As** `gateway-api` **I want** `TenantRepository`/`UserRepository`/`ApiKeyRepository` implemented against Postgres with row-level security policies (solution-design.md section 3.6's "defense in depth, cheap to add now") **so that** identity data gets the same durability and isolation guarantees solution-design.md specifies, once there's a real Postgres instance to target.

Acceptance criteria:
- [ ] New implementation classes behind GW-003's existing interfaces — no call-site changes anywhere else in the service (proving out decision 2's Repository-swap precedent).
- [ ] RLS policies scope every query to `tenant_id`, matching solution-design.md section 3.2's stated multi-tenancy model.
- [ ] GW-002's Alembic migrations (written against the schema, not yet run) are pointed at the real database as part of this story.

Rationale for priority: explicitly blocked on `infra/docker-compose.yml` + Postgres actually existing (trigger #4, not fired) — same status as `validation-service`'s own VS-013. Not build-able correctly until that trigger fires; scoped now so the interface (GW-003) already anticipates it.
Depends on: GW-004; blocked on infra trigger #4 (not fired)

### GW-013 — Rate limiting / abuse protection [Could]
**As** the operator of the only internet-facing service in this platform **I want** basic per-key or per-tenant rate limiting on routed requests **so that** a single misbehaving or compromised caller can't degrade the platform for everyone else.

Acceptance criteria:
- [ ] A configurable per-key request-rate ceiling returns `429` once exceeded.
- [ ] Rate-limit state does not require a new infra piece beyond what's already planned (e.g. in-process/interim counter now, Redis-backed later alongside Redis Streams' eventual arrival at trigger #7) — same "interim now, real infra later" logic as the rest of this backlog.

Rationale for priority: sensible hardening for an internet-facing surface, but with zero real external traffic yet (decision 1), there is no observed abuse pattern to defend against — build once a real caller exists to justify the complexity.
Depends on: GW-008

### GW-014 — Auth event audit logging [Could]
**As** an operator preparing for the first real pilot/compliance conversation **I want** auth events (key issued, key revoked, failed auth attempts) logged **so that** there's a record to point to when a client or auditor asks "who could access this."

Acceptance criteria:
- [ ] Key issuance, revocation, and failed-auth attempts are logged with tenant_id, timestamp, and outcome — no raw keys or secrets in the log line.
- [ ] Logging uses whatever structured-logging convention the rest of the platform already uses (matching `validation-service`'s `InProcessLogEventPublisher` precedent for "structured line, interim, not yet durable/shipped anywhere").

Rationale for priority: valuable for the eventual audit/compliance positioning (da-tese-ao-produto.md section 2.3.4/2.4) but not required for the core auth/routing path to function or be tested — genuinely nice-to-have at this stage, no real pilot or auditor is asking for it yet.
Depends on: GW-006

### GW-015 — Signed/verified internal tenant-identity propagation (LC-009 hardening handoff) [Won't (this backlog)]
**As** `validation-service` (or any future internal service) **I want** to require cryptographic proof that an `X-Tenant-Id` header actually came from `gateway-api`, not just trust it because it's present **so that** the header-forwarding interim built in GW-007 stops being a spoofable trust-by-network-topology assumption.

Acceptance criteria: none — not built in this backlog.

Rationale for priority: this is explicitly `libs/common`'s LC-009 concern per `docs/product/backlog-libs-common.md`'s own LC-009 entry ("gateway-api issues real JWT/API-key-verified TenantContext, swapping validation-service's header-based interim resolver for the real thing") — the *swap* of `_extract_tenant_id`'s internals belongs to that backlog, not this one (decision 3). Building it here would mean editing `libs/common`/`validation-service` files this backlog's own GW-007 acceptance criteria explicitly forbid touching. Flagged here, not silently omitted, so the boundary between "gateway-api issues verified identity" (done in this backlog, GW-006/007) and "internal services stop trusting an unsigned header" (not done here) stays visible to whoever picks up the LC-009 follow-up round `libs/common`'s backlog already anticipated.
Depends on: `libs/common`'s LC-009 (deferred there, not reopened here); also practically wants `infra/docker-compose.yml` (trigger #4, not fired) to exist so a private network / shared-secret channel has somewhere real to live.

### GW-017 — Locust load-test suite against key endpoints [Should]
As a Tech Lead wanting visibility into this platform's behavior under load, I want a Locust-based load-test suite driving gateway-api's key endpoints (auth, POST /runs, GET /runs/{id}, GET /runs/{id}/splits) against a real running Compose stack, so that request latency/throughput/error-rate behavior under concurrent load is observable before a real pilot client generates it for the first time.

No formal trigger from implementation-plan.md authorizes this (there is no pilot-scale load yet, no observed performance problem) — added at explicit user request, same disclosed-override treatment as this platform's other trigger overrides (dashboard-web's own trigger-#8 override, `docs/product/backlog-dashboard-web.md`).

Acceptance criteria:
- [ ] `services/gateway-api/loadtest/locustfile.py` (or equivalent) defines Locust user tasks covering: authenticated GET /runs/{id}, GET /runs/{id}/splits, POST /runs (against a seeded/interim dataset reference so runs actually execute), and at least one deliberately-invalid-auth request path (to observe 401 behavior under load, not just happy-path).
- [ ] README section (or `loadtest/README.md`) documents how to run it against the real `infra/docker-compose.yml` stack (host/port, how to provision a test tenant/API key first via GW-005's script, recommended user-count/spawn-rate starting points).
- [ ] No hard performance SLA/threshold is asserted or gated on — this is observability/instrumentation tooling, not a pass/fail gate; the suite's job is to produce Locust's own request-stats output for a human to read, not to fail CI on a number nobody has committed to yet.
- [ ] POST /runs's own synchronous, potentially-long-running execution (validation-service's documented behavior, VS-006) is called out explicitly in the README as a known factor affecting this specific endpoint's load-test numbers differently from the two GET endpoints — not silently averaged together as if all three had equivalent latency profiles.
- [ ] Cross-referenced (one line, not duplicated) from `docs/product/backlog-validation-service.md`'s own text, noting that `POST /runs`'s real compute cost is validation-service's, even though the load is driven through gateway-api as the public entry point.

Rationale for priority: valuable tooling to have available ahead of the first real pilot's traffic pattern, but nothing in flight depends on it and no trigger from implementation-plan.md fires it yet — Should, not Must.
Depends on: GW-008, GW-009 (the routing/failure-handling paths being load-tested)

### GW-018 — Proxy routes for reporting-service's `POST /reports/generate` and `GET /reports/{id}` [Must]
**As a** pilot client (or, pre-pilot, an internally-provisioned test client) needing to trigger and retrieve audit reports **I want** `gateway-api` to proxy `reporting-service`'s two endpoints (`POST /reports/generate`, `GET /reports/{id}`, per `docs/product/backlog-reporting-service.md`'s RS-004/RS-005) **so that** a client can reach `reporting-service` through this platform's one public-facing surface at all — today it is unreachable from outside the Docker network regardless of whether it's running, exactly the gap `reporting-service`'s own backlog flags as `RS-GAP` and explicitly declines to fix itself (RS-106, "this module owns no other service's routing").

Acceptance criteria:
- [ ] `gateway-api` exposes `POST /reports/generate` (body: `run_id`) and `GET /reports/{id}` with request/response shapes matching `reporting-service`'s real `RS-004`/`RS-005` contract exactly (`{id, status}` on generate per RS-004's `201`; `{id, run_id, report_kind, generated_at, status, content}` on retrieval per RS-005's `200`) — read from `reporting-service`'s actual router code once built, not guessed, same discipline GW-008's own ticket applied to `validation-service`'s real models.
- [ ] Handler bodies do nothing but: resolve verified tenant (GW-006/GW-007) → forward the request body/path param + verified `X-Tenant-Id` header via `httpx` to a new `REPORTING_SERVICE_URL` env var (same pattern as `VALIDATION_SERVICE_URL`, not hardcoded, defaulting to a `localhost` equivalent for non-Compose local dev) → return the response unmodified — no report-rendering or generation logic reimplemented here (matches this service's "does not own any business logic" boundary).
- [ ] Cross-tenant access to a report is proven impossible at this layer the same way GW-008 proves it for runs: a request authenticated as tenant A for a `report_id` belonging to tenant B gets the same `404` `reporting-service`'s own RS-005 already returns (this router adds no new isolation branching — that logic stays in `reporting-service`, per DRY across service boundaries, implementation-plan.md section 9).
- [ ] GW-009's existing timeout/connection-failure handling (`502`/`504`) applies to both new routes with no special-casing — reused, not reimplemented.
- [ ] Tests (`httpx.MockTransport`, mirroring `test_runs_routing.py`): both routes forward correctly and return `reporting-service`'s response shape unmodified; cross-tenant `404` proof; a `reporting-service` connection failure/timeout returns `502`/`504`.
- [ ] `services/gateway-api/README.md`'s Contract section documents both new proxied endpoints and the `REPORTING_SERVICE_URL` env var, cross-referencing `RS-GAP` as the reason they exist.

Rationale for priority: Must — without this, `reporting-service`'s already-built `POST /reports/generate`/`GET /reports/{id}` (RS-004/RS-005) are unreachable through the platform's one public-facing surface, leaving the whole reporting PoC unusable end-to-end even once it's wired into Compose (INF-018). Paired with INF-018 as the two prerequisites `RS-GAP` names explicitly.
Depends on: `reporting-service`'s RS-004/RS-005 existing as real, running routes (that module's own backlog, not built by this story), GW-007, GW-009; practically also wants INF-018 (compose wiring) to be testable against a real running `reporting-service`, though this story's own mocked-transport tests don't strictly require it
