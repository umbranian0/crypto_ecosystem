# DASH-115 — Monitoring page reflects `INGEST-015`'s async crawl-trigger contract

## Analysis

Depends on `INGEST-015` (real contract change) and `GW-024` (proxy documentation/tests confirmed).
`services/dashboard-web`'s crawl-trigger button (`DASH-110`, `src/app/routers/operator.py`'s
`trigger_crawl`) currently renders `_crawl_trigger_result.html` with `result.status`/
`result.row_count` straight from the proxy's forwarded JSON body. After `INGEST-015`, that body is
`{source, status: "queued", since, queued_at}` — `row_count` no longer exists on it. Jinja2's default
`Undefined` renders a missing attribute access as an empty string rather than raising, so this would
not crash today, but it would silently render "Crawl for X: queued, rows." (a blank instead of a real
row count) — a real, if non-crashing, regression the ticket must fix, not leave as a cosmetic gap.

Separately, the "last crawl status" panel (`DASH-109`, `monitoring.html`'s status table, backed by
`_fetch_crawl_statuses`/`GET /ingestion/connectors/{source}/status`) is rendered once, at page load —
a user who clicks "run this tenant's crawl now" and gets a `202 queued` back has no way to see the
status table itself progress from `"queued"` to `"completed"` without a manual full-page reload. The
sprint's own framing left this in-scope-or-follow-up decision to this Tech Lead: given `INGEST-015`
makes the panel's staleness materially worse (crawls used to finish synchronously within the same
request/response, so the pre-existing page's snapshot was usually already the final state by the
time a user saw it; now it will visibly say "queued" indefinitely until a reload), this is decided
**in scope**, not deferred — it is a small, well-contained HTMX addition (this platform's own existing
templating stack, `hx-trigger="every Ns"`), not a new subsystem.

## Design

**Files touched** (all `services/dashboard-web/`, one module): `src/app/templates/
_crawl_trigger_result.html` (fix the stale `row_count` reference), `src/app/templates/monitoring.html`
(wrap the crawl-status table in a polling container), `src/app/routers/operator.py` (a new small
fragment route the polling container targets), a new `src/app/templates/_crawl_status_panel.html`
(the table extracted so both the initial page render and the polling fragment route render the exact
same markup — see DRY check below), `tests/test_monitoring.py` / `tests/test_monitoring_triggers.py`
(extended).

**DRY check**: `monitoring.html`'s crawl-status `<table>` markup (lines ~33-65) would otherwise need
to be duplicated between the full-page template and a polling-fragment template — extracted into
`_crawl_status_panel.html` (a Jinja `{% include %}`-able partial, the same pattern `_dataset_macros.html`
already establishes in this module for shared markup) and both `monitoring.html` and the new fragment
route render it from the same file. `_fetch_crawl_statuses` (`operator.py`, already exists) is reused
unmodified by the new fragment route — no second "list sources, call status per source" implementation.

**New route**: `GET /monitoring/crawl-status-fragment` (tenant-scoped, `DownstreamHeadersDep` — a
logged-out visitor polling this makes no sense, so unlike the parent `/monitoring` page this one
requires the same session-header dependency `trigger_crawl` already requires, returning a small
error fragment via `_render_error_for_status` on failure rather than a full-page error, since it is
only ever loaded via HTMX into a `<div>`) — calls `_fetch_crawl_statuses` and renders
`_crawl_status_panel.html` with the result.

**Polling**: `monitoring.html`'s crawl-status section becomes
`<div id="crawl-status-panel" hx-get="/monitoring/crawl-status-fragment" hx-trigger="load, every 5s" hx-swap="outerHTML">{% include "_crawl_status_panel.html" %}</div>`
— `hx-trigger="load, every 5s"` re-fetches on initial load (picking up the extracted partial's own
`loop.index`-based per-row target ids consistently) and every 5 seconds thereafter, `hx-swap=
"outerHTML"` replaces the whole panel (including its own `hx-get`/`hx-trigger` attributes) each time,
which is what makes the polling self-sustaining. 5s is a disclosed, arbitrary interval (not
performance-tuned) — documented as such, not presented as a measured choice.

## Implementation acceptance criteria

- [ ] `_crawl_trigger_result.html` updated to render the new `{source, status, since, queued_at}`
      shape (no `row_count`/no assumption the crawl already finished) — e.g. "Crawl for {{ source }}
      queued (since {{ result.since }})." Wording must not claim the crawl is done.
- [ ] Crawl-status table markup extracted to `_crawl_status_panel.html`, included from both
      `monitoring.html`'s initial render and the new fragment route — byte-identical markup in both
      cases (same file, not copy-pasted).
- [ ] New `GET /monitoring/crawl-status-fragment` route added to `operator.py`, tenant-scoped via
      `DownstreamHeadersDep`, reusing `_fetch_crawl_statuses` unmodified.
- [ ] `monitoring.html`'s crawl-status section wrapped in the polling `<div>` described above.
- [ ] `credential`/anonymous-visitor behavior unchanged: the initial page load for a logged-out
      visitor still shows the existing "log in to view your own ingestion status" message (the
      polling container itself is only rendered inside the already-gated branch, matching this
      page's own existing `crawl_statuses is not none` gating precedent).

## Test acceptance criteria

- [ ] `_crawl_trigger_result.html` rendering test updated: given the new `{source, status: "queued",
      since, queued_at}` payload, the rendered fragment contains "queued" and the `since` value, does
      not contain a stray literal "None rows" or similar leftover-`row_count` artifact.
- [ ] New test for `GET /monitoring/crawl-status-fragment`: authenticated request returns the same
      table markup `GET /monitoring`'s own initial render would produce for the same stubbed
      downstream state (byte-for-byte or structurally equivalent — proves the shared-partial DRY
      claim, not just "the route returns 200").
- [ ] Unauthenticated request to the fragment route is rejected the same way every other
      `DownstreamHeadersDep`-gated route in this service already is (existing convention, not a new
      one) — added as a regression test, not assumed.
- [ ] Full `services/dashboard-web` suite re-run (including the Selenium e2e suite if it exercises
      `/monitoring` — check `tests/e2e/test_core_loop.py` for any monitoring-page assertions that
      might now need the new fragment stubbed in `tests/e2e/stub_gateway_api.py`), zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- [ ] Read `_crawl_status_panel.html`: confirm it is a single file included from both places, not two
      near-identical templates.
- [ ] Confirm the polling `hx-trigger`/`hx-swap` attributes are present on the outer container in the
      fragment response itself (not only in `monitoring.html`'s initial render) — otherwise polling
      would fire once and stop, since `hx-swap="outerHTML"` replaces the element carrying those
      attributes.
- [ ] Confirm the new fragment route enforces the same tenant-auth gate as every other
      `DownstreamHeadersDep` route (read the dependency, don't just trust the test).
- [ ] Run the full suite personally, confirm the reported pass count.

## Documentation acceptance criteria

- [ ] `services/dashboard-web/README.md`'s `DASH-109`/`DASH-110` sections updated: the crawl-status
      panel now auto-refreshes every 5s via `GET /monitoring/crawl-status-fragment`; the trigger
      button's result fragment shows a `"queued"` acknowledgment, not a finished-crawl outcome —
      cross-reference `INGEST-015` for why.
