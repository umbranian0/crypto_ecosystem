# Backlog — validation-service

Source: `docs/da-tese-ao-produto.md` (sections 1.2, 2.1, 2.3.1, 2.7), `docs/solution-design.md` (section 1 principles, section 3.4, section 4 data model, section 6 build order), `docs/implementation-plan.md` (sections 2, 4, 5, 6, 7, 9), `services/validation-service/README.md`, `libs/naive_first_engine/README.md` (status: implemented/hardened, Sprint 01 + Sprint 02 done, regression gate closed), `libs/common/README.md`, `docs/sprints/sprint-01.md`, `docs/sprints/sprint-02.md`.

Scope: `services/validation-service` only — trigger #3 (implementation-plan.md section 6) has fired: `naive_first_engine`'s backlog, including the hard regression gate, shipped in full across Sprint 01 + Sprint 02. In scope: the FastAPI service skeleton, the `validation` schema (`runs`, `split_results`), the Repository-pattern data-access layer, the three contract endpoints (`POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`), invoking `naive_first_engine.run_validation_protocol` per the fixed Template Method order, and emitting `run.completed`. Out of scope, not touched by any story below: the validation algorithm itself (`libs/naive_first_engine` — done, not reopened here), dataset storage/upload (`services/ingestion-service`, trigger #6, not fired), report rendering (`services/reporting-service`, trigger #7, not fired), auth/tenant routing at the edge (`services/gateway-api`, trigger #5, not fired), the dashboard (`services/dashboard-web`, trigger #8, not fired), and `services/economic-service` (trigger #11, not fired).

**Three explicit scope/dependency decisions made for this backlog** (per the instruction not to assume silently):

