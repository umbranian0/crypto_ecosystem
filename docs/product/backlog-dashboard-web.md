# Backlog — dashboard-web

Source: `docs/da-tese-ao-produto.md` (positioning constraints, sections 2.2/2.7), `docs/solution-design.md` (section 1, 3.6, 4, 6), `docs/implementation-plan.md` (sections 2, 6, 7, 9), `services/dashboard-web/README.md`, `services/gateway-api/README.md` (Authentication, Contract), `services/validation-service/README.md` (Routes list), `docs/tickets/README.md`, `docs/tickets/GW-008.md`, `libs/sdk/README.md`.

Scope: `services/dashboard-web` only. In scope: login/session, runs list + detail, submit-a-run form, an E2E test story. Out of scope: reporting-service, monitoring, ingestion upload UI, admin/provisioning UI, multi-tenant switching, libs/sdk.

## Explicit trigger override

Trigger #8 has NOT fired (no pilot client exists). Built anyway at explicit user request, same disclosed-override precedent as gateway-api (trigger #5) and ingestion-service connectors (trigger #6/#10).

## Explicit scope/dependency decisions

1. Trigger override recorded above.
2. `libs/sdk` confirmed not relevant — dashboard-web calls gateway-api directly, same as an external client.
3. Login uses gateway-api's existing Must-priority API-key auth (GW-006), not JWT (GW-011, Should, not built).
4. No `GET /runs` list endpoint exists on gateway-api or validation-service today — flagged as DASH-005-GAP, a new item for those modules' own backlogs, not invented client-side here.
5. Reporting/monitoring surfaces excluded deliberately (triggers #7 and build-order step 7 unfired).
6. DASH-009 (Selenium E2E) added at explicit user request as a testing/tooling story, sequenced last.

## Stories

### DASH-001 — Service scaffolding [Must]
As a Tech Lead standing up dashboard-web, I want a uv-managed FastAPI + Jinja2/HTMX skeleton, so that every other story has a place to live and a working test runner.

Acceptance criteria:
- [ ] `services/dashboard-web/pyproject.toml` declares the FastAPI app + Jinja2/HTMX deps; no import of another service's code, only `httpx` to call gateway-api.
- [ ] `src/app/` skeleton (`routers/`, `dependencies/`, `templates/`).
- [ ] `tests/` with working pytest config; `uv run pytest` passes with 0 collected as baseline.
- [ ] README status moves planned -> scaffolded, with the trigger-#8 override note.

Rationale: nothing else can be built without a skeleton.
Depends on: none

### DASH-002 — Login screen exchanging a tenant API key for a server-side session [Must]
As dashboard-web, I want a login screen accepting a tenant's gateway-api API key and establishing a server-side session, so that the dashboard isn't a hardcoded-key demo and every page can attach the right header.

Acceptance criteria:
- [ ] `GET /login` renders a form for the raw API key (gateway-api has no JWT/email login today, only GW-006's key check).
- [ ] `POST /login` stores the key in a new server-side session + secure HttpOnly cookie; validation is lazy (first authenticated gateway-api call proves validity via its 401 behavior) since no dedicated verify endpoint exists.
- [ ] A 401 from any downstream call redirects to `/login` with an error and clears the session.
- [ ] Raw key never rendered in HTML/JS, never logged, never in a URL; only sent as `Authorization: Bearer <key>` (gateway-api's documented header contract).
- [ ] Tests: valid key stored/forwarded (mocked gateway-api); empty key rejected before session creation; a session that gets a 401 downstream is invalidated and redirected.

Rationale: first of the three required minimum-scope items.
Depends on: DASH-001

### DASH-003 — Session-to-downstream-header dependency (DI seam) [Must]
As dashboard-web, I want one `Depends()` dependency resolving session -> API key -> outbound headers, so that every gateway-api call shares one auth-forwarding mechanism (DRY, matches gateway-api's own `build_downstream_headers` precedent).

Acceptance criteria:
- [ ] A dependency reads the session cookie, resolves the stored key, returns `{"Authorization": f"Bearer {key}"}` plus `GATEWAY_API_URL` (env var, no hardcode).
- [ ] No route hand-rolls its own header — all of DASH-004/005/006 go through this one dependency.
- [ ] A request with no valid session is rejected here, before route logic runs.
- [ ] Unit test confirms header shape and that unauthenticated requests never reach route logic.

Rationale: enabling story required by DRY/INVEST-small; without it every route duplicates the same logic.
Depends on: DASH-002

### DASH-004 — Run detail view (status + per-split results) [Must]
As dashboard-web, I want a page calling gateway-api's `GET /runs/{id}` and `GET /runs/{id}/splits` and rendering status + per-split results, so that a tenant can see a run's outcome without a manually-sent file.

Acceptance criteria:
- [ ] Calls `GET /runs/{id}` and renders `id, status, dataset_id, horizon, purge_gap_hours, created_at, completed_at, failure_reason` (confirmed field set, GW-008).
- [ ] If splits exist, calls `GET /runs/{id}/splits` and renders each split's boundaries, model/naive0 metrics (mae/rmse/smape/mase/da/f1/oos_r2), and `dm_statistic/dm_pvalue/dm_verdict` verbatim — no recomputation/reinterpretation (NFE-012's Harvey correction already applied upstream).
- [ ] No language implying price prediction or trading signal (CLAUDE.md positioning) — validation/audit framing only.
- [ ] gateway-api's 404 (nonexistent or cross-tenant, both collapsed upstream) renders a plain "not found" page, no distinction shown.
- [ ] gateway-api's 502/504 render a generic "results currently unavailable" message, no leaked internals.
- [ ] Tests (mocked gateway-api): success with splits; running-with-no-splits; 404; 502/504.

Rationale: second required minimum-scope item; both endpoints already exist.
Depends on: DASH-003

### DASH-005 — Runs list view [Must, done]
As dashboard-web, I want a page listing the tenant's runs, so a user can find a run without knowing its ID.

Acceptance criteria:
- [x] **Cannot be completed as specified today** — no `GET /runs` list endpoint exists on gateway-api or validation-service (confirmed by reading both READMEs' Contract/Routes sections). (Satisfied by construction once DASH-005-GAP closed in Sprint 14 — see below.)
- [x] No client-side substitute is invented (no local record-keeping/scraping) — see DASH-005-GAP.
- [x] Once DASH-005-GAP is resolved, this page calls the new tenant-scoped list endpoint and renders one row per run (id/status/dataset_id/horizon/created_at/completed_at), linking to DASH-004, most-recent-first.
- [x] Until resolved, the "see results" loop is only satisfiable via DASH-004 directly (e.g. the id returned by DASH-006's submit flow) — a disclosed gap, not a silent substitution, requiring explicit requester acknowledgment before scheduling. (This gap is now closed by `DASH-005-01`, Sprint 15.)

Rationale: Must per requested minimum scope, was blocked on a capability neither upstream service exposed — flagged, not faked (mirrors VS-010's own "blocked" precedent) — now unblocked and done (`DASH-005-01`, Sprint 15, `docs/tickets/DASH-005-01.md`) since DASH-005-GAP closed in Sprint 14 (`VS-022` + `GW-016`).
Depends on: DASH-005-GAP (closed, Sprint 14), DASH-003

### DASH-005-GAP — Flagged capability gap (not a dashboard-web story)
Confirmed missing: gateway-api proxies exactly `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`; validation-service's own Routes list has no list route either. Needed: a tenant-scoped `GET /runs` list endpoint on validation-service (paginated/bounded, ordered by `created_at` desc, tenant-isolated like `GET /runs/{id}`) plus a matching gateway-api proxy route (GW-008's pattern). Belongs as new tickets in `docs/product/backlog-validation-service.md` (new VS-0NN) and `docs/product/backlog-gateway-api.md` (new GW-016, since GW-015 is reserved/Won't) — not authored here, since dashboard-web owns no data access.

### DASH-006 — Submit-a-run form [Must]
As dashboard-web, I want an HTML form submitting a new run through gateway-api's `POST /runs`, so the PoC demonstrates submit -> running/complete -> view results, not just read-only viewing.

Acceptance criteria:
- [ ] `GET /runs/new` renders a form matching gateway-api's real `POST /runs` request shape exactly (GW-008): `dataset_id` (str), `dataset_reference` (supports validation-service's interim inline-payload/local-file modes), `horizon` (>=1), `purge_gap_hours` (>=0), `train_window/test_window/step` (>0).
- [ ] `POST /runs/new` submits via DASH-003's headers to gateway-api's real `POST /runs`; on 201 redirects to DASH-004's detail page for the returned id.
- [ ] No new run-execution logic, config default, or shortcut is introduced — pass-through UI only; no field/default can cause a run to skip the purge gap or mandatory naive baselines.
- [ ] A 422 redisplays the form with the specific error; client-side checks mirror the same constraints but do not replace server-side validation.
- [ ] After redirect, DASH-004 reflects the run's real initial status (running/completed/failed per VS-006/VS-012) — no fabricated optimistic state.
- [ ] Tests (mocked gateway-api): valid submit redirects; 422 redisplays form with error; 201 status:"failed" redirects to detail and is distinguishable there from a 502/504 transport failure.

Rationale: third required minimum-scope item; `POST /runs` already exists.
Depends on: DASH-003, DASH-004

### DASH-007 — Logout / session invalidation [Should]
As a logged-in user, I want to log out, so a shared/unattended session doesn't leave a key usable indefinitely.

Acceptance criteria:
- [ ] Logout clears the session/cookie, redirects to `/login`.
- [ ] Old session cookie rejected after logout (via DASH-003's dependency, no new mechanism).

Rationale: cheap closure of login, not part of the three required items — Should.
Depends on: DASH-002, DASH-003

### DASH-008 — Health check endpoint [Should]
As an operator, I want `GET /health` to check real connectivity to gateway-api, matching OPS-005-01/02's precedent.

Acceptance criteria:
- [ ] Real check (e.g. request to gateway-api's `/health`), not hardcoded `ok`.
- [ ] Success: `200 {"status":"ok"}`. Failure: `503 {"status":"unhealthy","detail":"gateway-api unreachable"}` — fixed generic string.

Rationale: matches an established low-cost convention, not part of the three required items — Should.
Depends on: DASH-001

### DASH-009 — Selenium browser-level E2E test suite for the core PoC loop [Should]
As a Tech Lead responsible for this PoC's quality, I want a Selenium WebDriver-driven E2E suite exercising the dashboard's HTMX pages in a real browser against a real running instance, so the login -> submit -> view-results loop is verified as an actual user experiences it (HTMX swaps, redirects, cookie session behavior) — beyond what route-handler pytest unit tests alone prove.

This is a testing/tooling story, not a new feature — it adds no new page/route/capability beyond DASH-002/004/006. Sequenced last, after the functionality it exercises exists.

Acceptance criteria:
- [ ] `services/dashboard-web/tests/e2e/` contains a Selenium WebDriver suite run against a real running `dashboard-web` instance (not in-process TestClient) pointed at a test/fixture gateway-api (stub or real service seeded with a known test tenant/key — implementer's choice, documented).
- [ ] Covers at minimum three flows: (1) successful login — valid key on `/login`, lands authenticated, session cookie present; (2) submit a run end-to-end — fill/submit DASH-006's form, redirected to the new run's detail page; (3) view a completed run — navigate to a known completed run's detail page and assert the rendered status + per-split metrics table are present in the DOM.
- [ ] Each flow also asserts at least one negative/edge case already specified elsewhere in this backlog (e.g. invalid/expired session redirects to `/login`, or a 404 run renders the not-found page) — proves it renders correctly in a real browser, does not invent new behavior.
- [ ] Documented/run separately from the default `uv run pytest` unit loop (e.g. `pytest -m e2e` marker or separate script) since it needs a running server + browser driver.
- [ ] README documents how to run the suite locally (driver/browser prerequisite, how the fixture gateway-api is stood up).

Rationale: valuable additional confidence at the real-browser level, but not required for the three-item minimum scope's own delivery/testability — Should, sequenced last since it tests functionality that must already exist.
Depends on: DASH-002, DASH-004, DASH-005 (or its DASH-005-GAP fallback), DASH-006

### DASH-101 — Won't: report viewer [Won't]
Not proposed. `services/reporting-service` (trigger #7) doesn't exist — no report artifact to view.

### DASH-102 — Won't: degradation-alerts / continuous-monitoring view [Won't]
Not proposed. Build-order step 7 (recurring runs, alerts) not reached — this PoC only shows explicitly submitted/looked-up runs.

### DASH-103 — Won't: dataset upload UI [Won't]
Not proposed. `ingestion-service`'s upload API (trigger #6) unfired — DASH-006's form already exposes validation-service's interim inline-payload/local-file modes, nothing more.

### DASH-104 — Won't: multi-tenant switching UI [Won't]
Not proposed. One session = one tenant, matching gateway-api's own model (one key, one tenant).

### DASH-105 — Won't: admin panel / tenant provisioning UI [Won't]
Not proposed. gateway-api's GW-005 provisioning is explicitly an operator/test-fixture CLI, not a public sign-up flow — no endpoint exists for this UI to call.

### DASH-106 — Won't: `libs/sdk` usage or wrapping [Won't]
Not proposed. dashboard-web calls gateway-api directly, a peer consumer of libs/sdk's future users, not a wrapper (decision 2).

### DASH-107 — Won't: JWT-based session auth (gateway-api's GW-011) [Won't, this backlog]
Not proposed. GW-011 is Should/not built (decision 3); DASH-002 uses GW-006's API-key mechanism instead. Revisiting this is gateway-api's own backlog's follow-up, not authored here.

