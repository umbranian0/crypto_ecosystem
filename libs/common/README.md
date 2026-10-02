# naive_first_common

**Status: implemented (partial): tenant-context module (`TenantContext`, `get_tenant_context`, LC-001-004, Sprint 04) plus later, real, shipped additions -- `db.build_engine` (ARCH-001), `db.tenant_scope` (LC-010, Sprint 18), `contracts` wire-contract Pydantic models (ARCH-003), `testing` shared pytest fixtures (ARCH-004), all from Sprint 06 -- and `logging` (structured logging + correlation id, OPS-006, Sprint 17) -- see docs/sprints/sprint-04.md, docs/sprints/sprint-06.md, docs/sprints/sprint-17.md, and docs/tickets/README.md. "Partial" describes the gap against this library's eventual full scope (shared cross-service Pydantic schemas beyond `contracts.py`, formatting logic -- see "Not yet owned" below), not a gap in what's already shipped: `TenantContext`/`get_tenant_context`/`build_engine`/`tenant_scope`/`contracts`/`testing`/`logging` are all complete, tested, and consumed in production by both `validation-service` and `gateway-api` (LC-005 reconciliation: the original backlog wording "tenant-context module only" predates ARCH-001/002/003/004 and is stale on this point -- see docs/tickets/LC-005.md Analysis). Sprint 18's GW-020 added `contracts.DatasetSummaryResponse` (the `gateway-api`/`ingestion-service` dataset-summary wire shape) -- `gateway-api`'s new proxy is its first consumer; `ingestion-service`'s own `src/app/routers/datasets.py` was updated (Tech Lead follow-up, same sprint) to import this canonical definition too, replacing its original local field-for-field-equivalent copy, closing the duplication GW-020's own ticket had explicitly flagged rather than silently resolved.**

Shared library for cross-cutting concerns used by more than one service. See [../../docs/implementation-plan.md](../../docs/implementation-plan.md) sections 2, 7, 9.

