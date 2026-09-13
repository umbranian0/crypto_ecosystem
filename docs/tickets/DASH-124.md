# DASH-124 — Confirmed small bug: `/monitoring`'s login-prompt vs. transient-fetch-failure conflation

**Status: Done.** `operator.py::monitoring` now passes `has_tenant_session` (`headers is not None`);
`monitoring.html`'s crawl-status panel and report-form login-prompt branches gate on
`{% if not has_tenant_session %}` with a new `{% elif crawl_statuses is none %}` branch showing the
generic "results currently unavailable" downstream-failure copy. AC1/AC2/AC3 met (see Test acceptance
criteria below). Full `services/dashboard-web` suite: 279 passed, 7 deselected (e2e), 0 regressions.

**Module**: `services/dashboard-web` only.
**Depends on**: none. Disjoint from every Track A file (`run_new.html`, `run_detail.html`, chart partials) —
can run fully in parallel with Track A and with `GW-029`.

## Analysis

Covers `docs/product/backlog-uat-findings.md`'s "Confirmed small bug" section, live-traced: `monitoring.html`
gates both the crawl-status panel and the report-generation form on `{% if crawl_statuses is none %}`, but
`crawl_statuses` is `None` in two structurally different cases (`operator.py::monitoring`):
1. Anonymous visitor — `headers` (`OptionalDownstreamHeadersDep`) is `None`, so `_fetch_crawl_statuses` is
   never called at all (`crawl_statuses = ... if headers is not None else None`).
2. Authenticated tenant whose downstream `GET /ingestion/datasets` call transiently fails —
   `_fetch_crawl_statuses` collapses every failure mode to `None` (per its own docstring), so `headers` is
   real but `crawl_statuses` is still `None`.

The template cannot currently tell these apart, so an authenticated tenant hitting a transient hiccup sees
"Log in to generate a report" — actively wrong and misleading about the real cause.

## Design

**Pattern**: none — one-template, one-conditional fix, matching the PO's own framing.

**DRY check**: `operator.py::monitoring`'s template context dict (currently `services`, `crawl_statuses`,
`recent_errors`, `runs_summary`) does not include `headers`/a session-presence flag today — this is the one
missing piece, not a duplicate of anything already passed.

**Files touched**:
- `services/dashboard-web/src/app/routers/operator.py`: in `monitoring()`'s returned `TemplateResponse`
  context dict, add `"has_tenant_session": headers is not None` (a plain boolean, not the raw `headers` dict
  — no need to leak header contents into the template layer, matching this codebase's existing
  don't-pass-raw-credentials-to-templates discipline elsewhere).
- `services/dashboard-web/src/app/templates/monitoring.html`: change both the crawl-status panel's and the
  report-form's login-prompt branches from `{% if crawl_statuses is none %}` to `{% if not has_tenant_session %}` for the true "not logged in" case; add an `{% elif crawl_statuses is none %}` branch for the
  authenticated-but-fetch-failed case, rendering the same generic downstream-failure text `error.html`
  renders by default (`"results currently unavailable"` — `error.html`'s own `{{ message | default("results
  currently unavailable") }}"`, reused verbatim as inline copy here since `error.html` itself extends
  `base.html` and can't be `{% include %}`d as a sub-block without a duplicate `<html>`/nav).

## Implementation acceptance criteria

- AC1: Anonymous visitor (`has_tenant_session=False`) still sees "Log in to..." for both the crawl-status
  panel and the report form — byte-identical wording to today for this case.
- AC2: Authenticated tenant (`has_tenant_session=True`) with a genuinely failed/empty crawl-status fetch
  (`crawl_statuses is None`) sees "results currently unavailable" (or equivalent generic downstream-failure
  copy matching `error.html`'s default), not the login prompt.
- AC3: Authenticated tenant with a successful fetch renders exactly as before (`_crawl_status_panel.html`/
  the report form) — unaffected by this ticket.

## Test acceptance criteria

- Unit test: render `monitoring.html` (or call the `monitoring()` handler with a mocked downstream client)
  three ways — (a) no session → login prompt, (b) session + failed fetch → generic-failure message, not
  login prompt, (c) session + successful fetch → existing panel/form. Assert the exact branch rendered in
  each case.
- Full `services/dashboard-web` suite re-run, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Read the actual diff in `operator.py`/`monitoring.html` — confirm the gating variable is the real
  session-presence signal (`headers is none`), not a re-derived heuristic.
- Confirm the fix does not change `_fetch_crawl_statuses`'s own failure-collapsing behavior (that stays
  intentionally coarse per its own docstring) — only the template's login-vs-error branching changed.

## Documentation acceptance criteria

- `services/dashboard-web/README.md`: one-line note under `/monitoring`'s documented behavior recording this
  fix (login-prompt vs. transient-failure now distinguished).
