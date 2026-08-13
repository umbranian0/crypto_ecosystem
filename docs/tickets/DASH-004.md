# DASH-004 — Run detail view (status + per-split results)

**Status: done**

## Analysis
Story: DASH-004 (Must), depends on DASH-003. Backlog acceptance criteria: calls `GET /runs/{id}` and
renders `id, status, dataset_id, horizon, purge_gap_hours, created_at, completed_at, failure_reason`
(confirmed field set, `GW-008`); if splits exist, calls `GET /runs/{id}/splits` and renders each
split's boundaries, model/naive0 metrics (mae/rmse/smape/mase/da/f1/oos_r2), and
`dm_statistic/dm_pvalue/dm_verdict` verbatim — no recomputation/reinterpretation (`NFE-012`'s Harvey
correction already applied upstream); no language implying price prediction or trading signal
(CLAUDE.md positioning) — validation/audit framing only; gateway-api's `404` (nonexistent or
cross-tenant, both collapsed upstream) renders a plain "not found" page, no distinction shown;
gateway-api's `502`/`504` render a generic "results currently unavailable" message, no leaked
internals; tests per backlog AC6.

**Exact field set, confirmed directly, not guessed**: read `docs/tickets/GW-008.md` and
`libs/common/src/naive_first_common/contracts.py` directly this session (ARCH-003 superseded
GW-008's original field-for-field-copy design — `gateway-api`'s `runs.py` now imports
`RunDetailResponse`/`SplitResultResponse` from `naive_first_common.contracts`, not a local copy).
`RunDetailResponse`: `id, tenant_id, dataset_id, horizon, purge_gap_hours, split_config, status,
created_at, completed_at, failure_reason`. `SplitResultResponse` (one list entry): `split_index,
train_start, train_end, purge_start, purge_end, test_start, test_end, model_mae, model_rmse,
model_smape, model_mase, model_da, model_f1, model_oos_r2, naive0_mae, naive0_rmse, naive0_smape,
naive0_mase, naive0_da, naive0_f1, naive0_oos_r2, dm_statistic, dm_pvalue, dm_verdict`. Render these
fields only — no invented field (the backlog's own field list for `GET /runs/{id}` omits
`tenant_id`/`split_config` from what must be *rendered*, but they are present on the response; do not
render `tenant_id` on the page — a tenant viewing their own run does not need their own id echoed
back, and rendering it needlessly increases the surface exposed in the HTML for no product value).

