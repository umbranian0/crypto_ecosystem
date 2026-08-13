# dashboard-web

**Status: DASH-001 through DASH-004 and DASH-006 through DASH-009 done (Sprint 11) -- scaffold,**
**login/session, the session-to-downstream-header DI seam, run detail view, submit-a-run form,**
**logout, a real health check, and a Selenium E2E suite covering the full login -> submit -> view**
**loop (47/47 tests passing: 42 unit + 5 e2e). `DASH-005` (runs list) is the one deferred story --**
**see "Known gaps" below. Built deliberately ahead of trigger #8 (implementation-plan.md section 6:**
**"as soon as a pilot client needs to see results without you manually sending them a file... second**
**pilot client, or first client asking 'where do I log in'") -- no real pilot client exists yet, the**
**same disclosed-override precedent `gateway-api`'s own README states for its own trigger #5 (see**
**docs/sprints/sprint-11.md's "Pre-planning checks" and "Explicit trigger override" sections, and**
**docs/product/backlog-dashboard-web.md's decision 1). Do not read anything in this README as "a pilot**
**client exists."**
**Sprint 11 goal: a tenant logs in with a gateway-api API key, submits a validation run through a**
**form, and views that run's status and per-split results -- the minimum submit -> view loop. See**
**docs/sprints/sprint-11.md and docs/tickets/README.md for live ticket status. `DASH-005` (runs**
**list) is deliberately deferred this sprint -- see "Known gaps" below.**

Formerly `dashboard/`. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.6.

**Owns**: server-rendered UI only (FastAPI + Jinja2 + HTMX) -- login/session, run detail, submit-a-run
form. (A runs-list page, report viewer, and degradation-alerts view are planned but not in scope this
sprint -- see "Known gaps" below.)

**Does not own**: any data access -- every page is rendered from calls to `gateway-api`'s public
contract, same as an external client would use. This is deliberate: it keeps the UI honest to the same
API contract external SDK users get, and means the UI can never drift into reading internal service
schemas directly.

**Design notes**:
- No `Repository` pattern here -- this service persists nothing of its own; DASH-002/003's session
  store is an interim in-memory cache of `session_id -> raw API key`, not a data-access layer over a
  owned schema, so implementation-plan.md section 7's Repository pattern doesn't apply. The one pattern
  from that table this service actually uses is **Dependency Injection** (FastAPI `Depends()`), for the
  session-to-downstream-headers seam (DASH-003) every route shares.
- **DASH-003**: `src/app/dependencies/downstream.py`'s `get_session_headers`/`DownstreamHeadersDep`
  is the one DI seam every future authenticated route (DASH-004/006/007) must depend on to get its
  outbound `gateway-api` headers -- no route hand-rolls its own cookie read, `SessionStore.get` call,
  or `Authorization` header dict. It reads the `session_id` cookie, resolves it via DASH-002's
  `SessionStore.get`, and returns `{"Authorization": f"Bearer {api_key}"}`; a missing/unresolvable
  session raises `HTTPException(303)` to `/login` before any dependent route body executes -- a
  redirect rather than `gateway-api`'s own `get_authenticated_tenant` 401, since this seam backs
  HTML-rendering routes, not a JSON API. `get_gateway_api_url`/`GatewayApiUrlDep` (same module) reads
  the same `GATEWAY_API_URL` env var DASH-002's `http_client.py` already uses, kept to one canonical
  name.