**Owns (shipped)**: tenant context -- `TenantContext` (frozen, validated Pydantic value object) and `get_tenant_context` (FastAPI `Depends()` resolver), dependency-injected in every service (LC-002/LC-003); `naive_first_common.db.build_engine` -- shared SQLAlchemy engine-building helper, generic over `url`/`base` (ARCH-001); `naive_first_common.db.tenant_scope` -- shared per-transaction Postgres RLS-scoping helper (`SELECT set_config('app.tenant_id', :tenant_id, true)`), extracted from `gateway-api`'s and `validation-service`'s independently-duplicated implementations (LC-010); `naive_first_common.contracts` -- shared Pydantic schemas passed across service boundaries (`RunRequest`/`RunResponse`/`RunDetailResponse`/`RunSummaryResponse`/`DatasetSummaryResponse`/`ClientBaselineResult`/`SplitResultResponse`, the run/split/dataset wire contract shared by `gateway-api` and `validation-service`/`ingestion-service`, ARCH-003, extended VS-017/GW-020); `naive_first_common.testing` -- test-utility fixtures shared across services (e.g. the `sqlite_db_path` pytest fixture, imported via each service's `tests/conftest.py`, ARCH-004); `naive_first_common.logging` -- structured JSON logging + request/tenant-correlation id convention shared by both FastAPI services (OPS-006, see its own section below); `naive_first_common.consistency` -- the pure "beat Naive0 in N of M" majority rule (`verdict_category`/`run_beats_naive0`/`compute_consistency_indicator`/`ConsistencyIndicator`/`UNDEFINED_VERDICT_CATEGORY`), extracted from `dashboard-web`'s `charting.py` so `reporting-service` can reuse it (RPT-002-01).

**Not yet owned (forward-looking, not current content)**: shared cross-service Pydantic schemas *beyond* `contracts.py`'s already-shipped run/split/dataset wire contract (e.g. any future non-run/split/dataset cross-service shape), and common formatting logic (e.g. metrics-table rendering) that `dashboard-web`/`reporting-service` will likely need to share once either exists (implementation-plan.md trigger #7/#8) -- no such module exists in this package yet; noted here only so a future second consumer knows where it would land, per this library's own "extract on second duplication" rule.

**Does not own**: any service-specific business logic. If logic is only used by one service, it stays in that service -- don't pre-emptively move things here "in case" another service needs them later (YAGNI; move on second real use, per the DRY convention in the implementation plan).

**Contract**: plain typed Python, Pydantic + SQLAlchemy. Every service depends on this; this depends on nothing internal.

## Public API

Implementation-plan.md section 8: "for libs, the public function signatures in the README stay in sync with the code -- CI should fail if they drift." The list below is machine-checked by [`scripts/check_doc_sync.py`](scripts/check_doc_sync.py) (also runnable as `tests/test_doc_sync.py`) -- **re-run it after adding, removing, or renaming any public (non-underscore-prefixed) top-level function or class in any of the five modules below.** One line per public function/class, `` `name(args)` `` for functions (default-value expressions included, type annotations omitted, mirroring `naive_first_engine`'s NFE-018 precedent) or `` `ClassName` (class) `` for classes.

### `tenant_context.py`
- `TenantContext` (class)
- `get_tenant_context(x_tenant_id=Header(default=None, alias='X-Tenant-Id'))`

### `db.py`
- `build_engine(url, base)`
- `tenant_scope(session, tenant_id)`

### `contracts.py`
- `PathDatasetReference` (class)
- `InlineDatasetReference` (class)
- `StoredDatasetReference` (class)
- `ObjectKeyDatasetReference` (class)
- `RunRequest` (class)
- `RunResponse` (class)
- `RunDetailResponse` (class)
- `RunSummaryResponse` (class)
- `DatasetSummaryResponse` (class)
- `ClientBaselineResult` (class)
- `SplitResultResponse` (class)
- `SplitPointResponse` (class)
- `RunSplitSummary` (class)
- `SplitPoints` (class)

### `testing.py`
- `sqlite_db_path(tmp_path)`

### `logging.py`
- `configure_structured_logging(level=logging.INFO)`
- `CorrelationIdMiddleware` (class)

### `diagnostics.py`
- `RecentErrorsHandler` (class)

### `consistency.py`
The "beat Naive0 in N of M" consistency rule (RAV-010, extracted by RPT-002-01), the single implementation
shared by `dashboard-web` and `reporting-service`. Also exports the module-level constant
`UNDEFINED_VERDICT_CATEGORY`. Counts only already-computed `dm_verdict` values; no DM statistic is recomputed.
- `verdict_category(split)`
- `ConsistencyIndicator` (class)
- `run_beats_naive0(splits)`
- `compute_consistency_indicator(runs)`

### `disclosures.py`
Shared user-facing disclosure text rendered by more than one service. Exports
module-level constants (not functions/classes, so not part of the
machine-checked list above): `METHODOLOGY_FACTS`/`METHODOLOGY_INTRO` -- the
four-fact statement of the leakage-aware validation protocol, rendered by
`dashboard-web`'s run-detail methodology panel and by `reporting-service`'s
audit report -- and `NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE` (TRUST-005) --
one sentence, appended by both services only when a real client model was
submitted and evaluated and did not beat Naive0 on any split. See "Shared
disclosure text (TRUST-001)" below.

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

## Recent-errors ring buffer (SETUP-021)

`naive_first_common.diagnostics.RecentErrorsHandler` is a `logging.Handler`
(the standard library's own Observer-pattern hook into the `logging` module's
event stream) that both `gateway-api` and `dashboard-web` attach to the root
logger *alongside* -- not replacing -- OPS-006's existing JSON-formatter/
correlation-id handler. It keeps a bounded, in-process `collections.deque`
(default `maxlen=50`) of `WARNING`-and-above records only (via the handler's
own `setLevel(logging.WARNING)`, the standard library's own filtering
mechanism -- no manual level check in `emit()`). Each buffered entry is a
plain dict: `timestamp`, `level`, `logger`, `message` (the already-formatted
string, `record.getMessage()`), `correlation_id`. It never captures
`record.exc_info`/`record.exc_text` (a raw traceback), a request body, or any
secret value. `.snapshot()` returns the buffer most-recent-first as a plain
list copy (never a live reference to the internal deque). Each service
exposes its own buffer via its own operator-authenticated
`/diagnostics/recent-errors` endpoint -- see each service's own README for
that wiring. This is not a log-aggregation backend: no cross-restart
persistence, no cross-service search (still `OPS-007`'s declined scope).

## Typed `dataset_reference` schema (UAT-007)

`contracts.py`'s `RunRequest.dataset_reference` field was `dict` (published in `GET /openapi.json` as
bare `additionalProperties: true`). It is now `DatasetReferenceType` (`Annotated[dict, WithJsonSchema(...)]`)
-- the field's actual runtime/validation type is still plain `dict`, so no call site anywhere (`dataset_source.py`'s
`isinstance(reference, dict)` checks, `validation-service`'s `runs.py`, `dashboard-web`'s `run_new_submit`)
needed to change and no request previously accepted is now rejected. Only the *published* OpenAPI schema
changed: `WithJsonSchema` replaces it with a real `anyOf` over four named, self-contained shapes, each with
at least one example --`PathDatasetReference` (`{"path": str}`), `InlineDatasetReference` (`{"inline": dict}`),
`StoredDatasetReference` (`{"source": str, start?, end?, field?}`, ADR-0005/DASH-108), and
`ObjectKeyDatasetReference` (`{"object_key": str}`, VS-015) -- the fourth shape not named in UAT-007's own
Analysis/Design but included because `dataset_source.py`'s `CompositeDatasetSource` already dispatches on it
today; omitting it from the published schema would have misrepresented a currently-accepted request shape as
unsupported. **Version-sync convention followed**: `RunRequest` has had exactly one canonical definition
since ARCH-003 (this module) -- `gateway-api` imports it directly from `naive_first_common.contracts` rather
than keeping a separate local copy, so this ticket required no second, hand-mirrored edit in `gateway-api`
(the ticket's own Analysis section predates that unification and describes a mirror that no longer exists).

## Optional run label (UAT-008)

`RunRequest` gained an optional `label: str | None = Field(default=None, max_length=200)` field --
a freeform, tenant-supplied name a run can be submitted with (e.g. "weekly audit"), never consulted
by the leakage-aware validation/split logic (pass-through only). `RunDetailResponse`/
`RunSummaryResponse` both gain a matching `label: str | None = None` so it round-trips back on
`GET /runs`/`GET /runs/{id}` once `validation-service` persists it. **Version-sync convention**:
same "one canonical definition" convention UAT-007 already established for `RunRequest` -- `gateway-api`
imports these classes directly from `naive_first_common.contracts` (no local mirror to update in sync),
so this field required no second, hand-mirrored edit in `gateway-api`.

## Per-run engine/config fingerprint (TRUST-003)

`RunDetailResponse` gained two optional fields: `engine_version: str | None = None` and
`config_fingerprint: str | None = None` -- the installed `naive_first_engine` distribution version and a
SHA-256 fingerprint of the run's `split_config`, both computed and persisted by `validation-service` at
`create_run` time (`services/validation-service/src/app/fingerprint.py`), never by this library. Same
defensive-default precedent `warnings`/`label` already established: a `None` here is deliberately
ambiguous between two honest cases -- "not yet computed, because a rolling deploy served this response
from a `validation-service` instance that omitted the field temporarily" (a wire-contract-compatibility
null, transient) and "this run row predates migration `0012`, so the value was never computed at all" (a
migration-boundary null, permanent). Both are equally "not a real value" from this contract's point of
view; distinguishing them, if ever needed, is `validation-service`'s own concern (its `runs.engine_version`/
`config_fingerprint` columns), not something `RunDetailResponse` encodes. **Version-sync convention**: same
"one canonical definition" convention UAT-007/UAT-008 already established -- `gateway-api` imports
`RunDetailResponse` directly from `naive_first_common.contracts`, so this field required no second,
hand-mirrored edit there.

