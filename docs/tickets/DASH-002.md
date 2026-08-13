# DASH-002 — Login screen exchanging a tenant API key for a server-side session

**Status: done**

**Tech Lead review (2026-08-12)**: personally read `session.py`, `auth.py`, `login.html`,
`http_client.py`, `test_auth.py` end to end (not just the dev agent's own summary). Confirmed: the
raw key is interpolated exactly once, into the outbound `Authorization: Bearer {api_key}` header sent
to gateway-api; never into a template context, log call, exception message, or redirect
URL/`Location` header anywhere in the diff. `login.html`'s API-key `<input>` has no `value=`
attribute on either the initial or error-redisplay render path, so a submitted key is never echoed
back. The cookie is set via `redirect.set_cookie(key="session_id", value=session_id, httponly=True,
samesite="lax", secure=_cookie_secure())` — `session_id` only, never the raw key in any form;
`httponly=True` is unconditional. Re-ran the test suite independently (not merely trusting the dev
agent's own report): `.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web` ->
**6 passed**, 0 failed — matches the agent's reported output exactly. `GATEWAY_API_URL` (the env var
name used by the new `http_client.py`) matches what DASH-003 will need — no reconciliation required
there. One accepted deviation from this ticket's own draft Design text: the "Lazy validation"
paragraph initially named `GET /health`, then self-corrected in the same paragraph to the actual,
load-bearing mechanism (`GET /runs/{uuid4()}`, since `/health` is unauthenticated and carries no
signal about key validity) — the agent implemented the corrected instruction, consistent with the
rest of that section and the Implementation acceptance criteria; not a scope deviation, and marked
accepted here rather than re-delegated.

## Analysis
Story: DASH-002 (Must), depends on DASH-001. Backlog acceptance criteria: `GET /login` renders a
form for the raw API key (`gateway-api` has no JWT/email login today, only `GW-006`'s key check —
confirmed by reading `services/gateway-api/README.md`'s "Authentication (GW-006)" section directly:
`Authorization: Bearer <key>` checked first, `X-Api-Key: <key>` as fallback); `POST /login` stores
the key in a new server-side session + secure HttpOnly cookie, lazy validation (no dedicated verify
endpoint exists on `gateway-api` — the first authenticated call elsewhere proves validity via its 401
behavior); a 401 from any downstream call redirects to `/login` with an error and clears the session;
raw key never rendered in HTML/JS, never logged, never in a URL, only ever sent as
`Authorization: Bearer <key>` (gateway-api's documented header contract — use `Authorization`, not
the `X-Api-Key` fallback, since that's the primary documented shape); tests per backlog AC5.

This is this sprint's most security-sensitive ticket (sprint-11.md's own flag) — treat it with the
same extra scrutiny this repo gave GW-006/GW-007 in Sprint 05. The Tech Lead will personally verify
the raw key is never rendered/logged/in a URL by reading the actual diff, not by trusting this
ticket's own test suite.

## Design
Pattern: **Dependency Injection** only (implementation-plan.md section 7) — no Strategy/Factory/etc.
applies to a login form. Files: `src/app/dependencies/session.py` (new — an in-memory
`session_id -> raw_api_key` store; a module-level `dict` behind a small class, e.g. `SessionStore`,
with `create(api_key: str) -> str` returning a new opaque `session_id` via
`secrets.token_urlsafe(32)`, `get(session_id: str) -> str | None`, `delete(session_id: str) -> None`.
This is deliberately **not** a `Repository` per implementation-plan.md section 7's table — it isn't a
data-access layer over an owned schema (this service persists nothing, per its README's "Does not
own"), it's a transient in-process cache; calling it a `SessionStore` rather than a
`SessionRepository` reflects that distinction. Interim/PoC-scoped: an in-memory dict means sessions
don't survive a process restart and don't work across multiple `dashboard-web` replicas — acceptable
for this sprint's single-instance PoC scope, but must be stated plainly in the README as a known
limitation, not silently presented as production-grade.), `src/app/routers/auth.py` (new — `GET
/login`, `POST /login` handlers), `src/app/templates/login.html` (new — extends `base.html` from
DASH-001).

**Cookie contents, the actual security-critical design decision**: the cookie holds *only* the opaque
`session_id` (`secrets.token_urlsafe(32)`), set via `Response.set_cookie(key="session_id",
value=session_id, httponly=True, samesite="lax")` — the raw API key itself is held server-side in
`SessionStore`, never placed in the cookie in any form (not even signed/encoded). This is a stronger
guarantee than a signed cookie (e.g. Starlette's `SessionMiddleware`, which base64-encodes and signs
but does not encrypt — its contents are readable by anyone holding the cookie, even without the
signing secret) — do not use `SessionMiddleware` or any cookie-encodes-the-payload approach for this
reason. `secure=True` on the cookie is gated behind a `DASHBOARD_COOKIE_SECURE` env var, defaulting to
`"false"` for this sprint's plain-HTTP local/Compose PoC — document this as a known, disclosed gap
(not silently accepted) for a future TLS-terminated deployment, same spirit as
`gateway-api`'s own disclosed GW-007 forwarding-mechanism caveat.

**401 redirect + session invalidation**: does not yet have a route to react to (DASH-003 defines the
one shared dependency all future routes go through) — this ticket's own AC3 ("a 401 from any
downstream call redirects to `/login`... and clears the session") is satisfiable today only by
`POST /login` itself performing a lazy validation call and reacting to its own 401 (there is no other
authenticated route yet at this point in the sequence). Document explicitly in this ticket's Outcome
that DASH-003's shared dependency is where *future* routes' 401-handling is centralized — this
ticket's own AC3 is proven via `POST /login`'s own lazy-validation call only, not a general mechanism
yet (DASH-003 formalizes it for every subsequent route).

**Lazy validation, concretely**: `POST /login` calls `gateway-api`'s `GET /health` — NOT an
authenticated endpoint (`GW-006`'s auth dependency isn't attached to `/health`, confirmed by reading
`services/gateway-api/src/app/main.py` directly: `/health` takes only `HealthCheckEngineDep`, no
`Security()`/`Depends(get_authenticated_tenant)`). Since there is no dedicated "verify this key"
endpoint and no other authenticated route exists yet at this point in the ticket sequence, use
`gateway-api`'s cheapest real authenticated call instead: `GET /runs/{id}` with a syntactically
well-formed but almost-certainly-nonexistent UUID (e.g. `str(uuid.uuid4())`) is authenticated
(`GW-006`) and returns `401` for a bad/missing key vs `404` for a well-formed-but-unknown run for a
*valid* key — both `401` and `404` are acceptable "the key format round-trips through gateway-api's
auth layer" signals, but only `401` specifically means "invalid key," which is what `POST /login`
must react to (store the session and redirect to `/runs/new` on anything other than 401; redisplay
`/login` with an error and do not create a session on 401). Any other transport-level failure (502/504,
connection refused) redisplays `/login` with a generic "gateway-api unreachable" error — do not treat
that as "invalid key."

DRY check: grepped `services/dashboard-web/src/` (only DASH-001's skeleton exists — nothing to reuse
yet); grepped `services/gateway-api/src/app/dependencies/auth.py` to confirm the exact header/scheme
contract this ticket's client call must match (`Authorization: Bearer <key>`) rather than guessing it.

## Implementation acceptance criteria
- [x] `GET /login` renders `login.html` (extends `base.html`) with a form posting to `POST /login`,
  one field for the raw API key, no pre-filled/default value.
- [x] `POST /login` performs the lazy-validation call described above against `GATEWAY_API_URL` (env
  var, default `http://localhost:8000`, no hardcode) with `Authorization: Bearer <key>`; on anything
  other than `401`, creates a session via `SessionStore.create`, sets the `session_id`-only HttpOnly
  cookie, and redirects (`303`) to `/runs/new` (DASH-006's future route — acceptable forward
  reference per sprint-11.md's own sequencing, since DASH-006 is built two tickets later in the same
  chain); on `401`, redisplays `/login` with an error, no session/cookie created.
- [x] An empty/whitespace-only submitted key is rejected with a `422`/redisplay-with-error *before*
  any call to `gateway-api` — no wasted round trip for a value that's obviously invalid.
- [x] Raw key never rendered in any HTML/JS response body (including the error-redisplay path — do
  not echo the submitted value back into the form field), never logged (no `print`/`logging` call
  anywhere in this ticket's new code takes the raw key as an argument, checked directly), never
  placed in a URL/query string/redirect Location header anywhere.
- [x] `SessionStore` is process-local, documented in the README as a known PoC-scoped limitation
  (no cross-replica/restart durability).

## Test acceptance criteria
- [x] `tests/test_auth.py`: valid key (mocked `gateway-api` returning non-401) is stored and a
  session cookie is set on the response; empty key is rejected before any outbound call is made
  (assert the mock transport records zero calls); a key that gets a `401` from the lazy-validation
  call is not stored and `/login` is redisplayed with an error, no `Set-Cookie` header present.
- [x] A test asserts the raw submitted key string does not appear anywhere in the response body of
  either the success or failure path (a real non-tautological string-search assertion, not merely
  "the test passed").
- [x] Run via `.venv\Scripts\python.exe -m pytest -q` (or `uv run pytest`), confirm pass, paste
  output into this ticket's Outcome section.

## Review acceptance criteria
- [x] Tech Lead personally reads `session.py`/`auth.py`/`login.html` end to end (not just the test
  file) and independently confirms: no `f"...{api_key}..."` or similar interpolation of the raw key
  into any template, log call, redirect URL, or exception message anywhere in this ticket's diff; the
  cookie's `Set-Cookie` value is confirmed (by reading the actual HTTP response in a test or by
  direct inspection) to be the opaque `session_id` only, never the raw key; `httponly=True` is set on
  the cookie unconditionally. See Tech Lead review note at the top of this file.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` gains a short "Authentication (DASH-002)" section
  documenting: the lazy-validation mechanism (which gateway-api call is used and why), the
  cookie-holds-only-a-session-id design and its rationale, the `DASHBOARD_COOKIE_SECURE` env var and
  its local-PoC default, and the `SessionStore`'s in-memory/non-durable limitation.

## Outcome

Implemented as designed, with one deviation from the Design section's literal wording (documented
below) and everything else built as specified.

**Deviation**: the Design section's "Lazy validation, concretely" paragraph opens by describing a
`GET /health` call, then immediately corrects itself in the same paragraph to specify the real
mechanism used (`GET /runs/{a random uuid4}`, since `/health` carries no signal about key validity —
it's unauthenticated and returns `200`/`503` regardless of any header). The implementation follows
the corrected, load-bearing instruction: `POST /login` calls `GET /runs/{uuid.uuid4()}` with
`Authorization: Bearer <key>`, treats `401` as "invalid key" and any other status (including `404`)
as "valid key," and treats `httpx.ConnectError`/`httpx.TimeoutException` as "gateway-api unreachable"
(redisplays `/login` with a generic error, does not create a session). This matches every other part
of the Design section (the AC1/AC2 wording, the DRY-check note about reading `auth.py`'s header
contract) and the Implementation acceptance criteria as written.

**Files created**:
- `services/dashboard-web/src/app/dependencies/session.py` — `SessionStore` (in-memory
  `session_id -> raw_api_key`), `get_session_store` provider, `SessionStoreDep`.
- `services/dashboard-web/src/app/dependencies/http_client.py` — `get_gateway_api_client` provider
  (`httpx.Client` pointed at `GATEWAY_API_URL`, default `http://localhost:8000`) + `GatewayApiClientDep`,
  mirroring `gateway-api`'s own `app.dependencies.http_client` shape 1:1 for the same
  DI-testability reason (override via `app.dependency_overrides` in tests, `httpx.MockTransport`
  since `httpx.Client` is sync). Not explicitly named as a ticket file, but required to make the
  Design section's stated DI pattern testable without duplicating client-construction logic inline
  in the router.
- `services/dashboard-web/src/app/routers/auth.py` — `GET /login`, `POST /login`.
- `services/dashboard-web/src/app/templates/login.html` — extends `base.html`; no `value` attribute
  on the API-key `<input>`, so a submitted key is never echoed back on redisplay.
- `services/dashboard-web/tests/test_auth.py` — 6 tests (see below).

**Files modified**:
- `services/dashboard-web/src/app/main.py` — imports and mounts `auth.router` after `templates` is
  defined (the router reads `templates` back from this module; ordering is deliberate and commented).
- `services/dashboard-web/README.md` — new "Authentication (DASH-002)" section; "Status" line and
  "Known gaps" updated to reflect DASH-002 as done and the `/runs/new` forward reference.

**Test run** (`.venv\Scripts\python.exe -m pytest -v` from `services/dashboard-web`):
```
collected 6 items

tests/test_auth.py::test_get_login_renders_form PASSED                   [ 16%]
tests/test_auth.py::test_valid_key_creates_session_and_redirects PASSED  [ 33%]
tests/test_auth.py::test_empty_key_rejected_before_any_outbound_call PASSED [ 50%]
tests/test_auth.py::test_invalid_key_gets_401_and_is_not_stored PASSED   [ 66%]
tests/test_auth.py::test_raw_key_never_appears_in_response_body_success_path PASSED [ 83%]
tests/test_auth.py::test_raw_key_never_appears_in_response_body_failure_path PASSED [100%]

6 passed, 1 warning in 0.41s
```
(The one warning is `fastapi.testclient`'s pre-existing `httpx`/`starlette.testclient` deprecation
notice, unrelated to this ticket's code.)

**Tech Lead independent re-run** (`.venv\Scripts\python.exe -m pytest -q`, 2026-08-12): 6 passed,
0 failed — matches exactly.
