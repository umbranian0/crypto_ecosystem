# naive_first_common

**Status: implemented (partial): tenant-context module (`TenantContext`, `get_tenant_context`, LC-001-004, Sprint 04) plus later, real, shipped additions -- `db.build_engine` (ARCH-001), `contracts` wire-contract Pydantic models (ARCH-003), `testing` shared pytest fixtures (ARCH-004), all from Sprint 06 -- and `logging` (structured logging + correlation id, OPS-006, Sprint 17) -- see docs/sprints/sprint-04.md, docs/sprints/sprint-06.md, docs/sprints/sprint-17.md, and docs/tickets/README.md. "Partial" describes the gap against this library's eventual full scope (shared cross-service Pydantic schemas beyond `contracts.py`, formatting logic -- see "Not yet owned" below), not a gap in what's already shipped: `TenantContext`/`get_tenant_context`/`build_engine`/`contracts`/`testing`/`logging` are all complete, tested, and consumed in production by both `validation-service` and `gateway-api` (LC-005 reconciliation: the original backlog wording "tenant-context module only" predates ARCH-001/002/003/004 and is stale on this point -- see docs/tickets/LC-005.md Analysis).**

Shared library for cross-cutting concerns used by more than one service. See [../../docs/implementation-plan.md](../../docs/implementation-plan.md) sections 2, 7, 9.

**Owns (shipped)**: tenant context -- `TenantContext` (frozen, validated Pydantic value object) and `get_tenant_context` (FastAPI `Depends()` resolver), dependency-injected in every service (LC-002/LC-003); `naive_first_common.db.build_engine` -- shared SQLAlchemy engine-building helper, generic over `url`/`base` (ARCH-001); `naive_first_common.contracts` -- shared Pydantic schemas passed across service boundaries (`RunRequest`/`RunResponse`/`RunDetailResponse`/`RunSummaryResponse`/`ClientBaselineResult`/`SplitResultResponse`, the run/split wire contract shared by `gateway-api` and `validation-service`, ARCH-003, extended VS-017); `naive_first_common.testing` -- test-utility fixtures shared across services (e.g. the `sqlite_db_path` pytest fixture, imported via each service's `tests/conftest.py`, ARCH-004); `naive_first_common.logging` -- structured JSON logging + request/tenant-correlation id convention shared by both FastAPI services (OPS-006, see its own section below).

**Not yet owned (forward-looking, not current content)**: shared cross-service Pydantic schemas *beyond* `contracts.py`'s already-shipped run/split wire contract (e.g. any future non-run/split cross-service shape), and common formatting logic (e.g. metrics-table rendering) that `dashboard-web`/`reporting-service` will likely need to share once either exists (implementation-plan.md trigger #7/#8) -- no such module exists in this package yet; noted here only so a future second consumer knows where it would land, per this library's own "extract on second duplication" rule. A dedicated DB *session* helper (as opposed to the already-shipped engine-building helper) is also not yet built.

**Does not own**: any service-specific business logic. If logic is only used by one service, it stays in that service -- don't pre-emptively move things here "in case" another service needs them later (YAGNI; move on second real use, per the DRY convention in the implementation plan).

**Contract**: plain typed Python, Pydantic + SQLAlchemy. Every service depends on this; this depends on nothing internal.

## Public API

Implementation-plan.md section 8: "for libs, the public function signatures in the README stay in sync with the code -- CI should fail if they drift." The list below is machine-checked by [`scripts/check_doc_sync.py`](scripts/check_doc_sync.py) (also runnable as `tests/test_doc_sync.py`) -- **re-run it after adding, removing, or renaming any public (non-underscore-prefixed) top-level function or class in any of the five modules below.** One line per public function/class, `` `name(args)` `` for functions (default-value expressions included, type annotations omitted, mirroring `naive_first_engine`'s NFE-018 precedent) or `` `ClassName` (class) `` for classes.

### `tenant_context.py`
- `TenantContext` (class)
- `get_tenant_context(x_tenant_id=Header(default=None, alias='X-Tenant-Id'))`

### `db.py`
- `build_engine(url, base)`

### `contracts.py`
- `RunRequest` (class)
- `RunResponse` (class)
- `RunDetailResponse` (class)
- `RunSummaryResponse` (class)
- `ClientBaselineResult` (class)
- `SplitResultResponse` (class)

### `testing.py`
- `sqlite_db_path(tmp_path)`

### `logging.py`
- `configure_structured_logging(level=logging.INFO)`
- `CorrelationIdMiddleware` (class)

`logging.py` also exports one module-level `contextvars.ContextVar` (not a
function/class, so it is not part of the machine-checked list above):
`correlation_id_var` -- holds the current request's correlation id (empty
string when unset). See "Structured logging / correlation id (OPS-006)"
below for the full contract.

## Structured logging / correlation id (OPS-006)

`naive_first_common.logging` is the shared structured-logging convention for
every FastAPI service in this platform (`gateway-api`, `validation-service`)
-- stdlib `logging` + a small JSON `Formatter` subclass, deliberately no
`structlog`/other third-party logging dependency (a Could-priority story that
must not add new dependency surface). `configure_structured_logging()`
replaces the root logger's handlers with one JSON-formatting `StreamHandler`
carrying a `_CorrelationIdFilter`, so every `logging.getLogger(__name__)` call
anywhere in the process picks up both the JSON shape and the current
request's correlation id automatically -- no `extra=` needed at each call
site. `CorrelationIdMiddleware` reads `X-Correlation-Id` from the inbound
request if present, otherwise generates `uuid4().hex`; sets `correlation_id_var`
for the duration of the request (reset via a `contextvars.Token` in a
`finally`, so a reused worker's next request can never see a stale id); also
sets `X-Correlation-Id` on the response. Both services register this
middleware and call `configure_structured_logging()` at `app.main` import
time; `gateway-api`'s `build_downstream_headers` forwards the same
correlation id as a header to `validation-service`, so one logical request's
logs can be joined across both services by that one id. This story does
**not** stand up a log-aggregation backend (still `OPS-007`'s own declined
scope) -- it ends at "logs are structured and correlatable," not "logs are
centrally searchable."

## CI

**CI**: `.github/workflows/ci.yml` runs this module's test suite on every push/PR.

**Coverage**: run tests with coverage locally via `uv run pytest -q --cov=naive_first_common --cov-report=term-missing` (no coverage threshold is enforced -- CI prints the report, it never fails the build on a percentage).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.
