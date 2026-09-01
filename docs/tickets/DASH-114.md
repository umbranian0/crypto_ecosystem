# DASH-114 — Monitoring page: expose first-crawl `since` override on the crawl-trigger form

**Module**: `services/dashboard-web`
**Story source**: direct requester ask (2026-09-01), same follow-up as `INGEST-013`/`GW-023`. Explicitly
flagged by the requester as a "your call whether same ticket or a clean split; sequence the API ticket
first" decision — Tech Lead decision: clean split (own ticket), sequenced after `GW-023` lands, since
this ticket's only new capability (an HTML date input on an existing form) has no reason to block or be
blocked by the backend plumbing, and keeping it separate avoids widening `INGEST-013`/`GW-023`'s own
file scope into a third module.
**Depends on**: `GW-023` (this sprint, must land first — this ticket's form posts to the gateway-api
route `GW-023` extends).
**Status**: done

## Analysis

`DASH-110` (Sprint 18) already added a per-source "run this tenant's crawl now" button/form
(`operator.py`'s `trigger_crawl`, `monitoring.html`'s crawl-status panel) with no input fields — a bare
submit button. This ticket adds one optional date input to that same form so a tenant can specify
`INGEST-013`'s new first-crawl `since` override from the UI, without duplicating any of
`INGEST-013`'s validation logic here (the existing "no new error-handling pattern," `_render_error_for_
status` reuse, already covers a downstream `422` from a bad date).

## Design

**Pattern**: none newly invoked — reuses the exact HTMX inline-fragment-swap mechanism `DASH-110`
already established for this same form (no new client-side mechanism).

**DRY check (grepped first)**: `trigger_report_generation` in the same file already has the exact
precedent needed — a `Form(...)`-declared string field (`run_id: str = Form("")`) read from an HTML
`<form>` POST and forwarded as part of an outbound `httpx` call. Reuse this identical convention for
`since` rather than inventing a query-param-on-a-GET-form or a hand-rolled JS `fetch()` call. `_call_
downstream`/`_render_error_for_status` (already imported from `runs.py` in this file) are reused
unmodified — no second failure-handling shape.

**Files touched** (two files, one module):
- `src/app/templates/monitoring.html`: inside the existing per-source crawl-trigger `<form
  hx-post="/monitoring/connectors/{{ entry.source }}/run" ...>` (the one `DASH-110` already renders per
  row), add one `<input type="date" name="since">` (optional, no `required` attribute — an empty
  submission must behave identically to today's no-field form) with a short label/tooltip stating it
  only takes effect on that tenant's first-ever crawl of this source, matching the sprint-18 UAT
  addendum's own precedent of a plain-language caveat next to a field with a non-obvious effect (the
  raw-levels-vs-returns tooltip on `run_new.html`).
- `src/app/routers/operator.py`'s `trigger_crawl` handler:
  - Add `since: str = Form("")` parameter.
  - Build `params = {"since": since} if since.strip() else {}` (mirrors `GW-023`'s own "omit rather
    than send empty string" convention, kept consistent end-to-end) and pass it to
    `_call_downstream(client.post, f"/ingestion/connectors/{source}/run", params=params,
    headers=headers)`.
  - No new validation in this handler — a downstream non-`202` (including `INGEST-013`'s `422`s,
    forwarded unmodified through `GW-023`) already renders via the existing `_render_error_for_status`
    call, unchanged.

## Implementation acceptance criteria

- The per-source crawl-trigger form in `monitoring.html` has one new optional date input, clearly
  labeled with the "first crawl only" caveat.
- Submitting the form with the date field blank behaves identically to before this ticket (byte-for-
  byte same downstream request — no `since` param sent).
- Submitting the form with a date value forwards it as `since` on the outbound `POST /ingestion/
  connectors/{source}/run` call.
- A downstream `422` (bad date, future date, before-earliest-available) renders the existing generic
  `_render_error_for_status` fragment — no new error-message shape introduced.
- No change to `trigger_report_generation` or any other route in this file.

## Test acceptance criteria

Extend `tests/test_monitoring_triggers.py` (existing pattern: fakes `gateway-api` via
`_call_downstream`'s `httpx.Client` dependency, matching this file's own established mocking approach —
read the existing file first to match its fixture shape exactly, do not invent a second one):
- Submitting `trigger_crawl` with a `since` form value results in the faked downstream request's query
  params containing `since` with that exact value.
- Submitting `trigger_crawl` with no `since` value (or blank string) results in the faked downstream
  request carrying no `since` param at all.
- A faked downstream `422` response renders the existing generic error fragment (reuse whatever
  assertion the existing transport-failure/non-202 test in this file already makes, applied to this new
  case).
- No regression to any existing test in this file.

## Review acceptance criteria (Tech Lead verifies personally)

- Read the actual diff: confirm `monitoring.html`'s new input is inside the existing per-source form
  (not a second, parallel form), confirm blank-submission produces an unmodified request compared to
  pre-ticket behavior, confirm zero new error-handling code path was added to `operator.py`.
- Run `services/dashboard-web`'s full test suite directly and confirm zero regressions plus new tests
  passing.
- Manually trace one full round trip in the diff (template → handler → gateway-api call) to confirm the
  form field name (`since`), the handler's `Form(...)` parameter name, and the outbound `params` key
  all match exactly — a name mismatch here would silently no-op the whole feature without any test
  necessarily catching it if the test only checks the fake's received params by key that happens to
  coincidentally match; explicit manual trace is the Tech Lead's own extra check beyond the test suite.

## Documentation acceptance criteria

- `services/dashboard-web/README.md`'s `DASH-110` section gains a short addition documenting the new
  optional `since` field on the crawl-trigger form and that it only affects a tenant's first-ever crawl
  of a source (linking to `INGEST-013`/`GW-023` for the underlying semantics, not re-documenting them).
- Ticket status updated to `done` once verified; `docs/tickets/README.md`'s Sprint 19 section updated.