- **DASH-004**: `src/app/routers/runs.py`'s `GET /runs/{id}` is the first route to consume
  `GatewayApiUrlDep` for an outbound `httpx.Client(base_url=...)` call (rather than the persistent
  `GatewayApiClientDep` provider DASH-002's login uses) -- built per the ticket's own Design section.
  `not_found.html`/`error.html` (`src/app/templates/`) are intentionally generic, not detail-specific,
  so DASH-006 can reuse `error.html` for its own transport-failure handling instead of a second
  near-identical template (implementation-plan.md section 9's DRY rule).
- **DASH-006**: `GET /runs/new`/`POST /runs/new` are declared in the same router module, registered
  *before* `GET /runs/{run_id}` (route registration order matters: `/runs/{run_id}` would otherwise
  swallow `/runs/new` as `run_id="new"`). Reuses `error.html` (no new template for the transport-failure
  path) and generalizes DASH-004's GET-only `_fetch` helper into `_call_downstream` (bound-method
  parameter, works for both `client.get` and `client.post`) instead of a second near-identical
  try/except -- implementation-plan.md section 9's DRY rule, checked against this file before writing
  per the ticket's own DRY check note.
- **DASH-007**: `POST /logout` (`src/app/routers/auth.py`, same file DASH-002 created -- not a new
  one) depends on DASH-003's `DownstreamHeadersDep` to get the "already invalid/missing session ->
  redirect to `/login`" behavior for free, before the handler body runs, per the ticket's own Design
  section ("no new mechanism") -- no second session-validity check is written. Calls `SessionStore
  .delete` (DASH-002's existing method, imported not reimplemented), clears the cookie via `Response
  .delete_cookie`, and redirects (303) to `/login`.
- **DASH-008**: `GET /health` (`src/app/main.py`) intentionally does *not* consume `GatewayApiUrlDep`
  as a FastAPI `Depends()` parameter (unlike DASH-004/006) -- it calls `get_gateway_api_url()`
  directly as a plain function, since this route itself must stay outside the
  `DownstreamHeadersDep`/session-required family entirely; the shared piece being reused is just the
  one-canonical-env-var-name function, not the DI seam pattern.
- Metrics-table rendering shared with `reporting-service`'s HTML report templates would belong in
  `libs/common`, not duplicated between the two (DRY across the module boundary via a shared lib, per
  implementation-plan.md section 9) -- not yet applicable, since `reporting-service` doesn't exist yet
  (trigger #7 unfired).

**Contract**: consumes `gateway-api`'s OpenAPI schema (`POST /runs`, `GET /runs/{id}`,
`GET /runs/{id}/splits`, `GET /health`); no contract of its own beyond its rendered HTML routes.
Response shapes are parsed via `naive_first_common.contracts`' shared `RunRequest`/`RunResponse`/
`RunDetailResponse`/`SplitResultResponse` models (ARCH-003) -- the same models `gateway-api` itself
uses -- rather than a third hand-duplicated copy of the same field list.
- **DASH-004**: `GET /runs/{id}` (`src/app/routers/runs.py`) consumes `gateway-api`'s `GET /runs/{id}`
  and, on a successful detail fetch, `GET /runs/{id}/splits`, via the same shared
  `naive_first_common.contracts` `RunDetailResponse`/`SplitResultResponse` models -- if those models'
  fields change, this route's rendering must be updated to match, not silently drift (same
  version-sync caveat `gateway-api`'s own GW-008 documentation states for its proxy). Gateway-api's
  `404` (nonexistent run or a run belonging to another tenant, collapsed upstream, no distinction
  shown) renders `not_found.html`; a transport-level failure or a `502`/`504` forwarded from
  `gateway-api` renders the generic, reusable `error.html` with a fixed "results currently
  unavailable" string -- no hostname/status/exception text leaked into the page.
- **DASH-006**: `GET /runs/new`/`POST /runs/new` (`src/app/routers/runs.py`) submit a run to
  `gateway-api`'s real `POST /runs` via the same shared `RunRequest`/`RunResponse` models -- same
  version-sync caveat as DASH-004's entry above (if those models' fields change, this route's form/
  request construction must be updated to match, not silently drift). `201` redirects (`303`) to
  DASH-004's `GET /runs/{id}` regardless of the returned `status` value -- no optimistic state is
  rendered on this route itself.

**Known gaps (disclosed, not silent)**:
- `DASH-005` (runs list) is **not built this sprint** -- no `GET /runs` list endpoint exists on
  `gateway-api` or `validation-service` today. Blocked on new, not-yet-authored backlog tickets
  (`VS-0NN` in `validation-service`, `GW-016` in `gateway-api`) -- see
  `docs/product/backlog-dashboard-web.md`'s `DASH-005`/`DASH-005-GAP` entries and
  `docs/sprints/sprint-11.md`'s scheduling decision. Until resolved, a run is only reachable via
  `GET /runs/{id}` directly (e.g. the id returned by the submit-a-run form's redirect).
- `GW-011` (JWT session auth) is not built either -- login uses `gateway-api`'s existing API-key auth
  (`GW-006`) instead (backlog decision 3).

## Authentication (DASH-002)

`GET /login` renders a form for a tenant's raw `gateway-api` API key; `POST /login`
(`src/app/routers/auth.py`) exchanges it for a server-side session:

- **Lazy validation**: `gateway-api` has no dedicated "verify this key" endpoint, and at this point
  in the ticket sequence no other authenticated route exists yet to react to a `401` from. `POST
  /login` calls `gateway-api`'s `GET /runs/{a random uuid4}` (authenticated per `GW-006`) instead --
  cheap, and a `401` unambiguously means "invalid key" (vs. `404` for "well-formed key, unknown run,"
  which is treated the same as any other non-`401` success signal). A transport-level failure
  (connection refused/timeout) redisplays `/login` with a generic "unreachable" error, not an
  invalid-key error. DASH-003's shared dependency is where 401-handling gets centralized for every
  *future* authenticated route; this ticket's own AC3 is proven only via this handler's own
  lazy-validation call.
- **Cookie holds only the opaque `session_id`** (`secrets.token_urlsafe(32)`), never the raw key in
  any form (not signed, not encoded) -- the raw key lives only in the server-side, process-local
  `SessionStore` (`src/app/dependencies/session.py`). This is a stronger guarantee than a signed
  cookie (e.g. Starlette's `SessionMiddleware`, whose payload is base64-readable by anyone holding the
  cookie even without the signing secret) -- do not swap this design for `SessionMiddleware` or any
  cookie-encodes-the-payload approach.
- `DASHBOARD_COOKIE_SECURE` (env var, default `"false"`) gates `secure=True` on the cookie --
  `"false"` is correct for this sprint's plain-HTTP local/Compose PoC and is a disclosed gap, not a
  silently-accepted one, same spirit as `gateway-api`'s own GW-007 forwarding-mechanism caveat; set it
  to `"true"` behind TLS termination in a future deployment. `httponly=True` is set unconditionally.
- `SessionStore` is an in-memory `dict` (module-level singleton) -- a known PoC-scoped limitation:
  sessions do not survive a process restart and are not shared across multiple `dashboard-web`
  replicas. Acceptable for this sprint's single-instance scope only.
- The raw API key is never rendered into any HTML/JS response body (including the error-redisplay
  path, which does not echo the submitted value back into the form), never logged, and never placed
  in a URL/query string/redirect `Location` header -- it is sent to `gateway-api` exactly once per
  login attempt, as `Authorization: Bearer <key>` only (never the `X-Api-Key` fallback).
- **DASH-007**: `POST /logout` (same `src/app/routers/auth.py` file) reuses this same session/cookie
  mechanism, no new one -- it depends on DASH-003's `DownstreamHeadersDep` (so an already-invalid or
  missing session is redirected to `/login` by that existing dependency before the handler body runs),
  calls `SessionStore.delete` (DASH-002's existing method, not a second one), and clears the cookie via
  `Response.delete_cookie`.

## Run detail (DASH-004)

`GET /runs/{run_id}` (`src/app/routers/runs.py`) renders one validation run's status/detail fields
plus its per-split results, both fetched from `gateway-api` and parsed via the shared
`naive_first_common.contracts` models (imported, not redefined):

- Resolves `headers: DownstreamHeadersDep`/`base_url: GatewayApiUrlDep` (DASH-003) -- no hand-rolled
  `Authorization` header anywhere in this router. Calls `GET /runs/{id}`; on `200`, calls
  `GET /runs/{id}/splits` unconditionally (a `"running"` run legitimately has zero splits yet, so
  whether any exist is decided by the splits endpoint's own response, not a client-side status guess).
- Renders `run_detail.html` with `id, status, dataset_id, horizon, purge_gap_hours, created_at,
  completed_at, failure_reason` from `RunDetailResponse`, and each split's boundaries, both
  baselines' full metric sets, and `dm_statistic`/`dm_pvalue`/`dm_verdict` verbatim from
  `SplitResultResponse` -- no recomputation/reinterpretation of the DM test (`NFE-012`'s Harvey
  correction is already applied upstream). `tenant_id`/`split_config` are present on the response but
  deliberately not rendered (no product value in echoing a tenant's own id back to them).
- **Positioning**: the template describes rendered numbers as "validation results" / "benchmark
  comparison" / "per-split metrics" only -- never "prediction," "forecast," "signal," or
  "recommendation" (CLAUDE.md's core positioning constraint; this is the first template in this
  service that renders real model output).
- `404` (nonexistent run, or a run belonging to another tenant -- both collapsed upstream by
  `gateway-api`/`validation-service`, no distinction shown here) renders `not_found.html`. A
  transport-level `httpx.ConnectError`/`httpx.TimeoutException`, or a `502`/`504` status forwarded
  from `gateway-api`, renders `error.html` with a fixed generic "results currently unavailable"
  string -- no hostname/status code/exception text is ever included in the rendered page.
- `not_found.html`/`error.html` are generic, reusable templates (not detail-specific) -- any future
  route needing the same two failure states (e.g. DASH-006) reuses them rather than duplicating a
  near-identical template.

## Submit a run (DASH-006)

`GET /runs/new` (`src/app/routers/runs.py`) renders `run_new.html`, a form matching `RunRequest`'s
exact fields (`dataset_id`, `dataset_reference`, `horizon`, `purge_gap_hours`, `train_window`,
`test_window`, `step`) -- a pure static render, no downstream call, but still gated behind
`headers: DownstreamHeadersDep` (DASH-003) so the form is only reachable once logged in, matching
`POST /login`'s own redirect target. `POST /runs/new` submits to `gateway-api`'s real `POST /runs`:

- **`dataset_reference`'s two interim modes** are exposed as two form fields, copied verbatim from
  `services/validation-service/src/app/dataset_source.py`'s `InlineOrLocalFileDatasetSource.load` (not
  approximated): a local file path text input (`dataset_reference_path`, maps to
  `dataset_reference = {"path": <value>}`) and an inline-payload JSON textarea
  (`dataset_reference_inline`, parsed via `json.loads` and wrapped as
  `dataset_reference = {"inline": <parsed>}` -- the parsed value can be either the
  `[[timestamp, value], ...]` list shape or the `{"timestamps": [...], "values": [...]}` dict shape,
  whichever the tenant submits, exactly as `InlineOrLocalFileDatasetSource` itself accepts). A blank
  submission of both fields, or unparseable inline JSON, redisplays the form with a `422` and the
  submitted values repopulated -- never falls through to a default/guessed dataset reference.
- **No pre-filled defaults**: no form field (including `purge_gap_hours`) carries a pre-filled value
  that could look like a recommended default -- the tenant must type every value. The handler never
  substitutes or overrides a submitted value with one of its own; this is pass-through UI only, so no
  field/default here can cause a submitted run to skip the purge gap or the mandatory naive baselines
  (CLAUDE.md's core constraint, restated in the ticket's Design section as its single highest-stakes
  requirement).
- Numeric/dataset-id fields are wrapped in a `RunRequest(...)` construction; a `ValueError` (bad
  numeric text) or Pydantic `ValidationError` (e.g. `horizon=0`) redisplays the form with the specific
  error and submitted values repopulated, without ever reaching `gateway-api` -- the *authoritative*
  validation beyond that point is `gateway-api`'s own `422` response, forwarded verbatim via
  `_extract_detail` (not reinterpreted or re-derived).
- On `201` (including a `201` with `status: "failed"` in the body -- a business outcome, not a
  transport failure), redirects (`303`) to DASH-004's `GET /runs/{run_id}` for the returned id. No
  status text is rendered on this route itself before redirecting -- DASH-004 is the single source of
  truth for the run's real status, so there is no optimistic state to fabricate here, satisfied by
  construction.
- A transport-level `httpx.ConnectError`/`httpx.TimeoutException`, or a `502`/`504` forwarded from
  `gateway-api`, renders the same `error.html` DASH-004 uses -- no second, near-identical template.

## Health check (DASH-008)

`GET /health` (`src/app/main.py`, same file gateway-api's/validation-service's own `/health`
handlers live in, per their precedent) performs a real HTTP call to `GATEWAY_API_URL`'s `/health`
(reusing DASH-003's `get_gateway_api_url()` rather than a second, differently-named env var read;
5s timeout) -- not a hardcoded response. On a `200` from gateway-api, returns `200 {"status": "ok"}`.
On any transport failure (connect error, timeout) or a non-200 status from gateway-api, returns
`503 {"status": "unhealthy", "detail": "gateway-api unreachable"}` -- a fixed generic string, no
leaked hostname/exception text, matching `OPS-005-01`/`OPS-005-02`'s body-shape precedent in
`validation-service`/`gateway-api`. This route is deliberately **unauthenticated** -- no
`DownstreamHeadersDep`/session dependency is attached, since an operator/orchestrator health-checking
this service has no tenant session.

## Local setup

`uv sync` from this directory, then `uv run uvicorn app.main:app --reload --app-dir src` (or the
project's usual `.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir src` on Windows).
Requires `GATEWAY_API_URL` (env var, default `http://localhost:8000`) pointing at a running
`gateway-api` instance. `DASHBOARD_COOKIE_SECURE` (env var, default `"false"`) controls the login
session cookie's `secure` flag -- see "Authentication (DASH-002)" above.

**Tests**: `uv run pytest` (route-handler unit tests, mocked `gateway-api`) from this directory -- 42
tests, the `e2e` marker's items deselected by default (`addopts = "-m \"not e2e\""` in
`pyproject.toml`).

**DASH-009 -- Selenium E2E suite** (`tests/e2e/`, the first browser-level suite in this platform): run
separately via `uv run pytest -m e2e` -- 5 tests, exercising login (valid + invalid key), submit-a-run
(valid + invalid payload), and view-a-run (completed run + nonexistent id), each in a real browser
against a real running `dashboard-web` subprocess.
- **Browser/WebDriver**: Chrome, auto-resolved by Selenium's built-in Selenium Manager (bundled with
  `selenium>=4.20`, a dev dependency) -- no manual `chromedriver` install needed in most environments.
  To use a different browser/driver, set Selenium's own standard driver-path env vars before running.
- **Fixture `gateway-api`**: automatic, no setup required -- `tests/e2e/conftest.py`'s
  `stub_gateway_api` session fixture starts a minimal stub implementing just enough of `gateway-api`'s
  real contract (`/health`, `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`) as its own
  subprocess. Does not require `infra/docker-compose.yml` or a real Postgres/Redis stack.
- **Environment note**: if this repo directory sits inside a cloud-synced folder (e.g. OneDrive), you
  may see intermittent file-write/`.venv`-creation failures unrelated to this suite's own code; setting
  `UV_PROJECT_ENVIRONMENT` to a path outside the synced tree before `uv sync`/`uv run` works around it.

**CI**: not yet wired into `.github/workflows/ci.yml` (OPS-001) -- planned as a follow-up once this
service's Sprint 11 scope is done and stable.
