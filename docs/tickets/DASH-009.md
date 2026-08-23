# DASH-009 — Selenium browser-level E2E test suite for the core PoC loop

**Status: done**

## Analysis
Story: DASH-009 (Should), depends on DASH-002, DASH-004, DASH-006, and `DASH-005`'s disclosed
`DASH-005-GAP` fallback (used since `DASH-005` itself is deferred out of this sprint — see
`docs/sprints/sprint-11.md`'s scheduling decision). Backlog acceptance criteria: a real Selenium
WebDriver suite in `services/dashboard-web/tests/e2e/`, run against a real running `dashboard-web`
instance (not in-process `TestClient`) pointed at a test/fixture gateway-api; covers at minimum three
flows (successful login; submit-a-run end-to-end; view a completed run) each with one negative/edge
case already specified elsewhere in the backlog; documented/run separately from the default `uv run
pytest` unit loop (`pytest -m e2e`, marker already declared in DASH-001's `pyproject.toml`); README
documents driver/browser prerequisite and how the fixture gateway-api is stood up.

**The `DASH-005-GAP` fallback, used exactly as disclosed, not reinterpreted**: flow 3 ("view a
completed run") does **not** navigate via a runs-list page (`DASH-005` does not exist this sprint) —
it uses the run id returned by flow 2's own submit-and-redirect (DASH-006 -> DASH-004), i.e. flow 3 is
effectively "navigate directly to the run detail URL for the id flow 2 just created," not a separate
lookup mechanism. **Do not build any client-side runs-list substitute (local record-keeping, DOM
scraping of prior pages, a hidden index page) to make this flow easier** — the backlog's own `DASH-005`
acceptance criteria explicitly forbid that, and sprint-11.md's handoff note repeats the warning
directly. If a genuinely pre-existing completed run (not one this suite itself just created) is
needed for the "completed" status specifically (flow 2's own submitted run may still be `"running"`
by the time flow 3 checks it, depending on how long `validation-service`'s synchronous execution
takes for the fixture dataset), the suite may submit a second, deliberately small/fast dataset via
DASH-006 ahead of flow 3 and poll its detail page until `status` is no longer `"running"` (bounded
retry, not an indefinite wait) — still using DASH-006's own redirect id, never a list page.

## Design
Pattern: none from implementation-plan.md section 7 — this is a testing/tooling story, not a new
route/feature. File: `services/dashboard-web/tests/e2e/test_core_loop.py` (new), plus a small fixture
helper `services/dashboard-web/tests/e2e/conftest.py` (new) providing: a `live_server` fixture that
starts a real `uvicorn` process serving `dashboard-web` on a test port (subprocess, not
`TestClient` — the backlog is explicit "not in-process TestClient"), and a `driver` fixture
(Selenium WebDriver — Chrome headless by default, configurable via an env var for a different
browser/driver if the implementer's local setup needs one, documented in the README either way).

**Fixture gateway-api, implementer's choice, documented**: the two options considered are (a) a
minimal stub FastAPI app implementing just enough of `gateway-api`'s real contract (`/health`, `POST
/runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`) to drive the three flows, run as its own subprocess
alongside `dashboard-web`'s `live_server`, or (b) the real `gateway-api` + `validation-service` (+
Postgres/Redis via `infra/docker-compose.yml`) seeded with a known test tenant/key via `gateway-api`'s
own `scripts/provision_tenant.py` (`GW-005`). **Recommendation, not a binding instruction — the dev
agent picks and documents whichever it actually builds**: option (a) is lower-setup-cost and doesn't
require Docker Compose to be running for this suite to pass, matching the spirit of the rest of this
sprint's mocked-gateway-api unit tests; option (b) is a stronger end-to-end proof but couples this
suite's pass/fail to infra being up. Either is acceptable per the backlog's own "implementer's choice"
wording — document which was chosen and why in this ticket's Outcome and in the README.

**Negative/edge case per flow, one already-specified backlog behavior, not invented here**: flow 1
(login) — an invalid/wrong API key redirects back to `/login` with an error, no session cookie set
(DASH-002's own AC). Flow 2 (submit) — an invalid submission (e.g. a non-numeric `horizon`) is
rejected with the form redisplayed and an error shown, not silently accepted (DASH-006's own AC).
Flow 3 (view) — navigating to a syntactically valid but nonexistent run id renders the not-found page
(DASH-004's own AC).

DRY check: grepped `services/dashboard-web/tests/` (DASH-002/003/004/006/007/008's own unit test
files, all using `httpx.MockTransport`/in-process `TestClient` — none of that fixture machinery is
reusable for a real-subprocess Selenium suite, confirmed directly rather than assumed) before writing
new fixtures — no existing live-server/WebDriver fixture exists anywhere in this repo to reuse (this
is the first Selenium suite in the platform).

## Implementation acceptance criteria
- [x] `tests/e2e/test_core_loop.py` + `tests/e2e/conftest.py` exist, run against a real subprocess
  `dashboard-web` instance (not `TestClient`) and a real running browser via Selenium WebDriver.
- [x] Flow 1 (login): valid key logs in (session cookie present, lands on an authenticated page);
  invalid key redirects to `/login` with an error, no cookie set.
- [x] Flow 2 (submit): fills and submits DASH-006's form with a valid payload, ends up redirected to
  the new run's detail page; a second case submits an invalid payload and confirms the form
  redisplays with an error, no redirect.
- [x] Flow 3 (view a completed run): navigates to the id from flow 2's own redirect, asserts the
  rendered status + per-split metrics table are present in the DOM; a second case navigates to a
  syntactically valid but nonexistent run id and confirms the not-found page renders.
- [x] No runs-list page, client-side run index, or DOM-scraping substitute is introduced anywhere in
  this ticket's diff — confirmed via `grep` across `src/app/routers/*.py` (only `/login`, `/logout`,
  `/runs/new` GET+POST, `/runs/{run_id}` exist, matching DASH-002/006/004 exactly, nothing added) and
  a re-read of `tests/e2e/test_core_loop.py`/`conftest.py`.

## Test acceptance criteria
- [x] Suite is collected only under the `e2e` marker: `uv run pytest -q` (default, no `-m`) collects
  and passes 42 tests, deselecting all 5 `tests/e2e/` items; `uv run pytest -m e2e -q` collects and
  runs exactly those 5, 0 from the unit suites — confirmed by direct count, not assumed.
- [x] `uv run pytest -m e2e` passes against a real running `dashboard-web` subprocess and the stub
  `gateway-api` fixture (Design section's option (a), as built): **5 passed in 12.68s** (final run,
  after the fix below). Selenium Manager auto-resolved a local Chrome + matching chromedriver install
  with no manual setup required in this environment.

## Review acceptance criteria
- Tech Lead personally ran `uv run pytest -m e2e -q` (and the full suite together, `uv run pytest -q
  -m ""`) against a real running instance — not merely trusted from a dev agent's report. Confirmed
  all three flows plus their negative/edge cases pass, and confirmed via `grep` across
  `src/app/routers/` that no runs-list substitute exists anywhere.
- **One real bug found and fixed during this personal verification, disclosed here rather than
  silently patched**: the first live run showed 4/5 passing, 1 failing —
  `test_submit_run_invalid_payload_redisplays_form` timed out waiting for the `.error` element. Root
  cause: the test submits `horizon=0` against `run_new.html`'s `<input type="number" id="horizon"
  min="1" required>` — the browser's own native HTML5 validation (DASH-006's correct client-side
  mirror of the server constraint, not an app bug) blocks the submit before it ever reaches the
  server, so the page never navigates and no server-rendered error ever appears; the Selenium wait
  correctly timed out because nothing happened. This is a test-authoring gap, not an application
  defect — the app's client-side mirroring is working exactly as DASH-006 specifies. Fixed by calling
  `driver.execute_script("arguments[0].noValidate = true;", submit_form)` immediately before the
  click, so the deliberately-invalid submit reaches the server and the test actually exercises the
  server-side validation path it exists to prove (the same round trip a non-browser caller or a
  client with JS/HTML5-validation disabled would take). Re-run after the fix: all 5 e2e tests pass.
  No application code was touched by this fix — only `tests/e2e/test_core_loop.py`.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md`'s Tests section documents the WebDriver prerequisite (Chrome,
  auto-resolved by Selenium's built-in Selenium Manager — no manual chromedriver install needed in
  this environment; documented as the expected default, with a note that an explicit driver path can
  be set via Selenium's own standard env vars if a different browser/driver is needed), how the stub
  `gateway-api` fixture is stood up (automatic, `tests/e2e/conftest.py`'s `stub_gateway_api` session
  fixture, no Docker Compose required), and the exact command (`uv run pytest -m e2e`), distinguished
  from the default `uv run pytest` unit loop.

## Outcome

Delegated to a dev subagent, which built `tests/e2e/test_core_loop.py`, `tests/e2e/conftest.py`, and
`tests/e2e/stub_gateway_api.py` (Design section's option (a): a minimal stub FastAPI app implementing
just enough of `gateway-api`'s contract to drive the three flows, run as its own session-scoped
subprocess alongside a real `dashboard-web` subprocess — no Docker Compose dependency for this suite).

Personally verified by the Tech Lead end-to-end, not trusted from the dev agent's own report:
- `uv run pytest -q` (default unit loop): **42 passed**, 5 deselected (the e2e suite correctly
  excluded by default via the `e2e` marker declared in DASH-001's `pyproject.toml`).
- `uv run pytest -m e2e -q`: first run **4 passed, 1 failed** — a real, disclosed bug found in the
  test itself (not the app), root-caused and fixed as described in the Review acceptance criteria
  section above. Re-run after the fix: **5 passed**, 0 failed, 12.68s.
- Combined full suite, `uv run pytest -q -m ""`: **47 passed**, 0 failed.
- `git status` scoped to `src/app/routers/` and `src/app/templates/` confirmed zero changes from this
  ticket (only `tests/e2e/` and the one test-file fix above) — no runs-list substitute, no new route,
  no template change introduced.
- Environment note: this repo directory sits inside a OneDrive-synced folder
  (`C:\Users\vasil\Documents`), which caused intermittent file-write/delete failures during this
  ticket's verification (`ENOENT` on direct edits, `Acesso negado` on `.venv` creation) unrelated to
  this ticket's own code. Worked around by building the test venv outside the synced tree
  (`UV_PROJECT_ENVIRONMENT` pointed at a scratch directory) — flagged here since it will recur for any
  future work in this repo directory until the sync exclusion is addressed at the OS level.

**Sprint 15 update (`DASH-009-02`)**: flow 3's redirect-id-only navigation described above is now
historical. Once `DASH-005-01` built the real `GET /runs` list page (Sprint 15, closing the
`DASH-005-GAP` fallback this ticket originally relied on), `DASH-009-02` rewrote flow 3's navigation
step in `test_submit_run_valid_payload_redirects_and_shows_completed_results`: the test now navigates
to `GET /runs` and clicks the `a[href='/runs/{run_id}']` link for the run flow 2's own redirect just
created, then proceeds through the same status-polling loop and DOM assertions unchanged. The run id
itself is still obtained from flow 2's redirect — only how the test reaches the detail page changed.
`tests/e2e/stub_gateway_api.py` gained a matching `GET /runs` handler (returning the same
`items`/`limit`/`offset`/`total` envelope shape as the real `gateway-api`/`validation-service`
contract, items shaped like `RunSummaryResponse`, sourced from the stub's own `_runs` dict,
most-recent-first) so the fixture gateway-api actually supports the real list page's own downstream
call — necessary plumbing, not a new capability. No new page/route/template was added to
`dashboard-web` itself; `git status` scoped to `src/app/routers/` and `src/app/templates/` confirmed
zero changes. Final counts: `uv run pytest -q` — **50 passed**, 5 deselected (unit-test count is 50,
not the original ticket's 42, because `DASH-005-01`'s own route tests were merged earlier this sprint
— unrelated to this ticket, confirmed unchanged by this ticket's diff); `uv run pytest -m e2e -q` —
**5 passed**, 0 failed.