1. **`libs/common` (trigger #2) — treated as a real cross-module dependency, not stubbed in-service.** Implementation-plan.md section 6 states trigger #2 fires "alongside" validation-service, and `libs/common`'s own README names tenant context as its exclusive ownership (dependency-injected via FastAPI `Depends()` in every service). Building a parallel tenant-context mechanism inside `validation-service` would duplicate logic implementation-plan.md section 9 explicitly says belongs in a lib once a second consumer needs it — and tenant isolation is called out in solution-design.md section 1 as a first-class, non-retrofittable principle, so getting the ownership boundary right here matters more than moving fast. Decision: `validation-service`'s own schema/repository work (tenant_id columns, tenant-scoped queries) proceeds now as this module's own responsibility, but the actual "resolve current caller's tenant" DI mechanism (VS-010) is written as **blocked on `libs/common` shipping a minimal tenant-context module** — flagged below for the PM/Tech Lead to sequence, most likely as a small parallel-track `libs/common` backlog rather than folded into this one.
2. **No `infra/docker-compose.yml` + Postgres yet, despite implementation-plan.md section 6 nominally firing that trigger "same moment as #3".** Per the current task framing, infra has not actually been built. Decision: Must-have stories build against the Repository interface (VS-003) with an **interim in-memory/SQLite-backed implementation** (VS-004) — this is exactly what the Repository pattern in this service's own README is *for* ("schema-per-service can later become DB-per-service without touching call sites"), so it's a legitimate use of the pattern rather than a workaround. The Postgres-backed implementation is written as a Should (VS-013), explicitly blocked on the infra trigger.
3. **Two more interim substitutions follow the same logic, flagged explicitly rather than left implicit:** (a) `run.completed` is contractually part of this service's "owns" section, but Redis Streams doesn't arrive until trigger #7 (`reporting-service`) — so event publishing is built as an interface (VS-009, Must, interim in-process/log implementation) with the Redis-backed implementation as a blocked Should (VS-014); (b) `POST /runs` needs a dataset to run against, but `ingestion-service`'s upload API and the processed object-storage zone don't exist yet (trigger #6) — so dataset input is built as a `DatasetSource` abstraction (VS-005, Must, interim inline-payload/local-file implementation) with the object-storage-backed implementation as a blocked Should (VS-015).

## Stories

### VS-001 — Service scaffolding [Must]
**As a** Tech Lead standing up the third module in the build order **I want** a proper `uv`-managed FastAPI service skeleton for `validation-service` **so that** endpoint, repository, and integration work in this backlog has a place to live and a working test runner from day one.

Acceptance criteria:
- [ ] `services/validation-service/pyproject.toml` exists, declares the FastAPI app, depends on `naive_first_engine` (path/workspace dependency) and, once available, `naive_first_common` — not before, per decision 1.
- [ ] `src/app/` skeleton exists (routers, dependencies, repositories packages) matching the layout implied by implementation-plan.md section 3.
- [ ] `tests/` exists with a working `pytest` config; `uv run pytest` passes with zero tests collected as a baseline.
- [ ] `services/validation-service/README.md`'s status line is updated from "planned" to "scaffolded" once this merges, per implementation-plan.md section 8's documentation convention.

Rationale for priority: nothing else in this backlog can be built or tested without a package/app skeleton to put it in — literal first step now that trigger #3 has fired.
Depends on: none

### VS-002 — `validation` schema definition (`runs`, `split_results`) [Must]
**As** `validation-service` **I want** typed schema definitions for `runs` and `split_results`, including a `tenant_id` column on both tables **so that** the service's own data model matches solution-design.md section 4 exactly and is tenant-scoped from the first commit, independent of whether tenant *resolution* (VS-010) exists yet.

Acceptance criteria:
- [ ] `runs(id, tenant_id, dataset_id, horizon, purge_gap_hours, split_config, status, created_at, completed_at)` and `split_results(id, run_id, split_index, train_start, train_end, purge_start, purge_end, test_start, test_end, model_mae, model_rmse, model_da, model_f1, naive0_mae, naive0_rmse, ..., dm_statistic, dm_pvalue, dm_verdict)` are defined as typed models (ORM or dataclass, per whatever VS-003/004 need), matching solution-design.md section 4 field-for-field.
- [ ] Every table carries `tenant_id` — no table in this schema is created without it, matching solution-design.md section 1 principle 3 ("every table ... tenant-scoped").
- [ ] The schema is defined once and reused by both the interim (VS-004) and future Postgres-backed (VS-013) repository implementations — no duplicate model definitions per backend.
- [ ] Migration source (e.g. Alembic revision files) exists under this service's own migration path even though it isn't run against a live Postgres yet — so VS-013 is a "point Alembic at a real DB" change, not a "write the migration" change.

Rationale for priority: every other story in this backlog (repositories, endpoints, event payloads) needs an agreed shape for `runs`/`split_results` first; this is the schema-per-service boundary from implementation-plan.md section 5 made concrete for this service.
Depends on: VS-001

### VS-003 — Repository interfaces: `ValidationRunRepository`, `SplitResultRepository` [Must]
**As** `validation-service` **I want** the two repositories named in this service's own README defined as typed interfaces (not tied to any storage backend) **so that** business logic (VS-006/007/008) never talks to storage directly, and the interim-to-Postgres swap (decision 2) is a new implementation class, not a rewrite of call sites.

Acceptance criteria:
- [ ] `ValidationRunRepository` and `SplitResultRepository` exist as ABCs/Protocols with methods covering: create a run, fetch a run by `(tenant_id, id)`, update run status, append split results, fetch splits by `(tenant_id, run_id)`.
- [ ] Every method signature requires `tenant_id` as an explicit parameter — no method can be called without specifying which tenant's data is being touched, matching this service's own tenant-isolation obligation regardless of where tenant *resolution* (VS-010) ends up living.
- [ ] No import of a concrete storage driver (SQLite, `sqlalchemy` engine, `psycopg`) appears in this interface module — enforced by a unit test that inspects imports, or by code review checklist noted in the PR.
- [ ] FastAPI route handlers (VS-006/007/008) are written to depend on these interfaces via `Depends()`, never on a concrete implementation directly, per implementation-plan.md section 7's Dependency Injection pattern.

Rationale for priority: this is the named Repository pattern from this service's own README and implementation-plan.md section 7 — it must exist before either the interim or the future Postgres-backed implementation, or the two will diverge in shape.
Depends on: VS-002

### VS-004 — Interim in-memory/SQLite-backed repository implementation [Must]
**As** `validation-service` **I want** a working implementation of both repositories backed by SQLite (or pure in-memory structures) **so that** `POST /runs`/`GET /runs/{id}`/`GET /runs/{id}/splits` are genuinely usable end-to-end now, without waiting on the infra trigger that hasn't fired yet (decision 2).

Acceptance criteria:
- [ ] A concrete class implements `ValidationRunRepository` and `SplitResultRepository` (VS-003) against SQLite (file-based, so state survives a process restart during manual testing) using the schema from VS-002.
- [ ] The implementation is swappable purely via dependency injection — no route handler or business-logic code changes when VS-013's Postgres-backed implementation later replaces this one in the DI wiring.
- [ ] A unit test suite exercises both repositories directly (create run, update status, append/fetch splits, tenant-scoping — two tenants' data never leaks into each other's query results) against this implementation.
- [ ] The service's README/status is updated to state explicitly that this is an interim storage backend pending `infra/docker-compose.yml` + Postgres (trigger #4), so a future contributor doesn't mistake it for the final design.

Rationale for priority: without a working repository implementation, no endpoint in this backlog can actually persist or return data — this unblocks VS-006/007/008 without silently waiting on an infra trigger that, per the task's current framing, hasn't actually fired yet.
Depends on: VS-003

### VS-005 — `DatasetSource` abstraction + interim inline/local-file implementation [Must]
**As** `validation-service` **I want** an abstraction for "where the series data for a run comes from," with an interim implementation that accepts inline payload data or a local file path **so that** `POST /runs` (VS-006) can execute a real validation run today, without `ingestion-service`'s upload API or the processed object-storage zone existing yet (trigger #6, not fired).

Acceptance criteria:
- [ ] A `DatasetSource` interface exists (e.g. `load(reference) -> Series`), mirroring the Adapter-style boundary implementation-plan.md section 7 uses elsewhere for pluggable external sources.
- [ ] An interim implementation accepts either an inline JSON/array payload in the `POST /runs` request body or a local filesystem path, and returns a time-indexed series in the shape `naive_first_engine.protocol.run_validation_protocol` expects.
- [ ] This module explicitly does not read from `processed/{tenant_id}/...` object storage — that's `ingestion-service`'s prefix per implementation-plan.md section 5, out of scope here even in the interim implementation.
- [ ] A unit test confirms both interim modes (inline payload, local file) produce an equivalent series structure and that malformed input is rejected with a clear validation error, not a silent empty series.

Rationale for priority: `POST /runs` has no data to validate without this; per decision 3(b), building the interface now and stubbing the transport is preferable to either blocking on `ingestion-service` or quietly hardcoding a dataset path into the endpoint handler.
Depends on: VS-001

### VS-006 — `POST /runs` endpoint [Must]
**As a** caller of `validation-service` (today: a Tech Lead/script invoking it directly; later: `gateway-api`) **I want** an endpoint that accepts a dataset reference plus run config (horizon, purge gap) and executes the full leakage-aware protocol **so that** running `naive_first_engine` against a real dataset via an API call — the literal trigger condition for this service — actually works.

Acceptance criteria:
- [ ] `POST /runs` accepts `tenant_id` (interim explicit field per decision 1, until VS-010 replaces it with resolved context), a dataset reference resolvable via `DatasetSource` (VS-005), and a config matching `naive_first_engine.protocol.ValidationConfig` (horizon, purge gap, at minimum).
- [ ] Config is validated against `ValidationConfig`'s own constraints before any execution starts (invalid horizon/purge-gap values return `422`, not a partially-run job) — no request reaches `run_validation_protocol` with a configuration `naive_first_engine` would itself reject.
- [ ] On success, the handler invokes `naive_first_engine.protocol.run_validation_protocol` (the fixed Template Method: split → baseline → metrics → DM test) exactly as-is — no reimplementation or reordering of the protocol inside this service, per this service's own README design note.
- [ ] Results are persisted via `ValidationRunRepository`/`SplitResultRepository` (VS-003/004): one `runs` row, one `split_results` row per split, matching solution-design.md section 4's field list.
- [ ] The endpoint returns the created run's `id` and initial `status` (e.g. `"running"` or `"completed"`, depending on whether execution is synchronous in this interim design — either is acceptable as long as it's documented, since no Prefect/worker orchestration exists yet).

