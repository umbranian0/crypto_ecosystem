# Backlog — Technical Upgrades (cross-cutting architecture review)

Source: `docs/implementation-plan.md` sections 7 (design patterns table) and 9 (engineering
conventions/DRY rules); `docs/solution-design.md` section 1 (four founding principles);
`CLAUDE.md`. Scope: every real, shipped, tested `.py` file under
`libs/naive_first_engine/src/`, `libs/common/src/`, `services/validation-service/src/app/`,
and `services/gateway-api/src/app/`, plus their `tests/` directories (read for fixture-
duplication analysis only, not for feature completeness). Explicitly out of scope per the
task brief: `infra/`, `ingestion-service`, `reporting-service`, `dashboard-web`,
`economic-service` — none of these have shipped code yet.

This is not a feature backlog. It is a gap analysis: what does the code actually do vs.
what implementation-plan.md's own named patterns/DRY rules and solution-design.md's four
principles say it should do. Every story below cites the exact file/lines the gap was found
in. Where a section was checked and found solid, that is stated explicitly rather than
padded with a manufactured story.

## Areas checked with no real gap found

- **naive_first_engine's Template Method / Strategy patterns**: `protocol.py`'s
  `run_validation_protocol` is genuinely the only code path that produces a `DMResult`, the
  split→baseline→metric→DM-test order is not parameterizable, and `baselines.py`'s
  `Baseline` Protocol is a clean Strategy seam (pre-sliced `train`/`test` args make
  post-`train_end` leakage structurally impossible, not just conventionally disallowed).
  Matches implementation-plan.md section 7 exactly. No story here.
- **Repository pattern shape consistency between the two services' interfaces**:
  `validation-service/.../repositories/interfaces.py` and
  `gateway-api/.../repositories/interfaces.py` independently converged on the same shape —
  `typing.Protocol` (not ABC), frozen local dataclass records (not reused SQLAlchemy
  models, specifically to keep the interface module import-clean of the storage driver),
  and a documented `tenant_id`-first convention with explicitly named exceptions. This is
  the one place two independently-built modules *didn't* diverge. No story here — see
  ARCH-001/002 below for where the *implementations* behind these interfaces did diverge
  in a way that matters.
- **DI usage**: both services exclusively inject repositories/clients via `Depends()` typed
  against the Protocol interfaces, never a concrete class, in every router. Consistent with
  section 7's DI row. No story here.
- **Observer/pub-sub**: `validation-service/.../events.py`'s `EventPublisher` Protocol +
  `InProcessLogEventPublisher` matches section 7's description exactly (interim in-process
  stand-in, explicit note that a Redis Streams implementation swaps in behind the same
  seam). No story here.
- **Error-handling style difference between the two services** was checked and is *not* a
  DRY violation: `gateway-api`'s `_call_downstream`/`_raise_for_error` handle HTTP-proxy
  failure modes (transport errors, status forwarding); `validation-service`'s broad
  `except Exception` in `routers/runs.py` handles business-logic execution failure
  (dataset load / protocol errors). These are genuinely different problems, not the same
  logic expressed two ways. No story here.
- **`libs/common` staying minimal (YAGNI-until-second-use)**: it currently holds exactly one
  thing, `TenantContext`, matching the documented plan. This was correct up to now — but
  ARCH-001 and ARCH-003 below identify the two places where a second consumer has already
  appeared and the YAGNI trigger has now fired.

## Stories

### ARCH-001 — Extract duplicated SQLite engine-building scaffolding into libs/common before Postgres repos land [Must]

**As a** dev-agent implementing VS-013/GW-012 (the upcoming Postgres repositories) **I want** the engine/session-bootstrap code to live in one shared place **so that** the debt sprint doesn't triple a piece of scaffolding that is already duplicated twice, instead of fixing it once while it's still cheap.

