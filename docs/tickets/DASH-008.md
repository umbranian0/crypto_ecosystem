# DASH-008 — Health check endpoint

**Status: done**

## Analysis
Story: DASH-008 (Should), depends on DASH-001 only. Backlog acceptance criteria: real check (e.g. a
request to gateway-api's `/health`), not hardcoded `ok`, matching `OPS-005-01`/`OPS-005-02`'s
precedent; success `200 {"status":"ok"}`; failure `503 {"status":"unhealthy","detail":"gateway-api
unreachable"}`, fixed generic string.

## Design
Pattern: none beyond a plain `httpx` call — no DI seam needed here (this route is deliberately
*unauthenticated*, since an operator/orchestrator health-checking `dashboard-web` has no tenant
session; do not put this route behind `DownstreamHeadersDep`, which would make health checks fail for
the wrong reason). File: `src/app/main.py` (edited — adds the `/health` route directly, same file
gateway-api's and validation-service's own `/health` handlers live in, per their precedent).

Handler: `GET /health` -> `httpx.get(f"{GATEWAY_API_URL}/health", timeout=<short, e.g. 5s>)` -> on a
`200` response from gateway-api, return `200 {"status": "ok"}`; on any exception (connect error,
timeout) or a non-200 status from gateway-api, return `503 {"status": "unhealthy", "detail":
"gateway-api unreachable"}` — the fixed generic string, matching the exact body shape
`OPS-005-01`/`OPS-005-02` already established for the other two services (consistency across all
three services' health-check bodies, confirmed by reading `services/gateway-api/src/app/main.py`'s
`/health` handler directly before writing this one).

DRY check: grepped `src/app/main.py` (DASH-001's skeleton — no existing `/health` route to duplicate)
and both other services' `/health` handlers for the body-shape precedent to match (confirmed above).

## Implementation acceptance criteria
- [x] `GET /health` performs a real HTTP call to `GATEWAY_API_URL`'s `/health`, not a hardcoded
  response.
- [x] Success: `200 {"status": "ok"}`.
- [x] Failure (connect error, timeout, or non-200 from gateway-api): `503 {"status": "unhealthy",
  "detail": "gateway-api unreachable"}` — fixed string, no leaked hostname/exception text.
- [x] Route is unauthenticated — no `DownstreamHeadersDep`/session dependency attached.

## Test acceptance criteria
- [x] `tests/test_health.py` (mocked gateway-api): healthy case (`200`); unhealthy case (gateway-api
  mock returns non-200 or the mock transport raises a connect error) — both asserted against the
  exact response body shape above.
- [x] Run via `.venv\Scripts\python.exe -m pytest -q` (or `uv run pytest`), confirm pass, paste output.

## Review acceptance criteria
- [x] Tech Lead confirms the failure body is byte-identical in shape to
  `services/gateway-api`'s/`services/validation-service`'s own `/health` failure body (same three
  keys, same generic detail string style), and that the route requires no session/cookie.

**Tech Lead review (2026-08-12)**: read `main.py`'s new `/health` handler and `test_health.py` end to
end. Body shape (`{"status": "unhealthy", "detail": "gateway-api unreachable"}`, `503`) matches
gateway-api's own OPS-005-02 failure-body style (same three keys, fixed generic string); success body
`{"status": "ok"}` matches exactly. Confirmed no `DownstreamHeadersDep`/session dependency attached —
`test_health_requires_no_session` proves this non-tautologically (no cookie set anywhere in the test
file, asserts no 303 redirect). Confirmed `get_gateway_api_url()` (DASH-003) is reused for the base
URL, no second env var read. Re-ran the suite independently: `.venv\Scripts\python.exe -m pytest -q`
from `services/dashboard-web` -> **42 passed**, 0 failed, matching the dev agent's reported output
exactly. (Note: this ticket's first delegation attempt appears to have stalled with zero progress
after an extended wait; it was abandoned and re-delegated fresh, which completed normally in ~6
minutes, correctly preserving the concurrently-landing DASH-007 README section rather than clobbering
it.)

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` gains a short "Health check (DASH-008)" line describing the
  real gateway-api-connectivity check and the fixed failure body, matching `OPS-005-01`/`02`'s own
  README documentation style in the other two services.

## Outcome

Implemented `GET /health` directly in `src/app/main.py` (no new router file, per the ticket's own
Design section). Uses a plain `httpx.get(f"{get_gateway_api_url()}/health", timeout=5.0)` call
(`get_gateway_api_url` imported from `app.dependencies.downstream`, DASH-003 — not re-read via a
second env var name). On `200` from gateway-api returns `200 {"status": "ok"}`; any exception
(`httpx.ConnectError`/`httpx.TimeoutException`/other) or non-200 status is caught and collapsed into
`JSONResponse(503, {"status": "unhealthy", "detail": "gateway-api unreachable"})` — matching
`gateway-api`'s own `/health` handler's body-shape precedent read directly before writing this one.
No `DownstreamHeadersDep`/session dependency is attached to the route.

`tests/test_health.py` added (5 tests): success (`200`), non-200 from gateway-api (`503` mock,
asserts the real mock body `"database unreachable"` is not leaked into the response), transport
`ConnectError`, transport `TimeoutException`, and a no-session-required check (no cookie set in any
test in the file, and the route does not 303-redirect). Ran:

```
.venv\Scripts\python.exe -m pytest -q tests/test_health.py
.....                                                                    [100%]
5 passed, 1 warning in 2.96s
```

Full suite (all 42 dashboard-web tests, including auth.py's concurrently-added DASH-007 `/logout`
tests) also run and passing:

```
.venv\Scripts\python.exe -m pytest -q
..........................................                               [100%]
42 passed, 1 warning in 1.58s
```

`services/dashboard-web/README.md` updated with a new "Health check (DASH-008)" section (placed
after "Submit a run (DASH-006)", before "Local setup") and a corresponding "Design notes" bullet
under the existing DASH-008 entry, merged against the live file (which the concurrently-running
DASH-007 agent had also updated) rather than a stale cached copy, to avoid clobbering their section.

Tech Lead independent re-run (2026-08-12): 42 passed, 0 failed -- matches exactly.

All Implementation, Test, Review, and Documentation acceptance criteria met.