Rationale for priority: this is the literal trigger condition for the whole service (implementation-plan.md section 6, trigger #3: "as soon as `naive_first_engine` needs to be run against a real dataset via an API call instead of a local script") — nothing else in this backlog matters if this doesn't work.
Depends on: VS-004, VS-005

### VS-007 — `GET /runs/{id}` endpoint [Must]
**As a** caller of `validation-service` **I want** to fetch a run's status and config by ID **so that** a client (script, future dashboard, future SDK) can poll for completion and see what config a run was executed with.

Acceptance criteria:
- [ ] `GET /runs/{id}` returns the run's `id`, `tenant_id`, `dataset_id`, `horizon`, `purge_gap_hours`, `split_config`, `status`, `created_at`, `completed_at` — the full `runs` row from solution-design.md section 4.
- [ ] Requests for a run belonging to a different tenant than the caller's return `404`, not the other tenant's data or a `403` that confirms the run exists — matches solution-design.md section 1 principle 3's tenant-isolation-by-default stance.
- [ ] Requests for a nonexistent run ID return `404` with a clear error body, not a `500`.
- [ ] A test confirms a run created via `POST /runs` (VS-006) is retrievable via this endpoint with matching field values.

Rationale for priority: named explicitly in this service's README contract (`GET /runs/{id}`); without it, `POST /runs` is a write-only endpoint with no way to check outcome.
Depends on: VS-006

### VS-008 — `GET /runs/{id}/splits` endpoint [Must]
**As a** caller of `validation-service` **I want** to fetch the per-split results of a run **so that** the detailed, non-aggregated metrics solution-design.md section 4 calls out as the point of this data model ("is the model still beating naive this month," not just a one-time verdict) are actually retrievable via API.

Acceptance criteria:
- [ ] `GET /runs/{id}/splits` returns one entry per split with all fields from `split_results` in solution-design.md section 4: boundaries, model metrics, naive0 metrics, DM statistic/p-value/verdict.
- [ ] Same tenant-isolation behavior as VS-007 (`404` on cross-tenant access, not data leakage).
- [ ] Splits are returned in `split_index` order.
- [ ] A test confirms the number and content of returned splits matches what `run_validation_protocol` produced for that run (round-trip check against VS-006's persisted output).

Rationale for priority: named explicitly in this service's README contract; this is the artifact the thesis's own appendix was missing (solution-design.md section 4) — the whole reason `split_results` is wide and per-split rather than aggregated-only.
Depends on: VS-006

### VS-009 — `run.completed` event publishing interface + interim implementation [Must]
**As** `validation-service` **I want** a publishing interface for the `run.completed` event, with an interim in-process/log-based implementation **so that** this service's contractual "emits `run.completed`" obligation (its own README's "owns" section) is honestly fulfilled today, without depending on Redis Streams infra that doesn't exist until trigger #7.

Acceptance criteria:
- [ ] An `EventPublisher` interface exists (e.g. `publish(event_name, payload)`), consistent with the Observer/pub-sub pattern named in implementation-plan.md section 7 for this exact event.
- [ ] `POST /runs` (VS-006) calls this interface with a `run.completed` event (run ID, tenant ID, status) when a run finishes, regardless of which implementation is wired in.
- [ ] The interim implementation logs the event (structured log line) and/or stores it in an in-memory list retrievable in tests — sufficient to prove the call happens at the right point in the flow, without a live message broker.
- [ ] A test confirms `run.completed` is published exactly once per completed run, and is not published if the run fails validation before completion (ties to VS-012).
- [ ] Documentation (service README) states plainly that this is an interim, non-durable event mechanism pending Redis Streams (trigger #7), so `reporting-service`'s eventual subscription isn't assumed to already work end-to-end.

Rationale for priority: "emits `run.completed`" is stated directly in this service's own README "owns" section — building the interface now (rather than deferring the whole feature) keeps the contract honest while decision 3(a) defers only the transport.
Depends on: VS-006

### VS-010 — Tenant context resolution (blocked on `libs/common`) [Must]
**As** `validation-service` **I want** the "who is calling, which tenant do they belong to" resolution to come from a shared, dependency-injected tenant-context mechanism **so that** tenant scoping isn't hand-rolled per-service and later diverges from what `gateway-api`/`dashboard-web` end up using.

Acceptance criteria:
- [ ] Route handlers resolve `tenant_id` via a FastAPI `Depends()` provided by `naive_first_common`'s tenant-context module, replacing the interim explicit `tenant_id` request field used by VS-006/007/008.
- [ ] No tenant-resolution logic (JWT/API-key parsing, tenant lookup) is implemented inside `validation-service` itself — it is imported from `libs/common`, per implementation-plan.md section 9's rule that shared logic belongs in a lib, not copy-pasted per service.
- [ ] A test confirms requests without a resolvable tenant context are rejected before reaching repository code (fails closed, not open).
- [ ] This story is not started until `libs/common` ships a minimal tenant-context module — it is **explicitly blocked**, not implemented against a placeholder that then gets thrown away.

Rationale for priority: tenant isolation is a first-class, non-retrofittable principle (solution-design.md section 1 principle 3); it is Must-priority for the service's eventual correctness, but its dependency status must be visible to the PM/Tech Lead rather than silently worked around — see decision 1.
Depends on: `libs/common` minimal tenant-context module (not yet built — cross-module dependency, flagged for PM/Tech Lead to sequence, likely via a small parallel `libs/common` backlog)

### VS-011 — Integration regression test: `POST /runs` round trip [Must]
**As** `validation-service` **I want** an integration test that drives a full `POST /runs` → `GET /runs/{id}/splits` round trip on a seeded synthetic dataset and checks the returned numbers **so that** the service's wiring of `naive_first_engine` (already regression-tested in isolation, per Sprint 01/02) is confirmed correct at the API boundary too, not just at the library boundary.

Acceptance criteria:
- [ ] Uses the same kind of seeded, documented synthetic fixture approach as `naive_first_engine`'s own `test_regression_1h.py` (disclosure block stating what's real vs. reconstructed), submitted via the actual `POST /runs` HTTP interface rather than calling `run_validation_protocol` directly.
- [ ] Asserts the persisted/returned Naive0 MAE and DM verdict counts match the same reference numbers `naive_first_engine`'s own regression suite checks against (da-tese-ao-produto.md section 1.3), confirming no value gets altered/misrouted between the library call and the persisted `split_results` row.
- [ ] Runs as part of this service's own `pytest` suite (`uv run pytest` in `services/validation-service`), not merely by depending on `naive_first_engine`'s suite passing.
- [ ] Clearly documented as an integration/wiring check, not a re-derivation of the algorithm's correctness (that remains `naive_first_engine`'s job, already done).

