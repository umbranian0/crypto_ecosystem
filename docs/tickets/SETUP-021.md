# SETUP-021 — Recent-errors visibility (in-process ring buffer)

**Sprint**: 32. **Modules**: `services/gateway-api` AND `services/dashboard-web` (two disjoint
sub-scopes within one ticket ID, per the sprint's instruction to reuse exact backlog IDs — implemented
as two separate dev-agent dispatches, one per module, since implementation-plan.md section 3 scopes a
ticket to one module's files). **Status**: done. **Priority**: Should.
**Depends on**: `SETUP-010` (done), `OPS-006` (done, structured JSON logging).
**Sequence note**: land after `SETUP-011` merges (both touch `gateway-api`'s `src/app/main.py`'s
router-registration list — avoid a same-file collision by sequencing, not parallelizing, those two
edits). Can run in parallel with `SETUP-012`/`SETUP-015` (disjoint dashboard-web files: this ticket
touches `operator.py`/`monitoring.html`, those touch `settings_tenants.py`/`settings_environment.py`).
Land before `SETUP-022`, which touches the same `monitoring.html`/`operator.py` files.

## Analysis

Backlog `SETUP-021`: each service adds an in-process ring-buffer `logging.Handler` (last 50
`WARNING`+ records), a new operator-authenticated `/diagnostics/recent-errors` endpoint per service,
and `/monitoring` renders these per service, most-recent first. Explicitly disclosed limitations: no
cross-restart persistence, no cross-service search UI — this is not `OPS-007`'s (declined)
log-aggregation scope.

**DRY constraint** (`implementation-plan.md` section 9, restated in the sprint's own dependency note):
reuse `OPS-006`'s existing JSON formatter/correlation-id convention via one *additional* `logging.Handler`
attached alongside the existing structured-logging setup — not a second logging system, and not a
second `Formatter`/`basicConfig` call anywhere.

**Status: done.** `libs/common`'s `RecentErrorsHandler` (+ `.clear()` test-isolation helper) and both
services' `/diagnostics/recent-errors` endpoints were already correctly implemented and tested before
this closing pass. This pass completed the missing piece: `dashboard-web`'s `/monitoring` route now
calls `_fetch_gateway_api_recent_errors` and renders both services' buffers in `monitoring.html`. A real
bug was found and fixed during this pass: an initial draft wired the gateway-api call to the tenant
session header (`OptionalDownstreamHeadersDep`), which would have silently 401'd against a real
gateway-api since that endpoint requires `X-Operator-Token`, not a tenant `Authorization: Bearer`
header -- fixed by adding `OptionalOperatorTokenHeaderDep` (`operator_session.py`) and wiring the panel
to it instead. See Review section below.

## Design

**Pattern**: Observer — a `logging.Handler` is itself an observer of the standard `logging` module's
event stream; this ticket adds one additional observer (the ring buffer) without touching the
existing JSON-formatter observer `OPS-006` already registered. This is the one place in this sprint
implementation-plan.md section 7's Observer pattern entry genuinely applies.

### Sub-scope A — `libs/common` shared ring-buffer handler (new, tiny, no I/O)

Both services need the *same* ring-buffer behavior — per the DRY rule, this is exactly the "cross-
module duplication gets pulled into a `libs/*` package" case implementation-plan.md section 9
describes, not two independent per-service implementations.
- `libs/common/src/naive_first_common/diagnostics.py` (new): `RecentErrorsHandler(logging.Handler)` —
  a bounded `collections.deque(maxlen=50)` of dicts (`timestamp`, `level`, `logger`, `message`,
  `correlation_id`), populated in `emit()` from the `LogRecord` (reusing whatever correlation-id
  attribute `OPS-006`'s existing filter already attaches to each record — read
  `naive_first_common/logging.py` first to confirm the exact attribute name, don't guess it). Only
  `WARNING`+ records are appended (set via `setLevel(logging.WARNING)` on the handler, the standard
  library's own filtering mechanism — no manual level check duplicated in `emit()`). **Never includes
  a raw exception traceback, request body, or any secret** — `message` is `record.getMessage()`
  (the formatted string), never `record.exc_info`/`record.exc_text`. Exposes `.snapshot() -> list[dict]`
  returning the buffer most-recent-first (a plain list copy, not a live reference to the internal
  deque). Exported from `naive_first_common/__init__.py` alongside the existing
  `configure_structured_logging`/`CorrelationIdMiddleware` exports.
- `libs/common` has no I/O and no FastAPI dependency (per its own README/implementation-plan.md
  section 3) — this handler is pure `logging` + `collections`, satisfying that constraint.

### Sub-scope B — `gateway-api`

- `src/app/main.py` — after `configure_structured_logging()`, instantiate one
  `naive_first_common.RecentErrorsHandler()` module-level singleton and
  `logging.getLogger().addHandler(recent_errors_handler)` (attached to the root logger, so it observes
  every service log call, the same scope `OPS-006`'s own formatter/filter already have) — no change to
  the existing formatter/filter registration.
- `src/app/dependencies/diagnostics.py` (new) — a `Depends()` provider exposing the same module-level
  handler instance to a route (mirrors `operator_session.py`'s module-level-singleton-behind-a-provider
  pattern already established in `dashboard-web`, applied here).
- `src/app/routers/diagnostics.py` (new module): `GET /diagnostics/recent-errors`
  (`get_authenticated_operator`, `SETUP-010`) returns `{"items": handler.snapshot()}`.
- `src/app/main.py` — `app.include_router(diagnostics.router)`, no `tags=` (ARCH-007, same reasoning as
  `setup.router`).
- `services/gateway-api/README.md` — new "Recent-errors ring buffer (SETUP-021)" section.

### Sub-scope C — `dashboard-web`

- `src/app/main.py` — same handler-attachment pattern as gateway-api's `main.py` change above (check
  `dashboard-web`'s own `main.py` for where `configure_structured_logging()` is called first).
- `src/app/dependencies/diagnostics.py` (new, mirrors gateway-api's shape) — module-level singleton +
  provider.
- `src/app/routers/operator.py` — **extend** this existing module (not a new one — this ticket's own
  file-overlap note names this file explicitly) with `GET /diagnostics/recent-errors`
  (`require_operator_session`, `DASH-113`'s existing gate — reused, not a new auth mechanism) returning
  this service's own buffer.
- `src/app/routers/operator.py`'s `monitoring()` — after fetching `/system/health`, also call
  `gateway-api`'s new `GET /diagnostics/recent-errors` (`OptionalDownstreamHeadersDep`-gated the same
  way the crawl-status panel is, since an anonymous visitor sees no per-service error detail) **and**
  this service's own local buffer directly (no HTTP call needed for `dashboard-web`'s own errors — it's
  in-process). Pass both into the template context as `recent_errors: {service_name: [items]}`.
- `src/app/templates/monitoring.html` — new "Recent errors" section, one sub-list per service,
  most-recent first, reusing the same `<table>`/`<div class="table-scroll">` conventions the health
  table already uses. Land this section addition **before** `SETUP-022`'s own template addition (per
  the sprint's file-overlap note) so `SETUP-022` starts from this ticket's already-merged state.
- `services/dashboard-web/README.md` — new "Recent-errors panel on /monitoring (SETUP-021)" section.

**DRY check note**: `RecentErrorsHandler` is written once in `libs/common`, imported by both services
— not two independent per-service ring-buffer implementations. `dashboard-web`'s
`OptionalDownstreamHeadersDep`/`_call_downstream`/`require_operator_session` are all reused unmodified.

## Implementation acceptance criteria

- [x] Both services attach one additional `RecentErrorsHandler` to the root logger, alongside (not
  replacing) `OPS-006`'s existing formatter/filter.
- [x] `GET /diagnostics/recent-errors` (operator-authenticated per each service's own existing
  mechanism) returns the last 50 `WARNING`+ records, most-recent first, each with
  `timestamp`/`level`/`logger`/`message`/`correlation_id` — never a raw traceback, request body, or
  secret value.
- [x] `/monitoring` renders both services' recent-error lists, most-recent first, with the buffer's
  disclosed limitations (no cross-restart persistence, no cross-service search) stated in the page
  copy, not silently omitted.
- [x] No alerting/paging behavior is added anywhere in this ticket — a list on a page only.

## Test acceptance criteria

- [x] `libs/common/tests/test_diagnostics.py` (new): buffer caps at 50, drops oldest first, only
  `WARNING`+ captured (an `INFO` call never appears), `snapshot()` returns most-recent-first and never
  includes `exc_info`/traceback text even when the log call included `exc_info=True`.
- [x] `services/gateway-api/tests/test_diagnostics.py` (new): unauthenticated → `401`/`403` per
  `get_authenticated_operator`'s existing behavior; a real tenant API key → `403` (the same
  cross-boundary guarantee `SETUP-010` established); authenticated → returns emitted `WARNING`+
  records from a test-triggered log call, and an `INFO` call from the same test never appears.
- [x] `services/dashboard-web/tests/test_operator_diagnostics.py` (new): mirrors the gateway-api test
  shape for this service's own endpoint and gate.
- [x] `services/dashboard-web/tests/test_monitoring.py` extended: mocks gateway-api's
  `/diagnostics/recent-errors` response and asserts it renders on `/monitoring`.
- [x] Full test suites for `libs/common`, `services/gateway-api`, `services/dashboard-web` run, zero
  regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads `RecentErrorsHandler.emit()` directly, confirms no traceback/request-body/secret field is ever
  captured.
- Confirms the handler is attached to the root logger without disturbing `OPS-006`'s existing
  formatter/filter registration (reads both services' `main.py` diffs directly).
- Confirms `/diagnostics/recent-errors` on both services is gated by each service's existing operator
  mechanism — no new, weaker auth path invented.
- Confirms `monitoring.html`'s new section is additive and does not alter the existing health-table or
  crawl-status-panel markup/behavior.
- Re-runs all three affected suites, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/gateway-api/README.md` and `services/dashboard-web/README.md` each get a
  "Recent-errors ring buffer (SETUP-021)" section documenting the buffer size, retention (none across
  restart), and the endpoint/page.
- [x] `libs/common`'s README (if one exists covering `naive_first_common`'s exports) notes the new
  `RecentErrorsHandler` export.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-021` acceptance boxes checked, status
  marked done, citing this ticket.

## Review (Tech Lead, this closing pass)

- `RecentErrorsHandler.emit()` (`libs/common/src/naive_first_common/diagnostics.py`) reads only
  `record.getMessage()` for `message`, never `exc_info`/`exc_text` — confirmed by direct read.
- Both `gateway-api/src/app/main.py` and `dashboard-web/src/app/main.py` attach the handler to the root
  logger after `configure_structured_logging()`, without touching the existing formatter/filter —
  confirmed by direct diff read.
- Both `/diagnostics/recent-errors` endpoints are gated by each service's own existing operator
  mechanism (`get_authenticated_operator` on gateway-api, `require_operator_session` on dashboard-web) —
  no new auth path.
- **Bug found and fixed during review**: the first implementation of `dashboard-web`'s `monitoring()`
  wired the gateway-api recent-errors fetch to the *tenant* session header
  (`OptionalDownstreamHeadersDep`), which would never satisfy gateway-api's operator-only gate against a
  real deployment (only worked in tests because the mock transport doesn't check headers). Fixed by
  adding `OptionalOperatorTokenHeaderDep` to `operator_session.py` and rewiring the panel to it, plus a
  regression test (`test_monitoring_recent_errors_gateway_api_does_not_populate_from_a_tenant_session_alone`)
  and a positive test using a real operator session cookie
  (`test_monitoring_recent_errors_gateway_api_populated_for_logged_in_operator`).
- `monitoring.html`'s new "Recent errors" section is additive; existing health-table/crawl-status-panel
  markup unchanged (confirmed by direct template diff read).
- Suites re-run after the fix: `libs/common` 37 passed; `services/gateway-api` 200 passed (untouched by
  this ticket); `services/dashboard-web` 274 passed, 7 deselected (Selenium E2E). Zero regressions.
