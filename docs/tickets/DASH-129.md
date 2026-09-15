# DASH-129 — Predicted-vs-actual chart per split

**Status**: Done — implemented, tested, and personally reviewed (354/354 unit + 7/7 e2e
`services/dashboard-web` tests pass; positioning copy verified clean).

**Module**: `services/dashboard-web` only.
**Story**: RAV-008.
**Depends on**: GW-031 (needs the real proxy endpoint to call).

## Analysis

RAV-008 requires a per-split drill-down chart plotting a chosen split's actual values against the
model's (naive_last) and Naive0's predicted values over the test window, plus the client baseline when
present — server-rendered inline SVG per RAV-001's binding decision
(`docs/adr/0006-dashboard-web-charting-server-rendered-svg.md`), explicitly retrospective/audit-only
framing per CLAUDE.md and this backlog's own "Framing decision" section (no forecast/extrapolation
language, no trend-line, no future-looking element — this is strictly a view of one split's own
already-completed test window).

## Design

**Design pattern**: none new — reuses `app/charting.py`'s existing pure-function-returns-geometry
pattern RAV-002/RAV-003 already established (Dependency Injection is the only pattern this service
uses per its own README's Design notes; charting itself is not a listed pattern in implementation-plan.md
section 7, consistent with RAV-002/003/004/005's own tickets).

Files touched (scoped to `dashboard-web` only):
- `src/app/charting.py` — new pure function, `build_predicted_vs_actual_chart(points:
  list[SplitPointResponse]) -> PredictedVsActualChartData`, grouping points by `baseline_key` into up
  to three series (model/naive_last, naive0, client baseline when present), computing line/point
  geometry over a shared x (timestamp) / y (value) scale — same "no I/O, no Jinja2 import, unit-tested
  standalone" shape `build_error_chart`/RAV-003's verdict-chart function already established
  (`tests/test_charting.py` is the existing home for this kind of test, extended not duplicated).
- `src/app/routers/runs.py` — new route, `GET /runs/{run_id}/splits/{split_index}/points-chart` (or an
  `{% include %}`-based drill-down link from the existing per-split table row — dev agent's call on
  exact route shape, constrained to: reuses `DownstreamHeadersDep`/`GatewayApiUrlDep`/
  `_call_downstream`/`_render_error_for_status`, the same DI/error-handling seam every existing route
  in this file uses, no new near-identical transport-failure handling).
- `src/app/templates/` — new partial/page rendering the chart, `{% include %}`-ed or linked from the
  existing `run_detail.html` per-split table (drill-down, per the story's own "likely a drill-down from
  RAV-002's chart or the existing table's row" framing).

**Positioning/copy (binding, CLAUDE.md + this backlog's Framing decision)**: chart title/axis labels/
copy must read as "actual value vs. this split's predicted value, test-window only" or equivalent —
explicitly **not** a forecast of anything beyond that split's already-completed test window. No
trend-line, no extrapolation, no "next value" prediction rendered. Status-neutral colors only
(`--color-accent`/`--color-accent-2`, and a third distinct color for the client baseline series when
present, matching RAV-005's existing three-series precedent) — never green/red.

**DRY check note**: grepped `src/app/charting.py`/`src/app/templates/run_detail.html` before writing —
`build_error_chart`'s/RAV-003's/RAV-005's existing "pre-compute geometry as a pure function, render via
a `.chart-container`/`.chart-title`/`.chart-caption` template convention" pattern is reused, not a
fourth independent charting approach invented for this one chart.

## Implementation acceptance criteria

- [x] Renders per-split (not per-run), for model/Naive0/client-baseline-when-present series, sourced
      from GW-031's endpoint.
- [x] Chart title/axis labels/copy state "actual value vs. this split's predicted value, test-window
      only" (or equivalent), no forecast/extrapolation/signal/recommendation language anywhere on this
      view — verified by the same banned-word test convention `datasets.html`'s `tests/test_datasets.py`
      already established (grep for "predict"/"forecast"/"signal"/"recommend" outside of the explicitly
      allowed "predicted value" axis label itself).
- [x] No trend-line, no extrapolated/future point rendered under any circumstance.
- [x] Status-neutral colors only, matching `style.css`'s documented no-green/red constraint.

## Test acceptance criteria

- [x] Unit test: `build_predicted_vs_actual_chart` renders correct point-for-point series for a
      fixture split's per-point data (model, naive0, and — separately — a fixture including a client
      baseline).
- [x] Unit test: positioning-language check (no forecast/extrapolation/signal/recommendation wording)
      on the new route's rendered HTML.
- [x] Unit test: a split with zero/pruned points (VS-032's retention cutoff) renders a plain "no
      per-point data available for this split" message, not a broken/empty chart or an error.
- [x] Full `services/dashboard-web` suite passes, including the existing Selenium e2e suite (no
      regression to the existing login → submit → view loop).

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Personally read the rendered template copy and confirm zero occurrences of "prediction"/
      "forecast"/"signal"/"recommend" outside the literal "predicted value" axis label (CLAUDE.md
      positioning check, the sprint's own binding Definition of Done item). Confirmed by reading
      `_predicted_vs_actual_chart.html`/`split_points_chart.html` in full: the word "predicted" only
      appears in "predicted value" text; none of "prediction"/"forecast"/"signal"/"recommend" appear
      anywhere on this view.
- [x] Confirm no trend-line/extrapolation element exists anywhere in the SVG-building code (read
      `build_predicted_vs_actual_chart`'s full body). Confirmed: `scale_x`/`scale_y` are bounded by
      `min_ts`/`max_ts`/`min_value`/`max_value` computed only from the passed-in `points`; each
      `LineSeries.polyline_points` strictly connects already-persisted points in ascending-timestamp
      order; no code path draws or infers anything beyond that range.
- [x] Confirm the new route/partial reuses `DownstreamHeadersDep`/`GatewayApiUrlDep`/
      `_call_downstream`/`_render_error_for_status` rather than a fifth near-identical transport-
      handling block. Confirmed by reading `run_split_points_chart`'s full body in
      `src/app/routers/runs.py` — identical DI/error-handling seam to `run_detail`.
- [x] Run the full test suite (unit + e2e) personally. Unit: 354 passed, 7 deselected. E2e: 7 passed,
      354 deselected (real Chrome + Selenium Manager driver, not skipped) — both run directly via
      `.venv/Scripts/python.exe -m pytest -q -m "not e2e"` / `-m e2e`.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gains a new section ("Predicted-vs-actual chart per split
      (RAV-008/DASH-129)") documenting the new route/partial and its positioning constraints, following
      the density/style of the existing RAV-002/003/004/005 sections. Confirmed present at line 2217.