## Design
Pattern: **Dependency Injection** only (`DownstreamHeadersDep`/`GatewayApiUrlDep` from DASH-003) — no
Strategy/Factory/Adapter applies to a read-only detail view. Files: `src/app/routers/runs.py` (new),
`src/app/templates/run_detail.html` (new, extends `base.html`), `src/app/templates/not_found.html`
(new, generic — reused by DASH-004's 404 case; do not create a second near-identical template later),
`src/app/templates/error.html` (new, generic — reused by DASH-004's 502/504 case and *must* be reused
by DASH-006's own transport-failure handling rather than duplicated, per implementation-plan.md
section 9's DRY rule).

Handler flow: `GET /runs/{id}` -> resolve `headers: DownstreamHeadersDep`, `base_url:
GatewayApiUrlDep` -> `httpx.get(f"{base_url}/runs/{id}", headers=headers)` -> on `200`, parse into
`naive_first_common.contracts.RunDetailResponse` (imported, not a fourth hand-copy of the field list
— DASH-001's Design section already flagged this as the reason `naive_first_common` is a real
dependency) -> if `status` indicates the run has produced results (i.e. splits may exist — do not
gate the splits call on a specific status string like `"completed"`; call `GET /runs/{id}/splits`
unconditionally after a successful detail fetch and render an empty-splits state if the list comes
back empty, since a `"running"` run legitimately has zero splits yet and the backlog's own AC2 says
"if splits exist" — let the splits endpoint's own response, not a client-side status guess, decide
whether any exist) -> parse each entry into `SplitResultResponse` -> render `run_detail.html` with
both. On `404` from `GET /runs/{id}`, render `not_found.html` (no distinction between
nonexistent/cross-tenant, matching gateway-api's own collapsed behavior — do not add a different
message for either case, since gateway-api itself provides no way to tell them apart). On
`httpx.ConnectError`/`httpx.TimeoutException` or a `502`/`504` status from gateway-api, render
`error.html` with the fixed generic string "results currently unavailable" — no hostname, status
code detail, or exception text in the rendered page.

**Positioning language, checked explicitly**: `run_detail.html`'s copy must describe the shown
numbers as "validation results" / "benchmark comparison" / "per-split metrics," never "prediction,"
"forecast," "signal," or "recommendation" — grep the finished template for those banned words as part
of this ticket's own self-check before handing back for review (CLAUDE.md's core positioning
constraint, checked here since this is the first template that renders real model output).

DRY check: grepped `src/app/templates/` (only `base.html` exists, DASH-001) and
`src/app/dependencies/` (DASH-002's `session.py`, DASH-003's `downstream.py`) before writing — no
existing gateway-api-calling code to reuse yet; this ticket and DASH-006 are the first two real
consumers of DASH-003's seam.

**Implementation deviation from the literal `httpx.get(...)` call shown above (disclosed, not
silent)**: `httpx`'s module-level `get()` function does not accept a `transport=`/mock-transport
parameter (confirmed directly against the installed `httpx==0.27`/`0.28`-family API surface — its
signature is `params, headers, cookies, auth, proxy, follow_redirects, verify, timeout, trust_env`
only), so it cannot be exercised via `httpx.MockTransport` the way this ticket's own Test acceptance
criteria requires. `src/app/routers/runs.py` instead opens `httpx.Client(base_url=base_url)` per
request (still built from `base_url: GatewayApiUrlDep`, still one GET per call, same headers/timeout
semantics) and calls `.get(path, headers=headers)` on it — functionally identical to the design's
intent (a single outbound `GET` to `{base_url}{path}` carrying `headers`), just structured as a
`Client` method call instead of the bare module function so the test suite can substitute a
`MockTransport`-backed client. Tests wire this in by monkeypatching `httpx.Client` itself (not a new
DI seam) to a factory that preserves `base_url` but swaps in `httpx.MockTransport(handler)`.

## Implementation acceptance criteria
- [x] `GET /runs/{id}` renders `run_detail.html` with `id, status, dataset_id, horizon,
  purge_gap_hours, created_at, completed_at, failure_reason` from `RunDetailResponse`.
- [x] Splits (if any come back from `GET /runs/{id}/splits`) render each split's boundaries, both
  baselines' full metric sets, and `dm_statistic/dm_pvalue/dm_verdict` verbatim, no recomputation.
- [x] `404` from `gateway-api` renders `not_found.html`, no distinction between "doesn't exist" and
  "belongs to another tenant."
- [x] `502`/`504` (or a transport-level `httpx` connect/timeout error) renders `error.html`, fixed
  generic "results currently unavailable" string, no leaked hostname/status/exception text.
- [x] No route in this ticket hand-rolls its own `Authorization` header — uses `DownstreamHeadersDep`
  exclusively (DASH-003).
- [x] Templates contain no price-prediction/trading-signal language anywhere (self-checked by grep
  before handoff, re-checked by the Tech Lead at review).

## Test acceptance criteria
- [x] `tests/test_runs_detail.py` (mocked `gateway-api` via `httpx.MockTransport`, mirroring
  `gateway-api`'s own `tests/test_runs_routing.py` mocking approach): success-with-splits case;
  running-with-no-splits case (splits endpoint returns `[]`); `404` case; `502`/`504` case (both,
  separately).
- [x] Run via `.venv\Scripts\python.exe -m pytest -q` (or `uv run pytest`), confirm pass, paste output.

Actual output (2026-08-12, from `services/dashboard-web`):
```
.....................                                                    [100%]
============================== warnings summary ===============================
.venv\lib\site-packages\fastapi\testclient.py:1
  ...: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
21 passed, 1 warning in 1.32s
```
(21 = 9 new `test_runs_detail.py` tests + 12 pre-existing DASH-002/003 tests, full suite run to
confirm no regression.)

## Review acceptance criteria
- [x] Tech Lead confirms field set against `docs/tickets/GW-008.md` and
  `libs/common/src/naive_first_common/contracts.py` directly (not from memory) — no invented field
  rendered, no field silently dropped from what the backlog requires; confirms `run_detail.html`
  contains none of the banned prediction/signal words via direct grep; confirms the 404/502/504
  templates leak no internal detail by reading their actual rendered output in a test.

**Tech Lead review (2026-08-12)**: read `runs.py`, `run_detail.html`, `not_found.html`, `error.html`,
`test_runs_detail.py` end to end. Field set matches `RunDetailResponse`/`SplitResultResponse`
exactly, no invented/dropped field; `tenant_id`/`split_config` correctly not rendered. Confirmed
`run_detail.html` contains none of "prediction"/"forecast"/"signal"/"recommendation" via direct grep
(also enforced by the dev agent's own `test_run_detail_template_has_no_banned_positioning_words`
test). `not_found.html`/`error.html` are generic/reusable, leak no hostname/status/exception text
(confirmed via `test_run_detail_502_from_gateway_api`/`test_run_detail_transport_connect_error`
asserting the raw upstream detail string is absent from the response body). Accepted the disclosed
`httpx.Client`-per-request deviation from the literal `httpx.get(...)` Design text — correct call:
`httpx.get()` genuinely has no mock-transport parameter, and the substitute preserves the same
`base_url`/headers/single-GET-per-call semantics. Re-ran the suite independently:
`.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web` -> **21 passed**, 0 failed,
matching the dev agent's reported output exactly.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` gains a short line under "Contract" confirming this route
  consumes `GET /runs/{id}` and `GET /runs/{id}/splits` via the shared `naive_first_common.contracts`
  models, and that a version-sync caveat applies if those models change (mirrors `gateway-api`'s own
  GW-008 documentation caveat).

## Outcome
Implemented as designed with one disclosed deviation (see Design section's "Implementation deviation"
note): the literal `httpx.get(...)` call could not be used because `httpx`'s module-level `get()`
does not accept a mock transport, which the ticket's own Test acceptance criteria requires
(`httpx.MockTransport`). Used a per-request `httpx.Client(base_url=base_url)` instead, same base_url
source (`GatewayApiUrlDep`), same headers source (`DownstreamHeadersDep`), same single-GET-per-call
semantics.

Files created: `services/dashboard-web/src/app/routers/runs.py`,
`services/dashboard-web/src/app/templates/run_detail.html`,
`services/dashboard-web/src/app/templates/not_found.html`,
`services/dashboard-web/src/app/templates/error.html`,
`services/dashboard-web/tests/test_runs_detail.py`.

Files modified: `services/dashboard-web/src/app/main.py` (mounted `runs.router`),
`services/dashboard-web/README.md` (Contract section + new "Run detail (DASH-004)" section).

All Implementation/Test/Documentation/Review acceptance criteria met and checked off above.
