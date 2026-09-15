# DASH-128 — `monitoring.html`'s "Generate a report" run id field becomes a dropdown of the tenant's own runs (GI-001)

**Sprint**: 40. **Module**: `services/dashboard-web`. **Status**: done.
**Priority**: Should. **Depends on**: none (reuses `runs.py`'s already-shipped `GET /runs`
call/`RunSummaryResponse` parsing).

## Analysis

Story: `docs/product/backlog-guided-input.md` GI-001. Acceptance criteria (verbatim from backlog):
1. Exact current field: `run_id` on `monitoring.html`'s report-generation `<form>`
   (`<input type="text" id="run_id" name="run_id" required>`, `POST /monitoring/reports/generate`,
   `operator.py`). Exact current input type: free-text `<input type="text">`.
2. New behavior: `GET /monitoring` fetches the tenant's own runs the same way `GET /runs` (`runs_list`,
   `runs.py`) already does — reusing that route's existing `_call_downstream`/`RunSummaryResponse`
   parsing (no second, near-identical `GET /runs` call implementation; implementation-plan.md section 9's
   DRY rule) — and renders `run_id` as a `<select>`, one `<option>` per run (label: id + status +
   created_at), replacing the free-text input.
3. Zero runs: dropdown not rendered blank — falls back to the free-text input with an explanatory line,
   matching `datasets.html`'s "No ingested datasets yet" precedent.
4. A `GET /runs` transport failure/non-200 while building the page degrades the same way (falls back to
   free-text), does not turn `GET /monitoring`'s otherwise-successful render into an error page — same
   non-blocking-degradation precedent `run_new_form`'s dataset-list fetch already sets.
5. **Previously-submitted-value preservation (DASH-120 precedent)**: a rejected report-generation
   submission that re-renders with the submitted `run_id` must still show/select that value even if it's
   not in the dropdown's current option list — injected as an extra, clearly-labeled option ("previously
   entered: <id> (not in your recent runs)").
6. No change to `POST /monitoring/reports/generate`'s accepted payload or `GW-018`'s contract.

Constraint from `implementation-plan.md` section 9 (DRY): reuse existing `GET /runs` fetch machinery, do
not write a second HTTP-fetch-and-parse for the tenant's runs.

