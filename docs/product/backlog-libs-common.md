# Backlog — libs/common

Source: `docs/da-tese-ao-produto.md` (section 2.1 positioning, section 2.7 ethical boundaries), `docs/solution-design.md` (section 1 principle 3 — tenant isolation first-class from day one; section 3.6 auth/multi-tenancy discussion), `docs/implementation-plan.md` (section 2 module boundary map, section 6 trigger table — trigger #2, section 7 Dependency Injection pattern, section 9 DRY/lib-ownership rules), `libs/common/README.md` (owns/does-not-own/contract), `docs/product/backlog-validation-service.md` (decision 1 and VS-010's own acceptance criteria — the concrete blocked consumer this backlog exists to unblock).

Scope: `libs/common` only. Trigger #2 (implementation-plan.md section 6: "as soon as a second module needs to share a data shape — right when validation-service is scaffolded") has fired — concretely, because `services/validation-service`'s VS-010 ("Tenant context resolution") is explicitly blocked waiting for this library to exist, per Sprint 03's ticket index and backlog-validation-service.md decision 1. This backlog's job is to unblock VS-010 with the smallest real thing that does so honestly — not to pre-build the rest of `libs/common`'s README-stated ownership ("owns" is a ceiling on what may eventually live here, not a floor of what must ship now). Out of scope, not touched by any Must/Should story below: shared Pydantic schemas for cross-service payloads, DB session helpers, and common formatting logic — see the Won't stories and the scope decision below for why each is deliberately deferred rather than silently dropped.

**Scope decision (stated explicitly, per instruction not to assume silently):**

`libs/common`'s Must-have scope in this backlog is **only** a minimal tenant-context module: a FastAPI `Depends()`-based dependency that resolves `tenant_id` from an explicit, already-present request field (mirroring the interim `tenant_id` field `validation-service`'s VS-006 already accepts) and fails closed when it's absent — **not** a JWT/API-key authentication system. Reasoning:

