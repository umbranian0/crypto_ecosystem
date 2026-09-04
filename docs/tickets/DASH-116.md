# DASH-116 — Stop/cancel button on the crawl-status panel

**Module**: `services/dashboard-web`. **Depends on**: `GW-027` (done, Sprint 23 — the real
`POST /ingestion/connectors/{source}/cancel` proxy this button calls) and `DASH-117` (run immediately
before this ticket, same file `_crawl_status_panel.html` — file-collision-avoidance sequencing, not a
data dependency; this ticket's own diff must land on top of `DASH-117`'s already-merged gating change,
not concurrently with it).

## Analysis

Covers `docs/product/backlog-crawl-lifecycle-control.md`'s `DASH-116` story — the literal, named ask
("stop it mid-flight... from the frontend, not just via curl"). The backend capability
(`POST /connectors/{source}/cancel`, `INGEST-024`) and its gateway-api proxy (`GW-027`) are both done
and live-verified as of Sprint 23 (see `docs/tickets/README.md`'s Sprint 23 section) — this ticket is
UI-only, wiring a button to an endpoint that already works correctly, including its documented `404`/
`409` outcomes.

Hard acceptance criteria from `docs/sprints/sprint-24.md`, restated here as binding: stop button
appears **only** for `queued`/`running`/`cancelling` rows; while `status == "cancelling"`, the button is
**disabled** (not re-clickable) rather than removed or left as a normal clickable button — clicking it
again would fire a redundant cancel request against an endpoint that would legitimately return `409`
("nothing to cancel" once already cancelling is arguably still "in flight," but re-firing serves no
purpose and the sprint file is explicit: disabled, not re-clickable). Mutually exclusive with `DASH-117`'s
restart button on the same row — since `DASH-117` already gated its own form to
`completed`/`failed`/`cancelled`, and this ticket gates the stop button to the complementary
`queued`/`running`/`cancelling` set, mutual exclusivity holds by construction (the two conditions
partition the six-value status vocabulary with no overlap) — verify this partition explicitly in review,
don't just assume it.

## Design

**Pattern**: Dependency Injection (FastAPI `Depends()`) — the new route reuses the exact same
`DownstreamHeadersDep`/`GatewayApiUrlDep` DI seam every other action route in `operator.py` already
uses (`trigger_crawl`, `trigger_report_generation`). No other pattern from implementation-plan.md
section 7 applies.

**Files touched** (scoped to `services/dashboard-web` only):
- `services/dashboard-web/src/app/routers/operator.py` — new `POST /monitoring/connectors/{source}/cancel`
  route (`cancel_crawl`), placed immediately after `trigger_crawl`.
- `services/dashboard-web/src/app/templates/_crawl_status_panel.html` — add the stop button/form for
  `queued`/`running`/`cancelling` rows, disabled while `cancelling`.
- `services/dashboard-web/src/app/templates/_crawl_cancel_result.html` — new small result fragment
  (mirrors `_crawl_trigger_result.html`'s shape).
- `services/dashboard-web/tests/test_monitoring_triggers.py` — new tests for the cancel route and the
  template gating.
- `services/dashboard-web/README.md` — new "Stop action (DASH-116)" subsection.

**DRY check note** (grepped `operator.py` and `runs.py` before writing this ticket): `cancel_crawl` must
call `_call_downstream`/`_render_error_for_status` (imported from `runs.py`, already used by every route
in `operator.py`) — no new transport-error pattern, no hand-rolled `httpx.Client` try/except. The route
must depend on `DownstreamHeadersDep`/`GatewayApiUrlDep`, the same DI seam `trigger_crawl` already uses —
no new header-construction code. `_crawl_cancel_result.html` mirrors `_crawl_trigger_result.html`'s
existing structure (a one-line status confirmation) rather than inventing a new fragment shape; do not
duplicate `_crawl_trigger_result.html`'s docstring/comment verbatim, but do follow its convention of only
ever confirming what the response body actually says (the cancel endpoint returns `202
{source, status: "cancelling"}` — the fragment must not claim the crawl has actually stopped, only that
the stop request was accepted, since the real transition to `"cancelled"` happens asynchronously and is
surfaced by the existing 5-second polling fragment, not by this one-shot result).

## Implementation acceptance criteria

- [x] `POST /monitoring/connectors/{source}/cancel` (`operator.py`): depends on `DownstreamHeadersDep`,
      calls `gateway-api`'s `POST /ingestion/connectors/{source}/cancel` (`GW-027`) via `_call_downstream`,
      forwards `404`/`409` unmodified via `_render_error_for_status`, renders `_crawl_cancel_result.html`
      on `202`. Confirmed by direct code read.
- [x] Stop button/form renders for `queued`/`running`/`cancelling` rows (confirmed by direct template read).
- [x] Disabled `<button type="submit" disabled>Stopping...</button>` specifically for `cancelling`
      (confirmed by direct template read and `test_monitoring_page_stop_button_disabled_while_cancelling`).
- [x] No restart form renders for `queued`/`running`/`cancelling` rows — confirmed via the six-value
      `test_monitoring_page_never_shows_both_stop_and_restart_for_same_row` parametrized test.
- [x] `crawl_status_fragment` confirmed unchanged (`git diff` shows zero lines added/removed in that
      function).
- [x] `grep -rn "docker\|subprocess" -i services/dashboard-web/src` → zero hits (re-run personally).

## Test acceptance criteria

- [x] Cancel-route unit tests present: 202 success, 404, 409, ConnectError→502, TimeoutException→504,
      session-required redirect — read directly in `test_monitoring_triggers.py`.
- [x] Template tests present: stop-button presence/absence, disabled-while-cancelling, and the six-value
      mutual-exclusivity parametrized test (`queued`/`running`/`cancelling`/`cancelled`/`completed`/
      `failed`) — all six checked, not just a couple.
- [x] Full suite re-run directly by the Tech Lead: **144 passed, 5 deselected, 0 failed**.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Confirmed `cancel_crawl` uses `_call_downstream`/`_render_error_for_status` imported from `runs.py`
      — no new try/except (direct code read).
- [x] Enumerated all six status values against the template's two `{% if %}` gates — confirmed the
      partition is exact and exhaustive: `queued`/`running`/`cancelling` → stop (disabled only for
      `cancelling`); `completed`/`failed`/`cancelled` → restart; no overlap, no gap.
- [x] Confirmed `_crawl_cancel_result.html`'s literal copy ("Stop request for {{ source }} accepted --
      {{ result.status }}") never claims the crawl has already stopped.
- [x] Live-stack verification performed as part of this sprint's combined final proof (see Sprint 24
      outcome, `docs/tickets/README.md`) after `DASH-118` also landed — not repeated per-ticket.
- [x] Full test suite run directly: 144 passed, 0 failed.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md`'s "Stop action (DASH-116)" subsection confirmed present
      (line 674), documenting the route, `GW-027` call site, disabled-while-cancelling behavior, and the
      mutual-exclusivity relationship with `DASH-117`.
- [x] README's Contract section confirmed to include `POST /ingestion/connectors/{source}/cancel` —
      `DASH-116`.
