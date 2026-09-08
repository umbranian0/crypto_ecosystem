# DASH-121 — Fix silent 5s httpx timeout on 13 ad-hoc `httpx.Client(base_url=...)` call sites

**Module**: `services/dashboard-web`. **Depends on**: none — same-pass production bug fix, per the
DASH-119/DASH-120 precedent (fix immediately rather than only file the ticket).

## Analysis

Live bug-hunt sweep (Orchestrator PM) reproduced a real, user-facing failure: logging into
dashboard-web and clicking "Generate a report" (`POST /monitoring/reports/generate`) for a real
completed run returned an HTTP `504` ("Unavailable") after ~5 seconds, while gateway-api's own logs
show the downstream `reporting-service` call completing successfully (`201 Created`) a few seconds
later — the report genuinely was generated, but the operator was shown a false failure.

Root cause: `services/dashboard-web/src/app/dependencies/http_client.py`'s `Depends()`-injectable
clients (e.g. `get_gateway_api_client`, line 26) are correctly built with `timeout=30.0`. But a
second, ad-hoc pattern used directly inside router handlers instantiates
`httpx.Client(base_url=base_url)` with **no** `timeout=` argument at all, which silently falls back
to httpx's library default of 5.0s (connect/read/write/pool each capped independently at 5s) —
bypassing the properly-configured 30s budget entirely. Grepped, confirmed 13 call sites, all missing
`timeout=`:

- `routers/operator.py` — lines 297, 339, 382, 423, 458 (`monitoring`, `crawl_status_fragment`,
  `trigger_crawl`, `cancel_crawl`, `trigger_report_generation` — the last is the one that surfaced
  the bug live)
- `routers/runs.py` — lines 451, 478, 511, 556, 623, 708, 774 (`runs_list`, `datasets_list`,
  `runs_horizon_summary`, `run_new_form`, `run_new_submit`, `runs_trend`, `run_detail`)
- `routers/settings.py` — line 84 (`connectors_credentials_status`)

Direct in-container repro (bypassing dashboard-web, calling gateway-api directly with a 60s client
timeout) confirms real report generation genuinely takes ~7-9 seconds end to end — well inside the
*intended* 30s budget, but past the *accidental* 5s one. Net effect: any of these 13 sites' downstream
calls that legitimately exceed 5s (confirmed for report generation; plausible for a slow crawl
trigger or run submission, or gateway-api under transient load) show the user a false "Unavailable"
result even though the operation succeeded server-side — a correctness/trust bug (duplicate report
submissions, users believing a submitted run/crawl failed when it didn't), not cosmetic.

CLAUDE.md/implementation-plan.md constraint: no service reads another service's schema — this ticket
does not touch that boundary at all, it is a pure HTTP-client-configuration bug inside
`dashboard-web`'s own router layer.

## Design

**Pattern**: none of implementation-plan.md section 7's listed patterns are being newly introduced —
this is a DRY-config fix, not a new architectural seam. `http_client.py`'s existing `Depends()`
providers are the module's single already-established "properly configured client" source of truth;
the fix must make the 13 ad-hoc sites consistent with that value, not invent a second, differently-
tuned timeout.

**Files touched** (scoped to `services/dashboard-web` only):
- `services/dashboard-web/src/app/dependencies/http_client.py` — export one new module-level constant,
  `DOWNSTREAM_HTTP_TIMEOUT_SECONDS = 30.0`, and have `get_gateway_api_client` (and any sibling
  provider in this file) reference it instead of the literal `30.0`, so there is exactly one place
  this number lives.
- `services/dashboard-web/src/app/routers/operator.py`, `routers/runs.py`, `routers/settings.py` —
  each of the 13 `httpx.Client(base_url=base_url)` call sites becomes
  `httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS)`, importing the constant
  from `app.dependencies.http_client`.
- `services/dashboard-web/tests/test_monitoring_triggers.py` or a new/existing test file with an
  httpx `MockTransport` pattern already in use in this test suite — add a slow-response regression
  test.
- `services/dashboard-web/README.md` — short fix note.

**DRY check note** (grepped `httpx.Client(base_url=` across `services/dashboard-web/src/app` before
writing this ticket): confirmed exactly 13 matches, all in `routers/operator.py` (5), `routers/runs.py`
(7), `routers/settings.py` (1) — no 14th site missed, no site already correctly timed out. The fix
reuses `http_client.py`'s already-chosen `30.0` value (a single new named constant), rather than
duplicating the literal `30.0` thirteen more times or inventing a distinct value — the exact
same-module DRY convention this repo's `implementation-plan.md` section 9 requires ("extract on
second duplication").

## Implementation acceptance criteria

- [x] `http_client.py` defines `DOWNSTREAM_HTTP_TIMEOUT_SECONDS = 30.0` at module level and
      `get_gateway_api_client` uses it (no bare `30.0` literal left in that function).
- [x] All 13 call sites listed above pass `timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS` explicitly —
      zero remaining bare `httpx.Client(base_url=base_url)` calls anywhere under
      `services/dashboard-web/src/app` (grep-verifiable).
- [x] No other already-correctly-configured client (`get_gateway_api_client` itself, and any other
      `Depends()`-based provider in `http_client.py`) has its timeout value changed.

## Test acceptance criteria

- [x] A new or extended test proves the regression is fixed: a mocked downstream response with an
      artificial delay between the old 5s default and the new 30s budget (e.g. 6-8s, via a
      `MockTransport`/fake handler with a controllable `time.sleep` or async delay, reusing whatever
      mock-transport pattern this test suite already uses for these routers) confirms the affected
      route (`trigger_report_generation`, the one that surfaced this live) completes successfully
      rather than raising `httpx.TimeoutException`/rendering the "Unavailable" error page.
- [x] `uv run pytest -q` in `services/dashboard-web` run in full, zero regressions vs. the pre-fix
      baseline count.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Grep confirms zero remaining `httpx.Client(base_url=base_url)` calls without an explicit
      `timeout=` anywhere in `services/dashboard-web/src/app`.
- [x] Read the diff directly: every one of the 13 sites uses the same imported
      `DOWNSTREAM_HTTP_TIMEOUT_SECONDS` constant (not 13 independent `timeout=30.0` literals) and no
      already-correct client's configured timeout changed.
- [x] Full test suite re-run directly by the Tech Lead (not merely trusted from the dev agent's own
      report).
- [x] Live-stack verification: with dashboard-web restarted/reloaded picking up the fix, repeat the
      exact live repro (log in, trigger report generation for a real completed run) and confirm it now
      returns `201`/renders the success fragment instead of `504`, with the actual observed timing
      recorded.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gains a short note (fix log / status line) documenting this
      bug and its fix: the 13 ad-hoc `httpx.Client` call sites now share the same 30s timeout as the
      `Depends()`-based clients, via `DOWNSTREAM_HTTP_TIMEOUT_SECONDS`.