1. **`validation-service` is the only real consumer today**, and VS-010's own acceptance criteria (backlog-validation-service.md) ask for exactly this: "Route handlers resolve `tenant_id` via a FastAPI `Depends()` provided by `naive_first_common`'s tenant-context module, replacing the interim explicit `tenant_id` request field." VS-010 does not ask for JWT parsing or API-key lookup — it asks for the *shape* (a DI-resolvable tenant context) to move out of the service and into the lib, so it isn't hand-rolled per-service and doesn't diverge later.
2. **`gateway-api` does not exist yet** (implementation-plan.md trigger #5: "as soon as more than one external caller needs access — i.e. the first pilot client" — not fired). Per solution-design.md section 3.6, JWT sessions and API keys are `gateway-api`'s concern, verified at the edge and embedded with `tenant_id` before any internal service sees the request. Building JWT/API-key verification into `libs/common` now would mean inventing an auth boundary with no real caller and no real edge service to issue/verify tokens against — exactly the kind of speculative build implementation-plan.md's trigger-based ordering exists to prevent.
3. **This matches solution-design.md's own multi-tenancy model for the current phase**: "pool" multi-tenancy with `tenant_id` as an explicit field, upgraded to resolved-from-auth-context only once `gateway-api`'s auth layer exists. A minimal tenant-context module that resolves an explicit field is the correct-for-now implementation of that same model — moved to a shared lib so `validation-service` isn't the one hand-rolling it, per implementation-plan.md section 9's DRY rule.
4. **Everything else in the README's "owns" list is explicitly deferred**, per the README's own YAGNI clause ("don't move things here in case another service needs them later ... move on second real use") — see LC-006/007/008 below. None of shared cross-service Pydantic schemas, DB session helpers, or formatting logic has a second real consumer yet: `validation-service` built its own interim SQLite repository (VS-004) rather than a shared DB session helper, and neither `dashboard-web` nor `reporting-service` (the two named consumers of shared formatting logic) has been scaffolded (triggers #7, #8 not fired).

Flagged for PM/Tech Lead review: if `gateway-api` scaffolding (trigger #5) is pulled forward before a second `libs/common` consumer materializes for schemas/DB helpers/formatting, this backlog will need a follow-up round for real JWT/API-key resolution (see LC-009) — that is a new backlog addition, not a reopening of the stories below.

## Stories

### LC-001 — Package scaffolding [Must]
**As a** Tech Lead standing up the second library in the build order **I want** a proper `uv`-managed Python package skeleton for `libs/common` (`naive_first_common`) **so that** the tenant-context module in this backlog, and anything added to this lib later, has a place to live and a working test runner from day one.

Acceptance criteria:
- [ ] `libs/common/pyproject.toml` exists, declares `naive_first_common` as a plain-Python package with Pydantic as its only external dependency (per the README's contract: "plain typed Python, no framework lock-in beyond Pydantic"; FastAPI itself stays a dev/test dependency only, since the lib exposes a `Depends()`-compatible callable, not a FastAPI app).
- [ ] `src/naive_first_common/` skeleton exists matching implementation-plan.md section 3's layout (`libs/common/src/naive_first_common/`).
- [ ] `tests/` exists with a working `pytest` config; `uv run pytest` passes with zero tests collected as a baseline.
- [ ] `libs/common/README.md`'s status line is updated from "planned" to "scaffolded" once this merges, per implementation-plan.md section 8's documentation convention.
- [ ] `services/validation-service/pyproject.toml` is **not** modified by this story — wiring the dependency in is VS-010's job (in the validation-service backlog), not this one's, keeping the two backlogs independently shippable.

Rationale for priority: nothing else in this backlog can be built or tested without a package skeleton to put it in — literal first step, same precedent as LC-equivalent NFE-001/VS-001 in the other two backlogs.
Depends on: none

### LC-002 — `TenantContext` typed value object [Must]
**As** `validation-service` (and any future service importing this lib) **I want** a single, typed `TenantContext` shape owned by `libs/common` **so that** every service that resolves a tenant agrees on the same shape instead of each inventing its own.

Acceptance criteria:
- [ ] A `TenantContext` type (Pydantic model or frozen dataclass) is defined with, at minimum, a required non-empty `tenant_id: str` field.
- [ ] The type is exported from `naive_first_common`'s public API (importable as `from naive_first_common import TenantContext`, matching the README's "plain typed Python" contract).
- [ ] Unit tests confirm construction rejects an empty/missing `tenant_id` (fails closed at the type level, not just at the dependency level in LC-003).
- [ ] No service-specific fields are added (no `dataset_id`, no validation-service-specific concept) — this type is shared-boundary-only, matching the README's "does not own any service-specific business logic."

Rationale for priority: LC-003's `Depends()` resolver needs a return type to resolve *to*; defining the shape first keeps the resolver's job narrow (extract + validate → construct), matching this module's "owns... tenant context" boundary exactly, nothing more.
Depends on: LC-001

### LC-003 — FastAPI `Depends()`-based tenant context resolver (interim: explicit-field extraction) [Must]
**As** `validation-service` **I want** a FastAPI dependency function that resolves the current request's `TenantContext` from an explicit, already-present request field **so that** VS-010 can replace its interim hand-rolled `tenant_id` field with an import from this lib, per implementation-plan.md section 9's rule that shared logic belongs in a lib once a second consumer needs it.

Acceptance criteria:
- [ ] A callable (e.g. `get_tenant_context`) exists, usable as `tenant: TenantContext = Depends(get_tenant_context)` in any FastAPI route handler, matching implementation-plan.md section 7's named Dependency Injection pattern.
- [ ] The interim resolution strategy extracts `tenant_id` from an explicit source already present on the request (e.g. an `X-Tenant-Id` header, or a request-body/query field the caller documents) — no JWT decoding, no API-key lookup, no network/DB call, per the scope decision above.
- [ ] The resolution strategy is a single, swappable point (e.g. one small internal function or a constructor parameter) so that swapping it for `gateway-api`-issued-context resolution later (LC-009, deferred) is a new implementation behind the same `Depends()` signature, not a rewrite of every call site — mirrors the Repository-swap precedent already used in `validation-service`'s own backlog (decision 2).
- [ ] Missing or empty `tenant_id` raises an HTTP 400/401 (not a 500, not a silently-empty `TenantContext`) before any route handler body runs.

Rationale for priority: this is the literal thing VS-010 is blocked on — implementation-plan.md trigger #2 fired specifically because this dependency doesn't exist yet; nothing else in `libs/common`'s scope is load-bearing for an already-blocked, already-real consumer the way this is.
Depends on: LC-002

### LC-004 — Fail-closed test suite for tenant context resolution [Must]
**As** `validation-service` (and the Tech Lead reviewing VS-010 later) **I want** the tenant-context dependency's fail-closed behavior proven by tests owned by this lib, not re-derived per consuming service **so that** every service importing `get_tenant_context` inherits the same tested guarantee instead of re-testing FastAPI wiring itself.

Acceptance criteria:
- [ ] A test confirms a request with a valid `tenant_id` resolves a `TenantContext` with that exact value, reachable inside a route handler via `Depends()`.
- [ ] A test confirms a request with a missing `tenant_id` is rejected (4xx) **before** reaching a route handler body — a dummy handler that would raise if called proves it was never invoked, matching VS-010's own acceptance criterion ("fails closed, not open").
- [ ] A test confirms a request with an empty-string or whitespace-only `tenant_id` is rejected the same way (not silently accepted as a valid-but-empty tenant).
- [ ] Tests run against a minimal FastAPI test app defined in this lib's own `tests/` (not against `validation-service`) — this lib's guarantee must be provable standalone, independent of any one consumer's app wiring.

Rationale for priority: solution-design.md section 1 principle 3 calls tenant isolation "first-class... not retrofitted"; a resolver without a proven fail-closed test is exactly the kind of gap that principle exists to prevent, so the test suite is Must, not a follow-up.
Depends on: LC-003

### LC-005 — README status update + public API doc-sync [Should]
**As a** future contributor (human or Claude) extending `libs/common` after this backlog **I want** the README's status, "owns"/"does not own" sections, and public function list kept current **so that** the next module (e.g. `gateway-api` at trigger #5) doesn't have to re-derive what this lib actually contains versus what it merely lists as eventual scope.

Acceptance criteria:
- [ ] `libs/common/README.md` status line reads "implemented (partial): tenant-context module only" rather than "planned," and explicitly lists `TenantContext` and `get_tenant_context` as the current public API.
- [ ] The README's existing "owns" bullet is annotated to distinguish shipped scope (tenant context) from not-yet-shipped scope (shared schemas, DB session helpers, formatting logic) so a reader doesn't assume the whole "owns" list is implemented.
- [ ] A doc-sync check (function-signature list in README vs. actual public API), following the precedent already set by `libs/naive_first_engine`'s NFE-018, is either added now or explicitly logged as a follow-up ticket if deferred — not silently skipped.

Rationale for priority: implementation-plan.md section 8 requires this for every module "from the moment it has more than a README"; it's Should rather than Must because VS-010 can be unblocked and verified against the actual code (LC-001–004) without the doc-sync tooling existing yet — the risk is future drift, not today's blocker.
Depends on: LC-003

### LC-006 — Shared Pydantic schemas for cross-service payloads [Won't (this backlog)]
**As a** future second consumer of a validation-service-shaped payload (e.g. `gateway-api` or `reporting-service`) **I want** a shared schema in `libs/common` **so that** both sides of that boundary can't drift.

Acceptance criteria: none — not built in this backlog.

Rationale for priority: no second real consumer exists yet. `gateway-api` (trigger #5) and `reporting-service` (trigger #7) are both not fired; `validation-service` is currently the only service with a request/response shape, and it owns that shape itself until something else needs to consume it. Building this now would violate the README's own explicit instruction: "don't move things here in case another service needs them later (YAGNI; move on second real use)." Revisit the moment a second service's route handler needs to accept or return a shape `validation-service` already defined.
Depends on: none (deferred, not blocked)

### LC-007 — DB session helpers [Won't (this backlog)]
**As a** future second service persisting to a shared Postgres instance **I want** a shared DB session helper in `libs/common` **so that** connection/session setup isn't duplicated per service.

Acceptance criteria: none — not built in this backlog.

Rationale for priority: `validation-service`'s VS-004 already shipped an interim SQLite-backed repository without this helper, and `infra/docker-compose.yml` + Postgres (trigger #4) has not been built yet per backlog-validation-service.md decision 2 — there is no live Postgres instance for a session helper to wrap, and still only one service that would use it. Building this now would be scaffolding for infrastructure that doesn't exist. Revisit when trigger #4 fires and a second service needs to open a session against the same Postgres instance.
Depends on: none (deferred, not blocked)

### LC-008 — Common formatting logic (e.g. metrics-table rendering) [Won't (this backlog)]
**As a** future `dashboard-web` or `reporting-service` **I want** shared metrics-table formatting in `libs/common` **so that** both render the same numbers the same way.

Acceptance criteria: none — not built in this backlog.

Rationale for priority: the README names this pattern's actual justification as "shared by `dashboard-web` and `reporting-service`" — neither exists yet (triggers #7 and #8, both not fired). There is nothing to de-duplicate between zero real implementations. Revisit the moment the second of those two services needs to render the same metrics table the first one already renders.
Depends on: none (deferred, not blocked)

### LC-009 — JWT/API-key-based tenant resolution [Won't (this backlog)]
**As** `gateway-api` (once it exists) **I want** `get_tenant_context` (or a sibling resolver) to derive `TenantContext` from a verified JWT/API key instead of an explicit request field **so that** tenant identity is cryptographically authenticated, not merely asserted by the caller.

Acceptance criteria: none — not built in this backlog.

Rationale for priority: this is explicitly `gateway-api`'s concern per solution-design.md section 3.6 ("JWT-based sessions... API keys... `tenant_id` embedded in the token/key, enforced at the API layer") and implementation-plan.md trigger #5 ("as soon as more than one external caller needs access — i.e. the first pilot client"), which has not fired. Building real auth now, before `gateway-api` or a real external caller exists, would mean inventing a verification boundary with nothing on the other end to issue or check tokens against — the precise kind of premature build the trigger-based order in implementation-plan.md section 6 is designed to prevent. LC-003's swappable-resolution-strategy design (single internal seam) is what makes this a clean follow-up rather than a rewrite when trigger #5 fires.
Depends on: `services/gateway-api` scaffolding (trigger #5, not fired) — flagged for PM/Tech Lead to sequence as a follow-up `libs/common` backlog round, not a reopening of LC-003.