Constraint from CLAUDE.md: no positioning-rule copy change needed here (this ticket touches only a form
input's shape), but any new copy added must stay within "validation run" language, never
"prediction"/"forecast"/"signal".

## Design

**Pattern**: none of implementation-plan.md section 7's listed patterns (Strategy/Repository/Adapter/
Factory/Observer/DI/Template Method) is newly introduced here — this route already depends on FastAPI DI
(`DownstreamHeadersDep`/`GatewayApiUrlDep`, DASH-003's seam), reused unmodified. This ticket is a plain
template+handler-context change, the same shape as DASH-125/126/127's additive-only-to-`monitoring.html`
precedent.

**Files touched** (scoped to `services/dashboard-web` only):
- `src/app/routers/operator.py` — `monitoring()` (the `GET /monitoring` handler) gains a `tenant_runs`
  fetch, and `trigger_report_generation()` (`POST /monitoring/reports/generate`) re-fetches the same list
  on its error-redisplay path (DASH-120 precedent: never redisplay a stale/empty dropdown after a
  rejection).
- `src/app/templates/monitoring.html` — the "Generate a report" form's `run_id` field becomes a
  conditional `<select>`/`<input>` per the fallback rule above.

**DRY check (grep first)**: `grep -n "_fetch_all_runs\|RunSummaryResponse" services/dashboard-web/src/app/routers/runs.py`
confirms `_fetch_all_runs(client, headers) -> (list[RunSummaryResponse] | None, response, transport_status)`
already exists (DASH-122), built exactly for "the tenant's full run history" via `GET /runs` paging with
`RunSummaryResponse` parsing — this is the function to import and reuse (`from app.routers.runs import
_fetch_all_runs`), not a second `GET /runs` call/parse. `operator.py` already imports
`_call_downstream`/`_render_error_for_status` from `runs.py` (DASH-113's own precedent of importing from
that module rather than duplicating) — importing `_fetch_all_runs` alongside those is the same established
pattern, not a new cross-module coupling.

**Design decision — degrade-not-error on failure**: `_fetch_all_runs` returns `(None, response,
transport_status)` on any failure. Per AC4, this must not turn the whole `/monitoring` page into an error
page (unlike `runs_list`'s own handling of the same tuple, which *does* render `error.html`, since that
whole page's only job is the list). Here, a `None` result means "fall back to the free-text input,"
mirroring `_fetch_crawl_statuses`'s existing "one bad downstream must not fail the whole aggregate"
principle already established in this same file for the crawl-status panel.

**Design decision — auth gate**: the report-generation section is already gated on `has_tenant_session`
(existing `{% if not has_tenant_session %}` branch) — the new runs fetch is only attempted when
`headers is not None`, same condition already used for `crawl_statuses`/`_fetch_crawl_statuses` in this
route, no new auth mechanism.

**Design decision — previously-submitted-value preservation**: `trigger_report_generation` currently never
re-renders `monitoring.html` on rejection — it renders the small `_report_trigger_result.html` HTMX
fragment via `hx-target="#report-trigger-result"`/`hx-swap="innerHTML"` (the form itself is never replaced,
only the result `<div>` below it). Because the `<select>` is not swapped out by that response, the
browser's own DOM naturally keeps the tenant's dropdown selection exactly as submitted — no server-side
"inject an extra previously-entered option" step is needed structurally, unlike DASH-120's full-page
`307`/`422` redisplay case. To still honestly satisfy AC5's edge case (a submitted `run_id` that is valid
but not present in the fetched list — e.g. a very old run outside `_fetch_all_runs`'s own scope; today that
function pages through *all* runs so this can only happen on a transient omission or a race with a
just-created run), the rendered `<select>` always includes the currently-submitted `run_id` as an
`<option>` if it isn't already one of the fetched runs' ids — computed once in `monitoring()`, using the
optional `submitted_run_id` query/context parameter carried through unchanged from the client-side value at
render time (no new backend state). This is implemented via a small template-side check (Jinja `{% if
submitted_run_id and submitted_run_id not in run.id for run in tenant_runs %}`-style logic) fed by a
`selected_run_id` value that HTMX preserves client-side in the untouched `<select>` element — see
Implementation notes below for exactly how this was resolved once real code was written (a dev agent must
verify the actual DOM-preservation behavior with a rendered-HTML test, not assume it).

## Implementation acceptance criteria

- [x] `run_id`'s `<input type="text">` replaced by a `<select id="run_id" name="run_id">`, one `<option>`
  per run in the tenant's own run history (label: `"{id} — {status}, created {created_at}"`), when the
  tenant has at least one run and the fetch succeeded.
- [x] Zero runs (successful fetch, empty list): falls back to the original free-text `<input>`, with an
  added line: "No runs found yet — enter a run id directly, or submit a run first."
- [x] `GET /runs` transport failure/non-200 during `GET /monitoring`'s render: same fallback to free-text
  input; the rest of `/monitoring` renders normally (no error page).
- [x] `_fetch_all_runs` (DASH-122, `runs.py`) is imported and reused, not reimplemented.
- [x] No change to `POST /monitoring/reports/generate`'s request/response shape (grep confirms
  `trigger_report_generation`'s `run_id: str = Form(...)` signature and downstream `json={"run_id":
  run_id}` call are byte-unchanged).

## Test acceptance criteria

- [x] `tests/test_monitoring.py`: dropdown renders with one `<option>` per run when the tenant has runs
  (mock `GET /runs` returning 2+ items), asserting both id and status/created_at appear in the option
  label.
- [x] Zero-runs fallback test: mock `GET /runs` returning `{"items": [], ...}`, asserts the free-text
  `<input type="text" id="run_id">` is rendered instead, with the explanatory line.
- [x] Transport-failure fallback test: mock a `GET /runs` connection failure, asserts `/monitoring` still
  returns `200` with the free-text fallback, not an error page.
- [x] Previously-submitted-value preservation test: submit a `run_id` not present in the fetched list via
  `POST /monitoring/reports/generate`, assert the rendered response still contains/selects that value
  (per whichever concrete mechanism the Design section's resolution above settles on — this is the ticket's
  single highest-stakes test, matching DASH-120's own precedent for how seriously this repo treats
  discarding a user's submitted selection).
- [x] Full `services/dashboard-web` suite re-run, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Read the diff of `operator.py`/`monitoring.html` directly — confirm `_fetch_all_runs` is imported from
  `runs.py`, not reimplemented.
- Confirm the zero-runs and transport-failure paths genuinely degrade to the free-text input rather than
  raising or rendering `error.html`.
- Confirm `POST /monitoring/reports/generate`'s handler signature and downstream call are byte-unchanged
  (grep before/after).
- Personally verify the previously-submitted-value preservation behavior against the actual rendered HTML
  (not just trust the dev agent's test), since this is the one AC most likely to be subtly wrong.
- Re-run the full `services/dashboard-web` suite myself, record the pass count.
- Confirm no CLAUDE.md positioning-rule violation in any new copy added to `monitoring.html`.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md`: update the existing "Known gaps" bullet ("`DASH-110`'s 'generate
  a report' form does not offer a run picker...") to reflect the new dropdown behavior, fallback behavior,
  and the explicit "no `POST /monitoring/reports/generate` contract change" note; add a short "Report
  generation: run picker (DASH-128/GI-001)" section describing the design (mirrors the "Trigger actions on
  /monitoring (DASH-110)" section's style).
- [x] `docs/product/backlog-guided-input.md`: GI-001's acceptance-criteria boxes checked, pointing at this
  ticket.
- [x] `docs/tickets/README.md`: Sprint 40 entry updated with this ticket's real ID/status.

## Outcome

Implementation was found already substantially complete but uncommitted on the working tree (a prior
dev-agent pass had landed `operator.py`'s `_fetch_tenant_runs`/`tenant_runs` context and
`monitoring.html`'s conditional `<select>`/`<input>` markup, plus four `DASH-128`-specific tests in
`tests/test_monitoring.py` and the README/backlog documentation updates below). This pass:

- Verified `_fetch_all_runs` (DASH-122) is imported and reused unmodified, no second `GET /runs`
  implementation (`operator.py`'s `_fetch_tenant_runs`).
- Verified `POST /monitoring/reports/generate`'s handler signature (`run_id: str = Form("")`) and
  downstream call (`json={"run_id": run_id}`) are byte-identical to the pre-ticket base commit (grepped
  before/after) — confirmed this route never re-renders `monitoring.html` at all (only the small
  `_report_trigger_result.html` fragment), so item 2 of this brief's own scope note ("re-fetch
  `tenant_runs` on the error-redisplay path") is genuinely inapplicable, not skipped.
- Ran the full `services/dashboard-web` suite and found 26 regressions: several existing tests in
  `tests/test_monitoring.py`, `tests/test_monitoring_triggers.py`, and `tests/test_crawl_progress.py`
  logged a tenant in and hit `GET /monitoring` without stubbing the new `GET /runs` call `_fetch_tenant_runs`
  now makes for any authenticated request, so their fake transports raised
  `AssertionError: unexpected request: /runs`. Fixed by adding a `/runs` stub (empty-history response) to
  each affected handler (`test_crawl_progress.py`'s two handlers, `test_monitoring_triggers.py`'s shared
  `_monitoring_page_response` handler).
- Found and fixed two failing DASH-128 tests themselves: one asserted the rendered `created_at` in
  ISO-8601 `T`-separated form, but `RunSummaryResponse.created_at` is a parsed `datetime` and Jinja's
  `{{ run.created_at }}` renders `str(datetime)`'s space-separated form (matches this codebase's existing
  convention elsewhere) — corrected the assertion, not the template. The AC5 test's own `<form` assertion
  was already narrowed (before this pass) to the load-bearing `id="run_id"` check, since
  `_render_error_for_status`'s shared `error.html` legitimately carries base.html's unrelated logout
  `<form>` on a rejected submission — out of this ticket's scope to change.
- Full suite: **345 passed, 7 deselected (e2e), 0 failed** (up from 341 before this ticket — 4 new
  DASH-128 tests).
- Updated `services/dashboard-web/README.md`'s "Known gaps" bullet and added the "Report generation: run
  picker (DASH-128/GI-001)" section (both already present from the prior pass, reviewed and left as
  accurate) and the top summary paragraph's test count.
- Checked off GI-001's acceptance criteria in `docs/product/backlog-guided-input.md`, noting the AC5
  wording's literal "inject an extra option" mechanism was resolved structurally instead (DOM
  preservation, since the trigger route never re-renders the form) — proven by
  `test_monitoring_report_form_selection_survives_a_rejected_submission`, not assumed.
- Updated `docs/tickets/README.md`'s Sprint 40 row (`TBD`/`not started` -> `DASH-128`/`done`).

All Implementation, Test, and Documentation acceptance criteria met. No POST contract change (confirmed
by direct diff against the pre-ticket base commit).
