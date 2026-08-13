# DASH-003 — Session-to-downstream-header dependency (DI seam)

**Status: done**

## Analysis
Story: DASH-003 (Must), depends on DASH-002. Backlog acceptance criteria: one `Depends()` dependency
resolving session -> API key -> outbound headers (DRY, mirrors `gateway-api`'s own
`build_downstream_headers` precedent — `src/app/dependencies/routing.py` there, confirmed by reading
`services/gateway-api/README.md`'s "Downstream header forwarding (GW-007)" section directly); no
route hand-rolls its own header — DASH-004/006/007 all go through this one dependency; a request with
no valid session is rejected here, before route logic runs; unit test confirms header shape and that
unauthenticated requests never reach route logic.

This is the DRY-enabling seam every later route depends on (sprint-11.md's handoff note) — get the
header shape and unauthenticated-rejection-before-route-logic behavior right now, since DASH-004 and
DASH-006 are both built directly on top of it without their own review pass on this exact point.

## Design
Pattern: **Dependency Injection** (implementation-plan.md section 7), the same table entry
`gateway-api`'s `build_downstream_headers`/GW-006's `get_authenticated_tenant` instantiate — this
ticket is `dashboard-web`'s own equivalent of that seam, not a new pattern.

File: `src/app/dependencies/downstream.py` (new). Provides:
- `get_session_headers(request: Request) -> dict[str, str]`: reads the `session_id` cookie (DASH-002),
  looks it up via `SessionStore.get` (DASH-002's `session.py`, imported not reimplemented — this
  ticket's own DRY obligation), and if found returns `{"Authorization": f"Bearer {api_key}"}`; if the
  cookie is missing or the session id is unknown to `SessionStore` (expired/never existed/already
  logged out), raises `HTTPException(303)` with a `Location: /login` header — a redirect, not a bare
  401 JSON body, since this dependency backs HTML-rendering routes, not a JSON API (`gateway-api`'s
  own `get_authenticated_tenant` returns 401 because it backs a JSON API — this is a deliberate,
  justified deviation from that precedent for the different consumer, documented here rather than
  copied blindly).
- `get_gateway_api_url() -> str`: reads `GATEWAY_API_URL` env var, default `http://localhost:8000` —
  the same default/env-var name DASH-002's lazy-validation call already uses (DASH-002 should not have
  hand-rolled a second, differently-named env var; if it did, this ticket reconciles them to one name
  and updates DASH-002's own call site to match, flagged in this ticket's Outcome if that correction
  was needed).
- `DownstreamHeadersDep = Annotated[dict[str, str], Depends(get_session_headers)]` and
  `GatewayApiUrlDep = Annotated[str, Depends(get_gateway_api_url)]` — the `Annotated[...,
  Depends(...)]` alias convention `gateway-api`'s own `TenantRepositoryDep`-style aliases already
  established (`src/app/dependencies/repositories.py`), reused here rather than reinvented.

**Rejection timing, the ticket's own hardest-to-get-wrong point**: because `get_session_headers`
raises before returning, and FastAPI resolves `Depends()` parameters before executing the route
function body, a route handler declaring `headers: DownstreamHeadersDep` as a parameter never
executes any of its own body when the session is invalid — this is what "rejected before route logic
runs" means concretely, and the ticket's own test must prove it non-tautologically (e.g. a route
whose body would raise/crash if reached, confirming the crash never happens for an unauthenticated
request — same non-tautological-proof style as `services/gateway-api`'s
`test_set_local_scope_does_not_leak_across_pooled_connection_reuse`).

DRY check: grepped `src/app/dependencies/` (only DASH-002's `session.py` exists) and
`services/gateway-api/src/app/dependencies/auth.py`/`routing.py` for the shape to mirror (confirmed
above) — no existing `dashboard-web` header-building code to reuse yet; this ticket is itself the
first and only place that logic will live.

## Implementation acceptance criteria
- [x] `get_session_headers` reads the `session_id` cookie, resolves it via `SessionStore.get`
  (DASH-002, imported not reimplemented), returns `{"Authorization": f"Bearer {api_key}"}` on success.
- [x] Missing cookie or unresolvable session id raises a redirect to `/login` before any route body
  executes — proven by the non-tautological test described above.
- [x] `get_gateway_api_url` reads `GATEWAY_API_URL` (single canonical env var name, reconciled with
  DASH-002 if it introduced a different one) via `Annotated[..., Depends(...)]` alias, no hardcode.
- [x] No route added in this ticket (there are none — DASH-004/006/007 are the actual consumers); this
  ticket only defines the seam, matching GW-007's own "this ticket only defines the seam" precedent.

## Test acceptance criteria
- [x] `tests/test_downstream.py`: valid session cookie -> correct `{"Authorization": "Bearer
  <key>"}` header shape returned; missing cookie -> redirect to `/login`, and a dummy route wired
  behind `DownstreamHeadersDep` whose body would fail an assertion if reached is proven never reached.
- [x] Run via `.venv\Scripts\python.exe -m pytest -q` (or `uv run pytest`), confirm pass, paste output.

## Review acceptance criteria
- [x] Tech Lead confirms: `get_session_headers` is the *only* place in the diff that reads the
  `session_id` cookie or calls `SessionStore.get`; no route file in this ticket (there are none) or
  future ticket's own diff hand-rolls an equivalent header dict (checked again at DASH-004/006/007
  review time, not just here); the header value is built with `f"Bearer {api_key}"` exactly matching
  `gateway-api`'s documented `Authorization: Bearer <key>` contract (`GW-006`), not `X-Api-Key`.

**Tech Lead review (2026-08-12)**: read `downstream.py`/`test_downstream.py` end to end. Confirmed
`get_session_headers` is the only reader of the `session_id` cookie/`SessionStore.get` in the diff;
header built as `{"Authorization": f"Bearer {api_key}"}`, matching GW-006's documented contract.
Non-tautological proof is real: `test_missing_cookie_redirects_before_route_body_runs` and
`test_unknown_session_id_redirects_before_route_body_runs` hit a dummy `/__probe__` route whose body
is `assert False` — the test only passes because that body is never reached, not because the response
happens to be 303. `GATEWAY_API_URL` env var reconciled correctly with DASH-002 (same name/default,
no duplicate). Re-ran the suite independently: `.venv\Scripts\python.exe -m pytest -q` from
`services/dashboard-web` -> **12 passed**, 0 failed (6 DASH-002 + 6 new DASH-003 tests), matching the
dev agent's reported output exactly. No mojibake or encoding corruption found in the final files (the
dev agent flagged and self-corrected an intermediate PowerShell encoding issue before handoff --
verified clean here).

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md`'s "Design notes" section gains a line naming this DI seam
  (`get_session_headers`/`DownstreamHeadersDep`) as the one mechanism every future route must share,
  mirroring `gateway-api`'s own `build_downstream_headers` documentation precedent.

## Outcome
Implemented by dev-squad agent (2026-08-12). Files created: `src/app/dependencies/downstream.py`
(`get_session_headers`/`get_gateway_api_url`/`DownstreamHeadersDep`/`GatewayApiUrlDep`),
`tests/test_downstream.py`. `services/dashboard-web/README.md`'s "Design notes" section updated with
a DASH-003 entry naming the seam.

No reconciliation needed for `GATEWAY_API_URL`: DASH-002's `http_client.py` already used that exact
env var name/default (`http://localhost:8000`), so `get_gateway_api_url` reuses it unchanged — no
second, differently-named env var was introduced.

Test run (`.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web`):
```
............                                                             [100%]
============================== warnings summary ===============================
.venv\lib\site-packages\fastapi\testclient.py:1
  ...StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated...

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 1 warning in 0.46s
```
(12 tests total: 6 pre-existing DASH-002 `test_auth.py` tests, unaffected/still passing, + 6 new
`test_downstream.py` tests.)

Tech Lead independent re-run (2026-08-12): 12 passed, 0 failed -- matches exactly.

All Implementation, Test, Review, and Documentation acceptance criteria met.
