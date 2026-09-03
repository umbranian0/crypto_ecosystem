# dashboard-web

**Status: DASH-001 through DASH-009 done (Sprint 11 + Sprint 15) -- scaffold, login/session, the**
**session-to-downstream-header DI seam, run detail view, submit-a-run form, logout, a real health**
**check, a runs list view, and a Selenium E2E suite covering the full login -> submit -> view loop.**
**`DASH-113` (Sprint 18) added a minimal `/monitoring` service-status page and a structurally-separate**
**operator-token session gate (`require_operator_session`), the minimal slice of the sibling backlog's**
**`SETUP-003`/`012`/`020` stories pulled into this sprint for `DASH-109`/`110`/`112`'s sake -- the full**
**setup wizard and tenant-management UI remain that other backlog's own scope, not duplicated here**
**(65/65 unit tests passing + 5 e2e). `DASH-109` (Sprint 18) extended that same `/monitoring` page with**
**a "last crawl status" panel, per-tenant, plus a new `GET /ingestion/connectors/{source}/status`**
**proxy on `gateway-api` -- see "Last crawl status panel (DASH-109)" below. `DASH-112` (Sprint 18,**
**revised scope) added that gate's first real**
**consumer: a per-tenant, read-only `/settings/connectors` connector credential-status lookup -- see**
**"Settings: connector credential status (DASH-112)" below. `DASH-110` (Sprint 18) added two trigger**
**actions to that same `/monitoring` page -- a per-source "run this tenant's crawl now" button and a**
**"generate a report" form -- see "Trigger actions on /monitoring (DASH-110)" below (101 unit tests**
**passing + 5 e2e as of that ticket). `DASH-115` (Sprint 20) updated the crawl-trigger fragment and**
**crawl-status panel for `INGEST-015`'s async crawl-trigger contract (`202 {source, status: "queued",**
**since, queued_at}`, no `row_count`), and made the crawl-status panel self-refresh every 5s via a new**
**`GET /monitoring/crawl-status-fragment` route -- see "Trigger actions on /monitoring (DASH-110)" and**
**"Last crawl status panel (DASH-109)" below (109 unit tests passing + 5 e2e as of this ticket).**
**`DASH-005` (runs list), deferred since**
**Sprint 11, was closed in Sprint 15 (`DASH-005-01`) once `DASH-005-GAP` was resolved upstream**
**(Sprint 14: `VS-022` + `GW-016`). Built deliberately ahead of trigger #8 (implementation-plan.md**
**section 6: "as soon as a pilot client needs to see results without you manually sending them a**
**file... second pilot client, or first client asking 'where do I log in'") -- no real pilot client**
**exists yet, the same disclosed-override precedent `gateway-api`'s own README states for its own**
**trigger #5 (see docs/sprints/sprint-11.md's "Pre-planning checks" and "Explicit trigger override"**
**sections, and docs/product/backlog-dashboard-web.md's decision 1). Do not read anything in this**
**README as "a pilot client exists."**
**Sprint 11 goal: a tenant logs in with a gateway-api API key, submits a validation run through a**
**form, and views that run's status and per-split results -- the minimum submit -> view loop. See**
**docs/sprints/sprint-11.md and docs/tickets/README.md for live ticket status.**

Formerly `dashboard/`. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.6.

**Owns**: server-rendered UI only (FastAPI + Jinja2 + HTMX) -- login/session, run detail, submit-a-run
form, runs list, an ingested-dataset browsing view (`DASH-111`), a minimal service-status monitoring
page, an operator-token session gate reusable by any `/settings/*` route (`DASH-113`), a first
`/settings/*` route itself: a per-tenant, read-only connector credential-status lookup (`DASH-112`), and
two trigger actions on the monitoring page -- "run this tenant's crawl now" per source, and "generate a
report" for an existing run (`DASH-110`), both plain authenticated HTTP calls through `gateway-api`'s
own already-existing proxies, never any container-runtime or OS-process control of their own. (A report
viewer, degradation-alerts view, and the full setup wizard/tenant-management UI are planned but not in
scope yet -- see "Known gaps" below.)

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
- **DASH-005-01**: `GET /runs` (`src/app/routers/runs.py`, same file/router module) reuses
  `DownstreamHeadersDep`/`GatewayApiUrlDep`/`_call_downstream`, same as every other route here -- no
  hand-rolled header or a fourth near-identical transport-failure try/except. This is also the point
  where the 502/504-to-`error.html` branch (already duplicated once between DASH-004's `run_detail` and
  DASH-006's `run_new_submit`) hit its third occurrence, so it was extracted into a small
  `_render_error_for_status(request, status_code)` helper in this same file and all three call sites
  (including the pre-existing two) now share it -- implementation-plan.md section 9's "extract on
  second duplication" rule.
- **DASH-111**: `GET /datasets` (`src/app/routers/runs.py`, same file/router module, same "no second
  router module" precedent DASH-005-01 set) lists all of a tenant's ingested datasets via a new
  `_fetch_ingestion_datasets(client, headers)` helper -- extracted out of `run_new_form`'s (DASH-108)
  original inline `GET /ingestion/datasets`-fetch-and-degrade logic so both routes share one
  implementation instead of two near-identical ones (ticket's own DRY check note; both call sites are
  documented in the "Ingested datasets (DASH-111)" section below). `run_new_form` also grew an optional
  `dataset_reference_source` query param so `datasets_list`'s per-row "Submit a run" link can pre-select
  that source in the "Stored dataset" dropdown.
- **DASH-008**: `GET /health` (`src/app/main.py`) intentionally does *not* consume `GatewayApiUrlDep`
  as a FastAPI `Depends()` parameter (unlike DASH-004/006) -- it calls `get_gateway_api_url()`
  directly as a plain function, since this route itself must stay outside the
  `DownstreamHeadersDep`/session-required family entirely; the shared piece being reused is just the
  one-canonical-env-var-name function, not the DI seam pattern.
- **DASH-111**: `src/app/templates/_dataset_macros.html`'s `date_range(dataset)` macro is a second,
  smaller DRY extraction -- the "earliest to latest" date-range phrase for one `DatasetSummaryResponse`
  item, imported by both `run_new.html`'s "Stored dataset" dropdown option label and `datasets.html`'s
  table cell, rather than two independent copies of the same string formatting.
- Metrics-table rendering shared with `reporting-service`'s HTML report templates would belong in
  `libs/common`, not duplicated between the two (DRY across the module boundary via a shared lib, per
  implementation-plan.md section 9) -- not yet applicable, since `reporting-service` doesn't exist yet
  (trigger #7 unfired).
- **DASH-113**: `src/app/dependencies/operator_session.py`'s `OperatorSessionStore`/
  `require_operator_session` is structurally separate from DASH-002/003's tenant-session mechanism --
  a different cookie name (`operator_session_id`, not `session_id`), a different module-level store
  instance/namespace, and a different dependency (no shared function, no shared dict). It reuses the
  same *mechanism* DASH-002 established (opaque `secrets.token_urlsafe(32)` id in a process-local
  store, never the raw credential in the cookie) rather than inventing a second one, per the ticket's
  own Design section ("same session mechanism DASH-002's tenant login already established -- reused,
  not reinvented"). `src/app/routers/operator.py` (new, disjoint router module, same reasoning
  `gateway-api`'s own `system.py` used for GW-022) declares `GET`/`POST /operator-login` and
  `GET /monitoring`; the latter reuses `runs.py`'s `_call_downstream`/`_render_error_for_status`
  helpers for the transport-failure path rather than a second near-identical try/except (DRY check
  note). `/monitoring` itself is deliberately unauthenticated, matching `gateway-api`'s own GW-022
  no-auth design choice for `GET /system/health` -- viewing this platform's own service health is not
  tenant/operator-sensitive data.
- **DASH-112**: `src/app/routers/settings.py` (new, disjoint router module -- not added to
  `operator.py`, mirroring that file's own precedent of one fresh module per distinct concern) adds
  `GET /settings/connectors`, this service's first `/settings/*` route and the first real consumer of
  `require_operator_session`'s anticipated `get_operator_token_header`/`OperatorTokenHeaderDep` seam
  (`DASH-113`'s docstring named this route as its expected first user). Calls `INGEST-012`'s patched
  `GW-021` proxy (`GET /ingestion/connectors/credentials-status`) directly -- no second
  credential-status query invented -- and reuses `runs.py`'s `_call_downstream`/
  `_render_error_for_status` helpers for the transport-failure/non-200 path, the same DRY-reuse
  `operator.py`'s `/monitoring` route already established.
- **DASH-110**: `src/app/routers/operator.py` (same module `DASH-113`/`DASH-109` already own,
  extended, not a new module -- both trigger routes attach to the same `/monitoring` page's own concern)
  adds `POST /monitoring/connectors/{source}/run` and `POST /monitoring/reports/generate`, both
  depending on `DASH-003`'s `DownstreamHeadersDep` (redirect-to-`/login`, unlike the page's own
  `OptionalDownstreamHeadersDep`) and reusing `runs.py`'s `_call_downstream`/`_render_error_for_status`
  for the transport-failure/non-2xx path -- the same DRY-reuse every other route in this file already
  established, no new near-identical try/except. Each returns a small HTML fragment
  (`_crawl_trigger_result.html` / `_report_trigger_result.html`, `src/app/templates/`, neither extends
  `base.html`) for HTMX to swap into a per-action result `<div>` -- see "Trigger actions on /monitoring
  (DASH-110)" below for the full note.

**Contract**: consumes `gateway-api`'s OpenAPI schema (`POST /runs`, `GET /runs`, `GET /runs/{id}`,
`GET /runs/{id}/splits`, `GET /health`, `GET /system/health`, `GET /ingestion/connectors/credentials-status`,
`GET /ingestion/datasets`, `GET /ingestion/connectors/{source}/status`, `POST /ingestion/connectors/
{source}/run` -- `DASH-110`, `GET /monitoring/crawl-status-fragment` -- `DASH-115`, a route of this
service's own, not gateway-api's, and `POST /reports/generate` -- `DASH-110`); no contract of its own
beyond its rendered HTML routes.
Response shapes are parsed via `naive_first_common.contracts`' shared `RunRequest`/`RunResponse`/
`RunDetailResponse`/`SplitResultResponse`/`RunSummaryResponse` models (ARCH-003) -- the same models
`gateway-api` itself uses -- rather than a third hand-duplicated copy of the same field list.
`RunListResponse` (the `GET /runs` envelope `{items, limit, offset, total}`) is *not* one of those
shared models -- per `gateway-api`'s own README, it is that router's own page/router-local envelope,
so `dashboard-web` works with the parsed dict directly for the envelope fields, only `items` elements
going through the shared `RunSummaryResponse`. `GET /ingestion/connectors/credentials-status`'s
`{"items": [{"source", "credential_set", "last_set_at"}, ...]}` envelope is likewise consumed as a
parsed dict directly, not through a shared model. `POST /ingestion/connectors/{source}/run`'s
`{source, status: "queued", since, queued_at}` response (`INGEST-015`'s async contract, `DASH-115` --
`row_count`/`fetched_at` no longer exist on this response, since the crawl now runs asynchronously) and
`POST /reports/generate`'s `{id, status}` response (`DASH-110`) are both consumed as parsed dicts
directly, same as `gateway-api`'s own README documents for those two proxies -- no local Pydantic model,
since this is a pass-through UI trigger only, not a page that needs to validate/re-render every field of
either response.
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
- `GW-011` (JWT session auth) is not built either -- login uses `gateway-api`'s existing API-key auth
  (`GW-006`) instead (backlog decision 3).
- `DASH-113`'s `POST /operator-login` does not validate the submitted operator token against
  gateway-api at all (no gateway-api endpoint validates a bare token today) -- any non-empty token is
  accepted and stored. `DASH-112`'s `/settings/connectors` is the first route that actually calls an
  operator-gated gateway-api endpoint, so an invalid token now surfaces as that call's own `401`/`403`
  (rendered as the generic `error.html`), not at login time. The full `SETUP-003` setup wizard and
  `SETUP-012` tenant-management UI are not built -- `DASH-113` is only the minimal `/monitoring` page
  and the reusable `require_operator_session` gate.
- `DASH-112`'s `tenant_id` field is a plain manual-entry text input -- no tenant directory/dropdown
  exists yet to look one up or validate it against (an honest reflection of that gap, not a silently
  degraded feature). `SETUP-011` (tenant list/create/revoke admin endpoints, backlog
  `docs/product/backlog-first-run-setup-and-ops.md`) is the eventual fix once it exists; this route will
  switch the field to a real directory-backed lookup at that point, not before.
- `DASH-112`'s `/settings/connectors` is read-only, structurally (no `@router.post` route exists in
  `settings.py`) -- an operator sets a connector credential via
  `services/ingestion-service/scripts/set_connector_credentials.py` (CLI) in the meantime; no write form
  exists on this page this sprint, per the ticket's own unchanged read-only scope (solution-design.md
  8.9(a)).
- `DASH-110`'s "generate a report" form does not offer a run picker -- the tenant types a `run_id`
  manually (the same `POST /reports/generate` contract `GW-018` already exposes; no run-list-with-a-
  "generate report" button integration exists yet). A `run_id` for a run that does not exist, or that
  belongs to another tenant, surfaces as whatever non-`201` status `reporting-service`/`gateway-api`
  themselves return, rendered via the same generic `error.html` -- no client-side existence check is
  performed before submitting.

**Sprint 15**: `DASH-005` (runs list), deferred since Sprint 11, is now built (`DASH-005-01`) -- see
"Runs list (DASH-005)" below. It was blocked on `DASH-005-GAP` (no `GET /runs` list endpoint existed on
`gateway-api`/`validation-service`), closed in Sprint 14 (`VS-022` + `GW-016`). `DASH-009-02` (a
separate, later ticket) will update the existing Selenium E2E suite's flow 3 to navigate via this new
list page instead of Sprint 11's disclosed redirect-id fallback -- not yet done as of this entry.

**Sprint 18**: `DASH-113` adds `GET`/`POST /operator-login` and `GET /monitoring` -- see "Operator
login and monitoring (DASH-113)" below. This is the minimal slice of the sibling backlog's `SETUP-003`
(setup wizard)/`SETUP-012` (tenant-management UI)/`SETUP-020` (monitoring epic) stories pulled into this
sprint for `DASH-109`/`110`/`112`'s sake -- the full setup wizard and tenant-management UI remain that
other backlog's own scope, not built or duplicated here. `DASH-112` (same sprint, revised per a live-UAT
design decision recorded in `docs/sprints/sprint-18.md`) adds `GET /settings/connectors` -- see
"Settings: connector credential status (DASH-112)" below. `DASH-110` (same sprint, last ticket) adds the
two trigger actions on `/monitoring` -- see "Trigger actions on /monitoring (DASH-110)" below.

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

### Stored-dataset context summary (RSS-001)

The "Stored dataset" mode's `#dataset_reference_source` dropdown (`run_new.html`) carries a small,
stable `data-*` attribute contract on each `<option>`, sourced from the same `DatasetSummaryResponse`
fields (`row_count`/`earliest_timestamp`/`latest_timestamp`) `run_new_form` already fetches via
`_fetch_ingestion_datasets` -- no new backend field, no second `GET /ingestion/datasets` call:

- `data-row-count` -- that source's total row count (integer, as a string).
- `data-earliest` -- that source's earliest timestamp (`str(datetime)`, e.g. `2024-01-01 00:00:00+00:00`).
- `data-latest` -- that source's latest timestamp, same format as `data-earliest`.

Selecting a source reads these attributes client-side (inline `<script>` in `run_new.html`, the same
block `checkReference()` lives in) and renders a summary line into `#dataset-source-summary` below the
dropdown -- no page reload, no new server call. If `dataset_reference_start`/`dataset_reference_end`
already have a value when a source is selected (or are edited afterward), the summary line explicitly
labels the row count as the *full source's*, not a value recomputed for the narrowed range -- RSS-003's
territory (a real narrowed-range row count) is not built here. RSS-002 (a live run-size estimate) depends
on this same `data-*` contract; keep those three attribute names stable for that ticket.

### Live split-count estimate (RSS-002)

Same "Stored dataset" fieldset, same inline `<script>` block `checkReference()`/
`updateDatasetSourceSummary()` already live in -- `computeEstimatedSplits()` renders a live
"approximately N split(s)" estimate into a new `#estimated-splits` element (next to RSS-001's
`#dataset-source-summary`) whenever the dropdown's `change` fires or any of `purge_gap_hours`/
`train_window`/`test_window`/`step` fires `input` (not `horizon` -- `generate_splits` takes no horizon
parameter). The formula is `naive_first_engine.splitting.generate_splits`'s row-count
(position-based) branch closed form -- see `_generate_splits_by_position` there for the authoritative
definition, not restated here a third time -- including its `purge_gap_hours`-as-a-literal-row-offset
semantics (the OQ-3 naming mismatch, `docs/product/backlog-run-submission-safety.md`, disclosed and out
of scope this sprint). When no stored dataset is selected (or a required numeric field is blank/
non-numeric), the element shows "Select a stored dataset to see an estimate." instead of a stale or
fabricated number. **This is informational only** -- it adds no new `event.preventDefault()` and does
not gate `form`'s `submit` event; `checkReference()` remains the sole client-side submission gate.
**This estimate is not the safety backstop** -- RSS-004's server-side check (`validation-service`/
`gateway-api`) is the actual guardrail against a run with too few/zero splits; this estimate exists only
so a tenant doesn't have to submit-and-see to find out. `tests/test_runs_submit.py`'s RSS-002 tests cover
(a) a Jinja-render-level assertion that `computeEstimatedSplits` and its event-listener wiring are
present in the rendered HTML (no JS-execution harness exists in this service's default suite for this),
and (b) a Python-side cross-check that the formula's own closed form matches
`naive_first_engine.splitting.generate_splits`'s real output for a synthetic, gapless hourly index
(added as a dev-only dependency on `naive_first_engine`, used only by this test, never imported by
`app/` code) -- guarding against formula drift between this client estimate and RSS-004's server check.

## Runs list (DASH-005)

`GET /runs` (`src/app/routers/runs.py`, DASH-005-01, Sprint 15) renders one row per tenant-scoped run,
in the server's own `created_at DESC` order:

- Resolves `headers: DownstreamHeadersDep`/`base_url: GatewayApiUrlDep` (DASH-003) -- no hand-rolled
  `Authorization` header, same as every other route here. Calls `gateway-api`'s real `GET /runs`
  (GW-016, itself a pass-through proxy of `validation-service`'s `GET /runs`, VS-022); `limit`/`offset`
  query params on the incoming request are forwarded to `gateway-api` unmodified (no locally invented
  defaults, no re-validation of `gateway-api`'s/`validation-service`'s own bounds).
- Parses the response envelope as `{"items": [...], "limit": ..., "offset": ..., "total": ...}`; each
  item is validated via the shared `naive_first_common.contracts.RunSummaryResponse` (imported, not
  redefined). `RunListResponse` itself is **not** imported from `naive_first_common.contracts` -- it
  does not exist there; per `gateway-api`'s own README, it is that router's own page/router-local
  envelope, so this route works with the parsed dict directly for the envelope fields.
- Renders `runs_list.html` with one row per run (`id` linking to DASH-004's `GET /runs/{id}`, `status`,
  `dataset_id`, `horizon`, `created_at`, `completed_at`), in the order `gateway-api`/`validation-service`
  returned them -- no client-side re-sort. Zero runs renders a plain "no validation runs yet" message,
  not an error.
- A transport-level `httpx.ConnectError`/`httpx.TimeoutException`, a `502`/`504` forwarded from
  `gateway-api`, or any other non-`200` (e.g. a `422` for an out-of-range `limit`/`offset`, since this
  list page has no form to redisplay a field-specific error against) reuses the same `error.html`
  DASH-004/006 already use, via the new `_render_error_for_status` helper -- no new error template, no
  leaked hostname/status/exception text.
- **Positioning**: `runs_list.html`'s copy describes the rows as "validation runs" / "validation/audit
  records" only -- never "prediction," "forecast," "signal," or "recommendation" (CLAUDE.md's core
  positioning constraint), matching `run_detail.html`'s existing convention.
- No client-side pagination, sorting, local record-keeping, or scraping of any other page is
  introduced -- this route calls `gateway-api`'s own list endpoint and renders exactly what it returns.

## Ingested datasets (DASH-111)

`GET /datasets` (`src/app/routers/runs.py`) lists all of a tenant's ingested datasets (source,
earliest/latest timestamp, row_count) via `gateway-api`'s `GET /ingestion/datasets` (GW-020) --
the same call `run_new_form`'s (DASH-108) "Stored dataset" dropdown already makes:

- **Shared fetch, not duplicated** (this ticket's own binding DRY/Review acceptance criterion):
  `_fetch_ingestion_datasets(client, headers)` (`src/app/routers/runs.py`) is `run_new_form`'s original
  inline fetch-and-degrade logic pulled out into one function; `datasets_list` (this route) and
  `run_new_form` both call it -- neither has its own copy of the "call `GET /ingestion/datasets` and get
  the list of items back" logic. Each item is parsed via the shared
  `naive_first_common.contracts.DatasetSummaryResponse` (imported, not redefined), same as
  `run_new_form` already did. A transport failure or non-200 response degrades to an empty list (the
  same "no ingested datasets yet" empty state a real empty-history tenant sees), matching
  `run_new_form`'s own degrade-don't-block precedent.
- Renders `datasets.html`, one row per source, with a "Submit a run" link
  (`/runs/new?dataset_reference_source=<source>`) and a "Trigger a crawl" link (`/monitoring`, a
  forward-compatible placeholder as of this ticket -- `DASH-110` is what actually wires up a real
  per-source crawl trigger, on `/monitoring` itself, not on this page; this route's own link still just
  navigates there, not a second copy of the trigger form).
  `run_new_form` grew a matching optional `dataset_reference_source` query param, so following the
  "Submit a run" link pre-selects that source in the "Stored dataset" dropdown via the same
  `values.dataset_reference_source == dataset.source` template comparison `run_new_submit`'s own
  error-redisplay path already used -- no second selection mechanism.
- `_dataset_macros.html`'s `date_range(dataset)` macro (imported by both `datasets.html` and
  `run_new.html`) is a second, smaller DRY extraction: the "earliest to latest" phrase for one dataset,
  shared instead of duplicated between the dropdown option label and the table cell.
- **Positioning**: `datasets.html`'s copy describes rows as ingested/raw data available for a validation
  run only -- never "prediction," "forecast," "signal," or "recommendation" (CLAUDE.md's core
  positioning constraint), proven by `tests/test_datasets.py`'s own banned-word test.
- Zero datasets renders the same "No ingested datasets yet -- run a crawl first." message `run_new.html`
  already shows for this case, not an error.

## Operator login and monitoring (DASH-113)

Minimal slice of the sibling backlog's `SETUP-003` (setup wizard)/`SETUP-012` (tenant-management
UI)/`SETUP-020` (monitoring epic) pulled into Sprint 18 for `DASH-109`/`110`/`112`'s sake -- the full
setup wizard and tenant-management UI remain that other backlog's own scope, not built here:

- `GET /operator-login` renders a single-field (operator token) form; `POST /operator-login`
  (`src/app/routers/operator.py`, new router module) does **not** call gateway-api to validate the
  submitted token (no gateway-api endpoint validates a bare token without also doing something else
  yet, per the ticket's own Analysis section) -- any non-empty token is stored, unvalidated, in
  `OperatorSessionStore` (`src/app/dependencies/operator_session.py`) and set as an `operator_session_id`
  cookie (`httponly`, `samesite=lax`, `secure` gated by the same `DASHBOARD_COOKIE_SECURE` env var
  DASH-002 already reads), then redirects (303) to `/monitoring`. A blank submission redisplays the
  form with a `422` and an error, the same convention `login.html`'s own empty-key path established.
- **Structurally distinct from the tenant session** (DASH-002/003, Review acceptance criteria): a
  different cookie name (`operator_session_id` vs `session_id`), a different store instance/namespace
  (`OperatorSessionStore` vs `SessionStore`, no shared dict), and a different dependency
  (`require_operator_session` vs `get_session_headers`). A tenant's own session cookie can never satisfy
  `require_operator_session`, and vice versa -- proven in `tests/test_operator_session.py` and, for its
  first real route consumer, `tests/test_settings_connectors.py` (`DASH-112`).
- `require_operator_session` (`RequireOperatorSessionDep`) is a reusable FastAPI dependency gating any
  `/settings/*` route (`DASH-112`'s `/settings/connectors` is its first real consumer, via the
  `get_operator_token_header`/`OperatorTokenHeaderDep` seam this same module also provides). Mirrors
  DASH-003's `get_session_headers` redirect-not-401 precedent (backs HTML-rendering routes, not a JSON
  API): a missing/unresolvable operator-session cookie raises
  `HTTPException(303, headers={"Location": "/operator-login"})` before any dependent route body runs.
- `GET /monitoring` calls gateway-api's `GET /system/health` (GW-022, itself requiring no auth) and
  renders one row per service (`gateway-api`, `validation-service`, `reporting-service`,
  `ingestion-service`) with its reported `"ok"`/`"degraded"`/`"unreachable"` status, verbatim, no
  reinterpretation. Deliberately **not** gated behind `require_operator_session` in this ticket's own
  scope -- kept consistent with GW-022's own no-auth design choice, since viewing this platform's own
  service health is not tenant/operator-sensitive data. Reuses `runs.py`'s `_call_downstream`/
  `_render_error_for_status` helpers for the case where the aggregate call to gateway-api itself fails
  entirely (network error/timeout, or a non-`200` from gateway-api) -- renders the existing generic
  `error.html` "results currently unavailable" page, no hostname/status/exception text leaked, no new
  near-identical try/except (DRY check note).
- **Positioning**: `operator_login.html`/`monitoring.html`'s copy describes this as operational status
  of the platform's own services only -- never "prediction," "forecast," "signal," or "recommendation"
  (CLAUDE.md's core positioning constraint).

### Last crawl status panel (DASH-109)

Extends the same `/monitoring` page/route (not a second page, per the ticket's Review acceptance
criteria) with a second panel below the four-row service-status table:

- **The fourth health row required no code change**: `monitoring.html`'s existing `{% for name,
  status in services.items() %}` loop already renders every key `GET /system/health`'s response
  carries, generically -- `GW-022` already returning a fourth `ingestion-service` key was sufficient
  by itself, confirmed (not assumed) by this ticket and by `test_monitoring_all_healthy`'s
  `>ok<` count.
- **New gateway-api proxy**: `services/gateway-api/src/app/routers/ingestion.py`'s
  `GET /ingestion/connectors/{source}/status` (DASH-109 addition to the `GW-019`/`GW-020` router)
  proxies `ingestion-service`'s real `GET /connectors/{source}/status` (`INGEST-009`), gated by
  `get_authenticated_tenant`, same handler flow as every other route in that file. See
  `services/gateway-api/README.md`'s own "Request routing to `ingestion-service`" section for the full
  contract note.
- **Auth design decision (`/monitoring` itself stays unauthenticated)**: the panel needs a
  `TenantContext` to call `GET /ingestion/datasets`/`GET /ingestion/connectors/{source}/status`, but
  gating the whole page behind `DownstreamHeadersDep` would break `GW-022`'s/`DASH-113`'s own no-auth
  requirement for `/monitoring` (`test_monitoring_requires_no_session` must keep passing).
  `app.dependencies.downstream.get_optional_session_headers`/`OptionalDownstreamHeadersDep` (DASH-109
  addition, same module) is a non-raising counterpart to `get_session_headers` -- it reuses the exact
  same cookie-read/`SessionStore.get` call rather than a second copy, and returns `None` instead of
  redirecting when no tenant session exists. The page itself always renders; the panel shows a plain
  "log in to view your own ingestion status" message when `headers is None`, the real per-source table
  once a tenant session cookie is present, and "no ingested sources yet" for a logged-in tenant with an
  empty `GET /ingestion/datasets` response.
- `src/app/routers/operator.py`'s `_fetch_crawl_statuses(client, headers)` lists the tenant's sources
  via `GET /ingestion/datasets` (GW-020, same call `DASH-108`/`DASH-111` already make), then calls the
  new per-source status proxy once per source; a failure on the datasets call degrades the whole panel
  to `None` (the login-or-unavailable state), and a single source's own status call failing is skipped
  rather than failing the whole panel -- the same "one bad downstream must not fail the whole aggregate"
  principle `GW-022`'s own health-row aggregation already established.
- **Positioning**: `monitoring.html`'s panel copy labels this "Last crawl status" and describes it as a
  plain run-status record, explicitly not a claim about data quality -- never "prediction," "forecast,"
  "signal," or "recommendation" (CLAUDE.md's core positioning constraint, proven by the existing
  `test_monitoring_template_has_no_banned_positioning_words` test, unchanged and still passing).
- **`DASH-115` (Sprint 20): self-refreshing panel**. `INGEST-015` made the underlying crawl-trigger call
  asynchronous, so a snapshot taken once at page load would otherwise show "queued" indefinitely until a
  manual reload. The table markup above was extracted into `src/app/templates/_crawl_status_panel.html`
  (a Jinja `{% include %}`-able partial, the same shared-partial pattern `_dataset_macros.html` already
  established) so both `monitoring.html`'s own initial render and a new `GET
  /monitoring/crawl-status-fragment` route (`src/app/routers/operator.py`) render the exact same file --
  one implementation, not two. The panel's own `<div id="crawl-status-panel">` carries
  `hx-get="/monitoring/crawl-status-fragment" hx-trigger="load, every 5s" hx-swap="outerHTML"`; because
  `hx-swap="outerHTML"` replaces the element carrying those attributes on every poll, `_crawl_status_panel
  .html` itself (not just `monitoring.html`'s initial render) repeats them on its own outer `<div>`, which
  is what keeps the polling self-sustaining rather than firing once and stopping. 5s is a disclosed,
  arbitrary interval, not a performance-tuned one. The new route is gated by `DownstreamHeadersDep` (not
  the parent page's own `OptionalDownstreamHeadersDep`) -- an anonymous visitor has no crawl status of
  their own to poll -- and reuses `_fetch_crawl_statuses` unmodified; a downstream failure renders a
  small error fragment via `_render_error_for_status` (a disclosed `502`, since that helper does not
  preserve which specific transport/status failure occurred) rather than the page's own login-prompt
  state, since `headers` is never `None` on this route.

## Trigger actions on /monitoring (DASH-110)

Two `POST` action routes attached to `src/app/routers/operator.py` (same module the two sections above
already own -- not a new router module, per the ticket's own Design section: "extend `DASH-113`'s
`/monitoring` template/route"), both rendered only inside the crawl-status panel's own logged-in branch
(`crawl_statuses is not none`, DASH-109's own auth gate reused, not a second one):

- **`POST /monitoring/connectors/{source}/run`**: one button per source row in the crawl-status panel
  ("Run this tenant's {source} crawl now"), calling `gateway-api`'s already-existing `GW-019` proxy
  (`POST /ingestion/connectors/{source}/run`). Depends on `DASH-003`'s `DownstreamHeadersDep` (not the
  page's own `OptionalDownstreamHeadersDep`) -- an action route has no "render for an anonymous
  visitor" case, unlike the read-only page above. On a `202`, renders `_crawl_trigger_result.html`
  (`{source, status, since}` from the forwarded response body, verbatim) for HTMX to swap into that
  row's own result `<div>`. **`DASH-115` (Sprint 20)**: `INGEST-015` made this call asynchronous
  (`202 {source, status: "queued", since, queued_at}` -- `row_count`/`fetched_at` no longer exist on
  this response), so `_crawl_trigger_result.html` now renders "Crawl for {source} queued (since
  {since})" only -- it never claims the crawl already finished; the crawl-status panel's own polling
  (see "Last crawl status panel (DASH-109)" above) is what surfaces real progress toward
  `"completed"`/`"failed"`.
- **`POST /monitoring/reports/generate`**: one form (single `run_id` text input, "Generate a report"
  button) calling the already-existing `GW-018` proxy (`POST /reports/generate`) -- no new reporting
  capability of any kind is added anywhere in this codebase by this ticket; `reporting-service`'s real
  report-generation logic (RS-002/RS-004) already existed end to end before this ticket, this is a UI
  trigger for it only. On a `201`, renders `_report_trigger_result.html` (`{id, status}`, verbatim) for
  HTMX to swap into a fixed `#report-trigger-result` `<div>`.
- **"No full-page reload"** (ticket Implementation acceptance criteria) is satisfied via HTMX
  (`hx-post`/`hx-target`/`hx-swap` attributes on each form in `monitoring.html`) -- `base.html` already
  loads `htmx.org` (present since this service's scaffold, unused by any route until this ticket); this
  is that script's first real consumer, not a newly introduced client-side dependency or pattern.
- **Failure handling is identical to every other route in this service**: a transport-level
  `httpx.ConnectError`/`httpx.TimeoutException`, or any non-`202`/non-`201` status forwarded from
  `gateway-api`, reuses `runs.py`'s `_render_error_for_status` unmodified -- the same generic
  `error.html` "results currently unavailable" page, no hostname/status/exception text leaked, no new
  error-handling pattern introduced for this ticket. HTMX swaps that response's body into the same
  small result `<div>` the success fragment would have used.
- **Structural proof (ticket Implementation acceptance criteria)**: `grep -rn "docker\|subprocess" -i
  services/dashboard-web/src` returns zero hits -- every action added by this ticket is exactly one
  outbound `httpx` call to `gateway-api`'s own already-running, already-authenticated HTTP contract,
  never a container-runtime socket or a locally spawned OS-level process. This is a structural
  guarantee (there is no code path in this service that could do otherwise), not a policy statement to
  take on faith.
- **Positioning**: `_crawl_trigger_result.html`/`_report_trigger_result.html`'s copy describes the
  results as a plain crawl-run/report-generation status only -- never "prediction," "forecast,"
  "signal," or "recommendation" (CLAUDE.md's core positioning constraint).
- **Tests**: `tests/test_monitoring_triggers.py` covers both actions' success and failure paths
  (non-2xx from `gateway-api`, transport `ConnectError`/`TimeoutException`, and the session-required
  redirect for an unauthenticated `POST`), mocking `gateway-api` the same `httpx.Client`-monkeypatching
  convention `tests/test_monitoring.py` already established, plus that `monitoring.html` renders (and
  hides) the two `hx-post` forms exactly when the crawl-status panel itself is (or is not) populated.
- **DASH-114** (Sprint 19): the per-source crawl-trigger form gained one optional `<input type="date"
  name="since">`, labeled as only taking effect on that tenant's first-ever crawl of this source. A
  blank/omitted value sends no `since` param at all (byte-for-byte the same outbound request as before
  this ticket); a non-blank value is forwarded verbatim as the `since` query param on the outbound
  `POST /ingestion/connectors/{source}/run` call, via `trigger_crawl`'s new `since: str = Form("")`
  parameter -- the same `Form(...)`-field convention `trigger_report_generation`'s `run_id` already
  established, not a new one. No new error-handling path: a downstream `422` (bad/future/before-earliest
  date) renders via the existing `_render_error_for_status` fragment, unchanged. See `INGEST-013`/
  `GW-023` for the underlying `since` override semantics and validation rules (not re-documented here).

## Settings: connector credential status (DASH-112)

`GET /settings/connectors` (`src/app/routers/settings.py`, new router module -- not added to
`operator.py`, mirroring that file's own precedent of one fresh module per distinct concern) is a
**per-tenant, read-only** connector credential-status lookup, revised per a live-UAT design decision
recorded in `docs/sprints/sprint-18.md`'s UAT addendum (originally scoped as a cross-tenant aggregate;
an operator now supplies a `tenant_id` explicitly instead):

- Gated by `DASH-113`'s `require_operator_session` via `OperatorTokenHeaderDep`
  (`app.dependencies.operator_session.get_operator_token_header`) -- this route never hand-rolls its
  own cookie read/store lookup, and a tenant's own `session_id` cookie is never read here, so it can
  never satisfy this gate (the cross-boundary case this ticket exists to close, proven in
  `tests/test_settings_connectors.py`).
- `tenant_id` is an optional query parameter with three cases: no param at all renders the initial,
  unsubmitted form with no error; a present but blank/whitespace-only value redisplays the form with a
  `422` and a "Enter a tenant id." error, never a raw passthrough; a non-blank value is forwarded to
  `gateway-api` unmodified. An **unrecognized** tenant id is not a distinguishable case at this layer --
  `INGEST-012`'s patched `GW-021` proxy (`GET /ingestion/connectors/credentials-status`) itself returns
  a normal `200` with per-source `credential_set: false` entries for a tenant with no stored
  credentials (`ingestion-service`'s own "empty is a valid answer" convention), so this route renders
  whatever `items` list comes back with no special-casing.
- Lists, per source, whether a credential is stored (boolean) and its last-set timestamp -- never the
  credential value itself; the proxied endpoint never returns one.
- **No write route**: structurally, no `@router.post` exists anywhere in `settings.py` -- an operator
  uses `services/ingestion-service/scripts/set_connector_credentials.py` (CLI) to write a credential in
  the meantime; this page does not grow a write form this sprint (solution-design.md 8.9(a), unchanged).
- **Manual `tenant_id` entry, disclosed**: the `tenant_id` field is a plain text input, not a
  directory/dropdown -- no tenant-list UI exists yet (`SETUP-011`, backlog
  `docs/product/backlog-first-run-setup-and-ops.md`, is the eventual fix once it exists). This is an
  honest reflection of that gap, not a silently degraded feature.
- **Positioning**: `settings_connectors.html`'s copy describes this as "connector credential status"
  only -- never "prediction," "forecast," "signal," or "recommendation" (CLAUDE.md's core positioning
  constraint).

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

**Tests**: `uv run pytest` (route-handler unit tests, mocked `gateway-api`) from this directory -- the
`e2e` marker's items deselected by default (`addopts = "-m \"not e2e\""` in `pyproject.toml`).
`tests/test_settings_connectors.py` (`DASH-112`) follows the same `httpx.Client`-monkeypatching
convention `tests/test_monitoring.py` established and the same operator-session-cookie setup
`tests/test_operator_login.py` established. `tests/test_datasets.py` (`DASH-111`) reuses the same
`httpx.Client`-monkeypatching convention `tests/test_runs_submit.py`'s `GET /ingestion/datasets` tests
already established, covering empty-history rendering, populated-history rendering, a transport-failure
degrade, the session-required redirect, and `run_new_form`'s `dataset_reference_source` pre-fill.
`tests/test_monitoring_triggers.py` (`DASH-110`) reuses `tests/test_monitoring.py`'s
`httpx.Client`-monkeypatching convention and `tests/test_runs_submit.py`'s tenant-session-cookie login
helper -- covering both trigger actions' success/failure/session-required cases, no new mocking
convention (101 unit tests passing as of that ticket, up from 90, plus 5 e2e). `DASH-115` (Sprint 20)
extended `tests/test_monitoring.py` with `GET /monitoring/crawl-status-fragment` coverage (matches the
page's own embedded panel markup for the same stubbed state, carries its own polling attributes,
requires a tenant session, degrades to a small error fragment on a downstream failure) and updated
`tests/test_monitoring_triggers.py`'s crawl-trigger success case to `INGEST-015`'s real `202 {source,
status: "queued", since, queued_at}` shape -- 109 unit tests passing as of this ticket, up from 101,
plus the same 5 e2e (unaffected -- the Selenium suite never exercises `/monitoring`). `RSS-002` (see
"Live split-count estimate (RSS-002)" above) added two more tests to `tests/test_runs_submit.py` --
113 unit tests passing as of this ticket, up from 111 (still `-m "not e2e"` by default), plus the same
5 e2e.

**DASH-009 -- Selenium E2E suite** (`tests/e2e/`, the first browser-level suite in this platform): run
separately via `uv run pytest -m e2e` -- 5 tests, exercising login (valid + invalid key), submit-a-run
(valid + invalid payload), and view-a-run (completed run + nonexistent id), each in a real browser
against a real running `dashboard-web` subprocess.
- **Flow 3 navigation (`DASH-009-02`, Sprint 15)**: view-a-run now navigates via the real `GET /runs`
  list page (`DASH-005-01`) -- the test clicks the just-created run's own link on the list page rather
  than driving straight to the post-submit redirect URL. The original Sprint 11 framing ("no
  runs-list page exists this sprint," the `DASH-005-GAP` redirect-id-only fallback) is now historical;
  see `docs/tickets/DASH-009.md`'s Outcome section for the full note. The run id is still obtained
  from the submit flow's own redirect -- only how the test reaches the detail page changed.
- **Browser/WebDriver**: Chrome, auto-resolved by Selenium's built-in Selenium Manager (bundled with
  `selenium>=4.20`, a dev dependency) -- no manual `chromedriver` install needed in most environments.
  To use a different browser/driver, set Selenium's own standard driver-path env vars before running.
- **Fixture `gateway-api`**: automatic, no setup required -- `tests/e2e/conftest.py`'s
  `stub_gateway_api` session fixture starts a minimal stub implementing just enough of `gateway-api`'s
  real contract (`/health`, `POST /runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`) as
  its own subprocess (the `GET /runs` handler was added by `DASH-009-02` to support the real list-page
  navigation above). Does not require `infra/docker-compose.yml` or a real Postgres/Redis stack.
- **Environment note**: if this repo directory sits inside a cloud-synced folder (e.g. OneDrive), you
  may see intermittent file-write/`.venv`-creation failures unrelated to this suite's own code; setting
  `UV_PROJECT_ENVIRONMENT` to a path outside the synced tree before `uv sync`/`uv run` works around it.

**CI**: not yet wired into `.github/workflows/ci.yml` (OPS-001) -- planned as a follow-up once this
service's Sprint 11 scope is done and stable.