Rationale for priority: closes the loop on this service's core purpose — wrapping `naive_first_engine` as a REST service — with the same rigor (regression-tested against published numbers) the engine itself was held to before any service was allowed to depend on it (per `naive_first_engine`'s README "Contract" section).
Depends on: VS-006, VS-008

### VS-012 — Run failure/status handling [Must]
**As a** caller of `validation-service` **I want** a run that fails during execution (bad data, protocol error) to be reflected as a `status="failed"` run with an error reason, not a silent `500` or a `runs` row stuck in `"running"` forever **so that** callers can distinguish "still processing" from "broke, here's why," which matters for an audit product where trust in the result is the entire value proposition.

Acceptance criteria:
- [ ] Any exception raised by `DatasetSource.load` or `run_validation_protocol` during `POST /runs` results in a persisted `runs` row with `status="failed"` and a stored error message/reason, not an unpersisted `500` with no trace.
- [ ] `GET /runs/{id}` surfaces the failure status and reason to the caller.
- [ ] `run.completed` (VS-009) is explicitly **not** published for failed runs — a failure is not a completion.
- [ ] A test forces a `DatasetSource` failure (e.g. malformed inline payload) and confirms the run row, status, and non-published event all behave as above.

Rationale for priority: an audit/validation product whose own failures are invisible or indistinguishable from success undermines the "honest statistical verdict" positioning in da-tese-ao-produto.md section 2.2 — this is a Must, not a hardening afterthought.
Depends on: VS-006, VS-009

