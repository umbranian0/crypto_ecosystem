# DASH-007 — Logout / session invalidation

**Status: done**

## Analysis
Story: DASH-007 (Should), depends on DASH-002, DASH-003. Backlog acceptance criteria: logout clears
the session/cookie, redirects to `/login`; old session cookie rejected after logout, via DASH-003's
dependency, no new mechanism.

## Design
Pattern: **Dependency Injection** (DASH-003's `DownstreamHeadersDep`, reused to require a valid
session before logout can even be called — see below). File: `src/app/routers/auth.py` (same file
DASH-002 created — this ticket adds a second route to it, `POST /logout`; not a new file, since it's
the same auth-lifecycle module).

Handler: `POST /logout` -> resolve `headers: DownstreamHeadersDep` (reusing DASH-003's dependency
means an already-invalid session gets redirected to `/login` by the dependency itself before the
logout body ever runs — acceptable and arguably correct: logging out an already-logged-out session is
a no-op that ends at `/login` either way) -> read the `session_id` cookie directly (the raw cookie
value, not the resolved headers — `SessionStore.delete` needs the `session_id`, not the API key) ->
call `SessionStore.delete(session_id)` (DASH-002, imported not reimplemented) -> clear the cookie via
`Response.delete_cookie("session_id")` -> redirect (`303`) to `/login`.

DRY check: grepped `src/app/dependencies/session.py` (DASH-002 — `SessionStore.delete` already
exists per DASH-002's own Design section; this ticket must not add a second deletion method) and
`src/app/dependencies/downstream.py` (DASH-003 — reused for the "already invalid -> /login" behavior
rather than a new no-session-required logout route, since backlog AC2 explicitly says "via DASH-003's
dependency, no new mechanism").

## Implementation acceptance criteria
- [x] `POST /logout` clears the session (`SessionStore.delete`) and the cookie (`delete_cookie`),
  redirects to `/login`.
- [x] A request to `POST /logout` with no valid session (missing/already-deleted `session_id`)
  redirects to `/login` via DASH-003's existing dependency — no new/duplicate validity check written.
- [x] A subsequent request using the now-deleted `session_id` cookie against any
  `DownstreamHeadersDep`-backed route is rejected (redirected to `/login`) — proves the deletion is
  real, not merely a cookie-clear on the client that a replayed old cookie could bypass.

## Test acceptance criteria
- [x] `tests/test_logout.py`: valid session -> logout -> redirect to `/login`, cookie cleared in the
  response; the same (now-stale) `session_id` replayed against a `DownstreamHeadersDep`-backed route
  (e.g. DASH-004's detail route, already built by this point in the sequence) is rejected.
- [x] Run via `.venv\Scripts\python.exe -m pytest -q` (or `uv run pytest`), confirm pass, paste output.

## Review acceptance criteria
- [x] Tech Lead confirms `SessionStore.delete` (not a new method) is what this ticket calls, and that
  no second session-validity mechanism was introduced alongside DASH-003's existing one.

**Tech Lead review (2026-08-12)**: read `auth.py`'s new `logout` handler and `test_logout.py` end to
end. Confirmed it calls `SessionStore.delete` (DASH-002's existing method, not a new one) and depends
on `DownstreamHeadersDep` (DASH-003) for the already-invalid-session case, with no second/duplicate
validity check anywhere in the diff. `test_stale_session_cookie_rejected_after_logout_on_other_route`
is a real, non-tautological proof — it replays the deleted session against DASH-004's actual
`GET /runs/{run_id}` route, not a dummy stub, confirming server-side deletion. Re-ran the suite
independently: `.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web` -> **42 passed**,
0 failed, matching the dev agent's reported output exactly. (Note: this ticket's first delegation
attempt appears to have stalled with zero progress after an extended wait; it was abandoned and
re-delegated fresh, which completed normally in ~4 minutes.)

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md`'s "Authentication (DASH-002)" section gains one line noting
  logout exists (`POST /logout`) and reuses the same session/cookie mechanism, no new one.

## Outcome
Implemented `POST /logout` in `services/dashboard-web/src/app/routers/auth.py` (same file as
DASH-002's `GET/POST /login`), depending on `DownstreamHeadersDep` (DASH-003) and calling
`SessionStore.delete` (DASH-002) — no new session-validity or deletion mechanism added. Added
`services/dashboard-web/tests/test_logout.py` (3 tests): valid-session logout clears cookie/session
and redirects to `/login`; a request with no valid session is redirected to `/login` by
`DownstreamHeadersDep` before the handler body runs; a stale `session_id` cookie replayed against
`GET /runs/{run_id}` (DASH-004's real `DownstreamHeadersDep`-backed route) after logout is rejected
(303 to `/login`), proving the deletion is server-side, not a client-side cookie clear. Updated
`services/dashboard-web/README.md`'s "Design notes" and "Authentication (DASH-002)" sections.

Test run (`.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web`):

```
..........................................                               [100%]
============================== warnings summary ===============================
.venv\lib\site-packages\fastapi\testclient.py:1
  ...\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is
  deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
42 passed, 1 warning in 3.33s
```

All 42 tests pass (39 pre-existing + 3 new `test_logout.py` tests). The one warning is pre-existing
and unrelated to this ticket (Starlette's `httpx`-in-`TestClient` deprecation notice).

Tech Lead independent re-run (2026-08-12): 42 passed, 0 failed -- matches exactly.

All Implementation, Test, Review, and Documentation acceptance criteria met.