Evidence: `services/validation-service/src/app/repositories/sqlite_repository.py:32-40`
(`_build_engine`) and `services/gateway-api/src/app/repositories/sqlite_repository.py:33-39`
(`_build_engine`) are byte-for-byte identical: `create_engine(f"sqlite:///{db_path}")` +
`Base.metadata.create_all(engine)`, down to the docstring wording. This is exactly the
scenario implementation-plan.md section 9 describes ("if two services seem to need the same
logic, that logic belongs in a lib, not copy-pasted") — and the "second use" that should
have triggered `libs/common` picking this up already happened; it just hasn't been acted on.

Acceptance criteria:
- [ ] `libs/common` gains a generic engine-building helper (e.g. `build_engine(url, base)`) that both services' repository modules call instead of defining their own
- [ ] Existing SQLite repository test suites (`test_sqlite_repository.py` in both services) pass unmodified in behavior after the refactor
- [ ] README/module docstring in both services' repository modules is updated to point at the shared helper as the seam VS-013/GW-012 must extend for Postgres

Rationale for priority: Must — this is a literal, already-doubled DRY violation against implementation-plan.md section 9's own rule, and the next sprint (VS-013 + GW-012, both adding Postgres repositories) is the exact trigger that turns "duplicated twice" into "duplicated and now backend-specific in four places," at which point unwinding it is a bigger job than doing it now.
Depends on: none

### ARCH-002 — Fix per-request DB engine instantiation before either service gets a real connection pool to exhaust [Must]

**As a** platform operator running the upcoming Postgres-backed services **I want** the database engine constructed once per process, not once per request **so that** the VS-013/GW-012 Postgres migration doesn't turn every single request into a fresh connection-pool creation under real traffic.

Evidence: `services/validation-service/src/app/dependencies/repositories.py:44-49`
(`get_validation_run_repository`, `get_split_result_repository`) and
`services/gateway-api/src/app/dependencies/repositories.py:41-50`
(`get_tenant_repository`, `get_user_repository`, `get_api_key_repository`) all construct a
brand-new `SQLite*Repository(_db_path())` on every `Depends()` resolution — i.e. every
request — with no caching. Each constructor call runs `_build_engine`, i.e.
`create_engine(...)`, again. SQLite tolerates this today mostly by accident (no real
connection pool, file-based); Postgres will not — `create_engine()` per request means a new
connection pool object per request, which will exhaust Postgres connections under any
concurrent load.

Acceptance criteria:
- [ ] Engine construction is memoized once per process in both services (e.g. `functools.lru_cache` on the provider function, or app-startup-time construction stored on `app.state`)
- [ ] Repository objects remain cheap/per-request, but share the single underlying engine
- [ ] A test asserts the same engine (or session factory) is reused across two separate dependency resolutions within a process, so a future edit can't silently reintroduce per-request engine creation

Rationale for priority: Must — this is precisely "a concrete DRY/SOLID problem that will get materially worse in the very next sprint": it's currently latent (SQLite masks it) and becomes an operational incident the moment VS-013/GW-012 point the same code shape at Postgres.
Depends on: ARCH-001 (same files; naturally fixed together)

### ARCH-003 — Move the gateway-api proxy wire-contract (RunRequest/RunResponse/RunDetailResponse/SplitResultResponse) into a shared libs package instead of hand-copied Pydantic models [Must]

**As a** dev-agent extending the metrics/results shape (e.g. VS-017's client-model baseline, or simply a new `MetricSet` field) **I want** the run/split response contract defined in exactly one place **so that** a single schema change doesn't require manually editing seven independently-maintained copies of the same field list across two services.

Evidence: `services/gateway-api/src/app/routers/runs.py:56-122` defines four Pydantic
models whose own docstrings say they are "Field-for-field copies of validation-service's own
`RunRequest`/`RunResponse`/`RunDetailResponse`... read directly from those files, not
guessed" and "Field-for-field copy of validation-service's `SplitResultResponse`". This is a
second, independently-maintained copy of `services/validation-service/src/app/routers/runs.py:88-122`
and `services/validation-service/src/app/routers/splits.py:39-69`. Counting all the places
the same 14 per-baseline metric fields (`model_mae`...`naive0_oos_r2`) currently have to be
kept in sync by hand: `naive_first_engine/report_schema.py`'s `MetricSet` (source of truth),
`validation-service/app/models.py`'s `SplitResult` SQLAlchemy columns,
`validation-service/app/repositories/interfaces.py`'s `SplitResultRecord` dataclass,
`sqlite_repository.py`'s row-construction code, `routers/runs.py`'s manual
`SplitResultRecord(...)` construction, `routers/splits.py`'s `SplitResultResponse` Pydantic
model, and now `gateway-api/routers/runs.py`'s own `SplitResultResponse` copy — seven places,
two of them (validation-service's internal ones) arguably necessary given the
Protocol/SQLAlchemy/Pydantic boundary, but the eighth (gateway-api's copy) is the one
implementation-plan.md section 9 explicitly calls out: "pull shared logic into a `libs/*`
package instead if it's genuinely cross-cutting."

Acceptance criteria:
- [ ] A shared Pydantic contract module for the run/split wire shapes exists under `libs/*` (e.g. `libs/common` or a new small package)
- [ ] `gateway-api`'s router imports it instead of hand-copying the four model classes
- [ ] `validation-service`'s router uses the same shared models as its `response_model` wherever the shape is genuinely field-for-field identical
- [ ] `test_runs_routing.py` (gateway-api) and `test_runs_endpoint.py`/`test_splits_endpoint.py` (validation-service) pass unmodified in behavior

Rationale for priority: Must — the two-consumer YAGNI threshold that `libs/common`'s own stated rule ("as soon as a second module needs to share a data shape") is keyed to has already been crossed; leaving it copy-pasted means every future field addition (VS-017's client-model baseline is already planned) is a two-service manual-sync operation with no test that would catch drift if one copy is missed.
Depends on: none

### ARCH-004 — Extract duplicated SQLite test-fixture scaffolding into a shared test-utility [Should]

**As a** dev-agent writing VS-013/GW-012's Postgres repository test suites **I want** the "isolated per-test DB file" fixture defined once **so that** it isn't hand-copied a third and fourth time as both services' test suites grow.

Evidence: `services/validation-service/tests/test_sqlite_repository.py:26-31` and
`services/gateway-api/tests/test_sqlite_repository.py:30-35` define byte-identical `db_path`
pytest fixtures — including copy-pasted comment wording ("A real file path (not `:memory:`)
so this exercises the same file-based-persistence code path..."). Three independent dev-agent
sessions built `naive_first_engine`, `validation-service`, and `gateway-api`'s test suites
with no shared review pass between them; this fixture is the one piece of scaffolding that
is genuinely identical, not just similarly-shaped.

Acceptance criteria:
- [ ] A shared test fixture/helper (e.g. via a small `libs/common` test-utilities extra, or a documented `conftest.py` pattern both services import) provides the `db_path`-style fixture
- [ ] Both services' `test_sqlite_repository.py` files use it instead of their own copy

Rationale for priority: Should, not Must — it's test scaffolding, not production code, so the cost of leaving it duplicated is developer annoyance and drift risk, not an operational failure mode. Worth doing alongside ARCH-001 while touching the same files, but doesn't block the Postgres migration the way ARCH-001/002 do.
Depends on: none

### ARCH-005 — Track validation-service's unauthenticated tenant-header trust as a hard network-isolation dependency, not an implicit assumption [Should]

**As the** Product Owner following solution-design.md principle 3 ("tenant isolation is a first-class concern from the first commit, not retrofitted") **I want** the current gap between gateway-api's verified auth and validation-service's header-trusting auth to be an explicit, tracked dependency **so that** it is never mistaken for already having been closed.

Evidence: `libs/common/src/naive_first_common/tenant_context.py:43-58`'s
`get_tenant_context` reads `X-Tenant-Id` straight off the inbound request with no
verification — its own docstring says so ("Interim strategy... LC-009 will replace this with
gateway-api-verified-auth-derived resolution"). `validation-service`'s routers
(`runs.py:132`, `splits.py:77`) depend on it directly and have no equivalent of
`gateway-api`'s `get_authenticated_tenant` (`services/gateway-api/src/app/dependencies/auth.py`),
which does verify a hashed API key before trusting a tenant. Concretely: anything that can
reach `validation-service`'s port directly (not only `gateway-api`) can set `X-Tenant-Id` to
any value and read/write any tenant's runs — this is real today, not hypothetical, and it's
the one place the "fail closed, tenant_id-first" rule is enforced with materially different
strictness between the two services (gateway-api: cryptographic proof; validation-service:
an unverified header).

Acceptance criteria:
- [ ] LC-009 (already referenced in the code's own docstring) ships before validation-service's port is ever reachable by anything other than gateway-api in any deployed environment
- [x] Once `infra/docker-compose.yml`/README exist (implementation-plan.md section 6, trigger #4), they document "only gateway-api may reach validation-service" as a hard network-topology requirement, not an implicit one inherited from "well, nothing else calls it yet" — **partially addressed 2026-08-09**: `infra/docker-compose.yml`'s `validation-service` port is now bound to `127.0.0.1` only (not the host's public interface), closing the cheap network-topology half of this AC. The cryptographic half (LC-009) is still open — this binding does not stop anything already on the same host/Docker network from reaching validation-service directly, it only stops external hosts.

Rationale for priority: Should, not Must — the code already flags this as a known, scheduled interim state (not a silent gap), and `validation-service` is architecturally not internet-facing per implementation-plan.md section 2 ("gateway-api is the only internet-facing service"), so the actual exposure only materializes if network-level isolation is separately misconfigured. That's a real but secondary risk, not a founding-principle violation happening in the code path today.
Depends on: none (tracking/documentation story; LC-009 itself is already implied future work, not new scope invented here)

### ARCH-006 — Do not force a generic "record mapper" abstraction over the two services' SQLAlchemy-to-dataclass conversion functions [Won't]

Considered: `_run_to_record`/`_split_result_to_record` (validation-service) and
`_tenant_to_record`/`_user_to_record`/`_api_key_to_record` (gateway-api) all follow the same
*shape* — take a SQLAlchemy row, return a frozen dataclass with the same field names.

Rejected because: the field lists are entirely different per schema (`Run`/`SplitResult` vs.
`Tenant`/`User`/`ApiKey`) — there is no shared *logic* to extract, only a shared *pattern
shape*, and implementation-plan.md section 9's DRY rule is about duplicated logic, not
duplicated code shape. Forcing a generic mapper abstraction over two structurally-unrelated
schemas would add a layer of indirection without removing any real duplication, and runs
against the grain of section 7's own explicit anti-goal list ("Deliberately not using yet...
generic plugin/microkernel frameworks"). Contrast with ARCH-001, where `_build_engine` in
both files is not just shape-similar but line-for-line identical, executable logic — that is
the real duplication worth extracting.

### ARCH-007 — Adopt a protocol-agnostic service-identification convention for every API surface [Should]

**As a** dev-agent adding a new router or protocol surface to `gateway-api` **I want** a documented, protocol-agnostic convention for naming which backing service an endpoint belongs to **so that** the identification scheme doesn't have to be redesigned the first time a non-REST protocol (gRPC, GraphQL) is added alongside REST.

Evidence: `services/gateway-api/src/app/main.py`'s `app.include_router(runs.router, tags=["validation-service"])` (added 2026-08-09) is currently the only place a downstream-service identifier is attached to an API surface, and it's REST/OpenAPI-tag-specific — there is no written convention for what the equivalent identifier should be if a gRPC service (package/service name in the `.proto`) or a GraphQL surface (schema stitching / type namespace per source service) is added later. Without a documented rule, each protocol would likely invent its own ad hoc naming shape instead of following one deliberate convention.

Acceptance criteria:
- [ ] A short "service identification" convention is documented (e.g. in `services/gateway-api/README.md` or `docs/implementation-plan.md` section 9): REST surfaces tag every router with the backing service's name (`tags=["<service-name>"]`); the same rule is written down for gRPC (service/package naming) and GraphQL (schema namespace) so the convention is protocol-agnostic even though gRPC/GraphQL don't exist yet
- [ ] Existing `runs.router` tag (`"validation-service"`) is confirmed as the first instance of this convention, not a one-off
- [ ] Any future router added to `gateway-api` follows the same tagging rule as part of its own acceptance criteria (noted for the Tech Lead to enforce at ticket-writing time, not re-derived per ticket)

Rationale for priority: Should — no current code violates this (there's exactly one router today), but writing the convention down now, while it's cheap and REST-only, avoids three independently-built protocol surfaces converging on three different naming shapes the way `_build_engine` (ARCH-001) independently converged on duplicated logic.
Depends on: none

### ARCH-008 — Document the OpenAPI `Security()`/`APIKeyHeader` auth pattern as the standard for any future authenticated route [Should]

**As a** dev-agent adding a new authenticated router to `gateway-api` **I want** the `Security()`/`fastapi.security.APIKeyHeader` pattern (not bare `Header()`) written down as the required shape for any header-based auth dependency **so that** Swagger's single top-level "Authorize" button keeps working for every future endpoint, instead of a future router silently reverting to plain `Header()` parameters that force per-endpoint header re-entry.

Evidence: `services/gateway-api/src/app/dependencies/auth.py`'s `get_authenticated_tenant` was rewritten 2026-08-09 from `authorization: str | None = Header(default=None)` / `x_api_key: str | None = Header(default=None, alias="X-Api-Key")` to `Security(_authorization_scheme)` / `Security(_x_api_key_scheme)` (`APIKeyHeader` instances), purely so FastAPI registers `securitySchemes` in the OpenAPI doc and Swagger UI shows one "Authorize" dialog instead of two per-request header fields repeated on every endpoint. This change has no ticket and, unlike the `tags=` change (ARCH-007), had no backlog record at all until now.

Acceptance criteria:
- [ ] `services/gateway-api/README.md`'s auth section notes the `Security()`/`APIKeyHeader` pattern as the required shape for header-based auth dependencies, not just describing the resulting header names
- [ ] Any future authenticated router/dependency in `gateway-api` uses `Security()` + a `fastapi.security` class, not bare `Header()`, so it participates in the same global "Authorize" UX
- [ ] `_extract_raw_key`'s parsing/validation logic (unchanged by this rewrite, confirmed via `tests/test_auth.py`'s 11 passing cases) stays the single place format-checking happens, regardless of which FastAPI mechanism supplies the raw header string

Rationale for priority: Should — purely a documentation/consistency gap (the code behavior is unchanged and fully covered by existing tests), but cheap to close now before a second authenticated router exists and either follows or breaks this pattern by guesswork.
Depends on: none

## Summary

| Priority | Count | IDs |
|---|---|---|
| Must | 3 | ARCH-001, ARCH-002, ARCH-003 |
| Should | 4 | ARCH-004, ARCH-005, ARCH-007, ARCH-008 |
| Could | 0 | — |
| Won't | 1 | ARCH-006 |

Single most important finding: **ARCH-001/ARCH-002 together** — both services independently
implement the exact same SQLite engine-bootstrap function (`_build_engine`, byte-identical)
and both re-instantiate that engine on every single request via uncached `Depends()`
providers. This is latent and harmless under SQLite but becomes a real connection-pool
exhaustion risk under Postgres, and the next sprint's own tickets (VS-013, GW-012) are
exactly the trigger that turns this from "duplicated twice, works fine" into "duplicated
four times, breaks under load" — it is cheaper to fix once, now, than to fix after both
services have already grown Postgres-specific copies of the same bug.