### VS-013 — Postgres-backed repository implementation [Should]
**As** `validation-service` **I want** a Postgres/TimescaleDB-backed implementation of `ValidationRunRepository`/`SplitResultRepository` **so that** the service moves off the interim SQLite backend (VS-004) onto the schema-per-service Postgres design solution-design.md section 3.2 specifies, once real infra exists.

Acceptance criteria:
- [ ] Implements the same interfaces as VS-004 against Postgres, using the Alembic migration source already written in VS-002.
- [ ] Swapping VS-004 → VS-013 in the DI wiring is the only change required — no route handler or business logic changes, proving the Repository pattern (VS-003) did its job.
- [ ] Row-level tenant scoping is enforced at the query level (not just application-level filtering), matching solution-design.md section 3.2's "pool" multi-tenancy model.
- [ ] The interim SQLite implementation (VS-004) is retained (not deleted) for local/unit-test use, per the pattern's own stated purpose.

Rationale for priority: correct and expected per the design, but explicitly blocked on `infra/docker-compose.yml` + Postgres (trigger #4), which per the current task framing has not actually been built yet — Should, not Must, until that trigger fires in practice.
Depends on: VS-004; blocked on `infra/docker-compose.yml` + Postgres (trigger #4, not yet built)

### VS-014 — Redis Streams-backed `run.completed` publisher [Should]
**As** `validation-service` **I want** the interim in-process event publisher (VS-009) replaced with a Redis Streams-backed implementation **so that** `reporting-service` can actually subscribe to `run.completed` once it exists, per implementation-plan.md section 4.

Acceptance criteria:
- [ ] Implements the same `EventPublisher` interface as VS-009 against Redis Streams.
- [ ] Swapping VS-009's interim implementation for this one in DI wiring requires no change to `POST /runs`'s call site.
- [ ] Event payload shape is documented (run ID, tenant ID, status, completion timestamp) so `reporting-service`'s eventual consumer can be built against a stable contract.

Rationale for priority: correct per the design, but blocked on Redis Streams infra, which per implementation-plan.md section 6 arrives with trigger #7 (`reporting-service`) — not yet fired.
Depends on: VS-009; blocked on trigger #7 (`services/reporting-service` + Redis Streams, not yet built)

### VS-015 — Object-storage-backed `DatasetSource` implementation [Should]
**As** `validation-service` **I want** a `DatasetSource` implementation that reads from the `processed/{tenant_id}/...` object-storage zone **so that** runs can be triggered against datasets `ingestion-service` has already landed, instead of requiring inline payloads or local files.

Acceptance criteria:
- [ ] Implements the same `DatasetSource` interface as VS-005 against the processed object-storage zone path scheme from solution-design.md section 3.2.
- [ ] Swapping VS-005's interim implementation for this one requires no change to `POST /runs`'s handler code.
- [ ] Still does not write to or own any part of the object-storage prefix — read-only, consistent with this service's "does not own dataset storage" boundary.

Rationale for priority: correct per the design, but blocked on `ingestion-service`'s upload API and processed-zone writes (trigger #6), not yet fired.
Depends on: VS-005; blocked on trigger #6 (`services/ingestion-service`, not yet built)

### VS-016 — OpenAPI contract / README sync check [Should]
**As a** future contributor to `validation-service` **I want** confirmation that the FastAPI-generated OpenAPI schema and this service's README stay in sync **so that** implementation-plan.md section 8's documentation-for-scaling convention ("OpenAPI schema is the source of truth ... don't hand-maintain a duplicate") is actually true here, not just stated.

Acceptance criteria:
- [ ] The service's README links to how to regenerate/view the OpenAPI schema (e.g. `/openapi.json`, or a generated docs page) rather than hand-listing endpoint request/response shapes.
- [ ] A check (script or test) fails if the README's "Contract" section lists endpoints that don't match the live route set (mirrors `naive_first_engine`'s own `check_doc_sync.py` approach for its public function list, applied to routes instead of functions).

Rationale for priority: valuable hygiene matching an established convention in this repo, but not blocking any functional Must story — Should, not Must.
Depends on: VS-006, VS-007, VS-008

### VS-017 — Client-supplied prediction column as a `Baseline`-interface Strategy [Could]
**As** `validation-service` **I want** the ability to accept a client-supplied prediction column and run it through the same protocol as the naive baselines, via a Strategy implementation of `naive_first_engine`'s `Baseline` interface **so that** a client model can eventually be scored against Naive0/NaiveLast without a special-cased code path, per this service's own README design note.

Acceptance criteria:
- [ ] A wrapper class implements the same `Baseline` interface (`predict(train, test) -> Series`) `naive_first_engine.baselines.Naive0`/`NaiveLast` already implement, backed by a client-supplied prediction series instead of a computed forecast.
- [ ] `POST /runs` optionally accepts a client-prediction reference alongside the mandatory naive baselines — the naive baselines are never optional or skippable, per naive_first_engine's own structural rule (solution-design.md section 1 principle 1).
- [ ] No new execution path is introduced that runs arbitrary client code — this remains "client submits predictions," not "client submits a model," per solution-design.md section 1 principle 2.

Rationale for priority: valuable (it's the "bring your own model" flow's real starting point) but not required for the trigger condition that created this service (running `naive_first_engine` against a dataset via an API call) — Could, deferrable without blocking anything else in this backlog.
Depends on: VS-006

### VS-018 — Won't: execute arbitrary client model code [Won't]
Not proposed. Solution-design.md section 1 principle 2 states plainly that clients submit predictions, not model binaries, in the MVP — "running client model artifacts is a deliberate phase-2+ decision, not an MVP requirement." No story in this backlog authorizes a code path that executes client-supplied model code inside `validation-service`, now or as a follow-up.

### VS-019 — Won't: make the naive baseline optional or skippable [Won't]
Not proposed. Solution-design.md section 1 principle 1: "there is no code path that scores a model without them [Naive0/NaiveLast]." `naive_first_engine` already enforces this structurally; no story in this backlog introduces a `validation-service` flag, config option, or fast-path that bypasses it — including VS-017's client-prediction Strategy, which explicitly keeps the naive baselines mandatory.

### VS-020 — Won't: let another service read the `validation` schema directly [Won't]
Not proposed. Implementation-plan.md section 2: "no service reads another service's database schema directly." Any future need for `reporting-service` or `dashboard-web` to see run/split data is served through `validation-service`'s own API (or the `run.completed` event, VS-009/014) — never a direct query against the `validation` Postgres schema from outside this service.

### GW-017 cross-reference — Locust load-test suite (owned by gateway-api)
See `docs/product/backlog-gateway-api.md` GW-017 for a Locust load-test suite exercising this service's `POST /runs` (and validation-service's own synchronous execution cost) via gateway-api's public entry point — not duplicated here since gateway-api is the public-facing surface the load is actually driven through.
