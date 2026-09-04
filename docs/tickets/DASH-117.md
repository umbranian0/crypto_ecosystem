# DASH-117 — Restart button once a crawl is stopped/completed/failed

**Module**: `services/dashboard-web` (templates + `src/app/routers/operator.py` test coverage only —
no new route). **Depends on**: none beyond already-shipped `DASH-110`/`INGEST-021` (for the `cancelled`
status value to exist at all). **Sequenced first** in Sprint 24 per `docs/sprints/sprint-24.md`: cheapest,
lowest-risk story, no new backend/proxy code, banks an early win before `DASH-116`/`DASH-118` touch the
same file.

## Analysis

Covers `docs/product/backlog-crawl-lifecycle-control.md`'s `DASH-117` story: a tenant whose crawl has
stopped (`completed`/`failed`/`cancelled`) needs a "restart" control in the same row, understood as
"just a normal new crawl trigger" (backlog's decision #1) — never a second "resume" code path. The
existing `POST /monitoring/connectors/{source}/run` route (`trigger_crawl`, `operator.py`, `DASH-110`)
already resolves the watermark via `ingestion-service`'s existing `latest_watermark_from_db`-first
order — no backend change is needed for the *continuation* behavior itself, only for exposing/labeling
the button correctly on the dashboard.

Binding constraint from `docs/sprints/sprint-24.md`: stop button (`DASH-116`, next ticket) and restart
button must be **mutually exclusive on the same row** — a row never shows both. Since `DASH-116` hasn't
landed yet when this ticket executes, this ticket's own scope is: gate the *existing* trigger form to
only render for `completed`/`failed`/`cancelled` rows (it currently renders unconditionally for every
row, regardless of status) and relabel it as a restart action with checkpoint-continuation copy. This
by itself already achieves "never both on the same row" for this ticket's own diff, since no stop
button exists yet; `DASH-116` (which runs immediately after, same file) is responsible for adding the
stop button for the complementary `queued`/`running`/`cancelling` states.

## Design

**Pattern**: none from implementation-plan.md section 7 applies — this is a template/route gating
change, not a new abstraction boundary. The one pattern this service already uses (Dependency
Injection, FastAPI `Depends()`) is untouched by this ticket.

**Files touched** (scoped to `services/dashboard-web` only, per implementation-plan.md section 3's
module-boundary rule):
- `services/dashboard-web/src/app/templates/_crawl_status_panel.html` — gate the existing per-row
  trigger `<form>` behind `{% if entry.status in ("completed", "failed", "cancelled") %}`, and change
  its button copy.
- `services/dashboard-web/tests/test_monitoring_triggers.py` — extend/adjust the existing
  `test_monitoring_page_renders_trigger_forms_for_logged_in_tenant` test (currently asserts the form is
  present for a `"completed"` row — still true) and add new cases for `queued`/`running` rows (form
  absent this ticket, since the stop button doesn't exist until `DASH-116`).
- `services/dashboard-web/README.md` — update the "Trigger actions on /monitoring (DASH-110)" section
  (or a new subsection) noting the trigger form is now restart-gated and worded as a restart action.

**DRY check note** (grepped `services/dashboard-web/src/app/templates/_crawl_status_panel.html` and
`operator.py` before writing this ticket): the existing `POST /monitoring/connectors/{source}/run`
route (`trigger_crawl`) and its `_crawl_trigger_result.html` fragment are reused completely unmodified
— this ticket adds zero backend code. The `{% for entry in crawl_statuses %}` loop already in
`_crawl_status_panel.html` is extended with an `{% if %}` guard, not duplicated into a second loop or a
second template file (matches `_crawl_status_panel.html`'s own extraction precedent, `DASH-115`'s DRY
note in its docstring).

**Status: Done (Sprint 24).** 118 unit tests passing (up from 113), plus the same 5 e2e (unaffected).
`operator.py`/`_crawl_trigger_result.html` confirmed byte-for-byte unchanged via `git diff --stat`.

## Implementation acceptance criteria

- [x] `_crawl_status_panel.html`'s per-source row renders the existing trigger `<form>`
      (`hx-post="/monitoring/connectors/{{ entry.source }}/run"`) **only** when `entry.status` is one of
      `completed`/`failed`/`cancelled`. For `queued`/`running`/`cancelling` rows, this ticket renders no
      trigger form at all (an intentional, disclosed gap this ticket alone leaves — `DASH-116`, run
      immediately next against the same file, is what adds the stop button for those three statuses; this
      ticket does not invent a placeholder for them).
- [x] The button's label changes from "Run this tenant's {{ entry.source }} crawl now" to explicit
      restart-from-checkpoint copy, e.g. "Restart {{ entry.source }} crawl (continues from last saved
      checkpoint)" — plain-language honesty requirement (sprint-24.md's own hard acceptance criterion):
      never an unqualified "Restart" that could imply starting over.
- [x] The `since` date input and its "only takes effect on this tenant's first-ever crawl" helper text
      are unchanged — a restart of an already-once-crawled source ignores `since` exactly as today,
      matching `run_connector`'s/`INGEST-013`'s existing semantics (no behavior change, only relabeling).
- [x] No new backend route, no new gateway-api proxy call, no new template file — `trigger_crawl` in
      `operator.py` and `_crawl_trigger_result.html` are byte-for-byte unchanged (confirm via `git diff`
      showing zero changes to `operator.py` and `_crawl_trigger_result.html` for this ticket).

## Test acceptance criteria

- [x] A unit test proves the restart form/button is present for a `"completed"` row, a `"failed"` row,
      and a `"cancelled"` row.
- [x] A unit test proves the restart form/button is **absent** for a `"queued"` row and a `"running"`
      row (the disclosed gap above — no button of any kind for those statuses until `DASH-116`).
- [x] A unit test proves the rendered button/label text contains checkpoint-continuation language (e.g.
      asserts the phrase "continues from" or equivalent appears), not just an unqualified "Restart".
- [x] Existing `test_trigger_crawl_*` tests (the route-handler tests, not the template-gating tests)
      continue to pass unmodified — this ticket does not touch `trigger_crawl`'s own handler behavior,
      only what template markup decides to render the form at all.
- [x] Full `services/dashboard-web` suite re-run with zero regressions from the pre-ticket baseline count
      (118 passed, 5 deselected e2e; baseline was 113).

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff: confirmed `git diff --stat` for `operator.py`/`_crawl_trigger_result.html`
      is empty — zero line changes.
- [x] Confirmed the `{% if %}` guard is exactly `entry.status in ("completed", "failed", "cancelled")` —
      no accidental inclusion of `queued`/`running`/`cancelling`.
- [x] Confirmed the button copy literally reads "Restart {{ entry.source }} crawl (continues from last
      saved checkpoint)" — read the rendered template source directly, not just a test's substring check.
- [x] Confirmed no positioning-banned words in the new template markup (manual read of the full file).
- [x] Ran the full suite directly (Tech Lead's own run, not the dev agent's report):
      `122 passed, 5 deselected, 0 failed` (dashboard-web, `-m "not e2e"` default).

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md`'s "Trigger actions on /monitoring (DASH-110)" section (or a new
      "Restart action (DASH-117)" subsection immediately after it) documents: the trigger form is now
      gated to `completed`/`failed`/`cancelled` rows only, is labeled as a restart-from-checkpoint action,
      and that `DASH-116` (next ticket) is what adds the complementary stop control for the other three
      statuses — so a reader of this section alone isn't left thinking `queued`/`running`/`cancelling`
      rows permanently have no action at all.