## Shared disclosure text (TRUST-001, TRUST-005)

`naive_first_common.disclosures.METHODOLOGY_FACTS` is the platform's one statement of the
leakage-aware validation protocol (rolling-origin walk-forward, the purge gap, the mandatory
Naive0/NaiveLast comparison, and the Diebold-Mariano test with the Harvey et al. (1997) correction).
It is rendered by `dashboard-web`'s run-detail methodology panel and by `reporting-service`'s audit
report, and lives here because those two surfaces must never tell a tenant different things about how
their model was validated.

`naive_first_common.disclosures.NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE` (TRUST-005) is one additional
sentence, additive to the existing "did not beat naive" verdict language in both services (never a
replacement for it), rendered only when a real client model was submitted and evaluated (`has_client_model
== True` in `dashboard-web`, and the equivalent condition in `reporting-service`'s render context) and did
not beat Naive0 on any split (`better_count == 0`). It is never rendered for the `has_client_model=False`
placeholder case in either service -- there is no real model to frame as "expected not to beat naive" when
no client model was submitted. Same shared-constant/drift-guard mechanism as `METHODOLOGY_FACTS` below.

This is CLAUDE.md's DRY rule applied literally -- cross-module duplication is pulled into a `libs/*`
package, never copy-pasted across service boundaries. The neighbouring no-cross-service-import rule
forbids one *service* importing another service's code, which is a different constraint and precisely
what this package exists to satisfy.

**Drift guard**: the exact-text assertion for each constant lives once, in `tests/test_disclosures.py`.
Each consuming service asserts only *identity* with the constant (`... is METHODOLOGY_FACTS`, `... is
NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE`), never a second copy of the literal text -- so a service
re-defining the text locally fails its own test even if the wording happens to match. Editing a fact here
is therefore a deliberate one-line change that fails this library's test until the expected text is
updated alongside it.

**History**: TRUST-001-01/02 originally copy-pasted the methodology tuple into both services, each with a
"same-text test" comparing its copy against another literal in its own test file. That guard could not
detect the failure it was written for -- nothing cross-checked the two services, so editing one service's
wording left the other silently stale. TRUST-005-01/02's own tickets, as originally written, specified the
same per-service-copy-plus-same-text-test shape for `NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE` -- corrected
before implementation to use this shared-constant mechanism from the start, rather than repeating the
mistake a second time.

## CI

**CI**: `.github/workflows/ci.yml` runs this module's test suite on every push/PR.

**Coverage**: run tests with coverage locally via `uv run pytest -q --cov=naive_first_common --cov-report=term-missing` (no coverage threshold is enforced -- CI prints the report, it never fails the build on a percentage).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.
