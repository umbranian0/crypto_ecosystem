# Sprint 28 — Run analysis visualization, Epic A/C extensions (deferred Should stories)

Sprint goal: extend Sprint 26's Epic A audit charts (`run_detail.html`) to all seven metric pairs and
an optional client-baseline overlay, and open Epic C (cross-run trend view) with a consistency
indicator — the four `Should` stories deferred out of Sprint 26/27 on sprint-sizing grounds, now
picked up as the next unblocked, non-trigger-gated work.

Backlog source: `docs/product/backlog-run-analysis-visualization.md` (RAV-004, RAV-005, RAV-009,
RAV-010 — all `Should`, all sized S, all deferred-not-blocked). RAV-006/007/008 remain explicitly
excluded: genuinely blocked on the storage-sizing conversation, not scheduled here.

## Stories in scope, in execution order

1. **RAV-004** — Extend the RAV-002 comparison chart to the remaining metric pairs (`smape`, `mase`,
   `da`, `f1`, `oos_r2`) via a single selector control, using only `SplitResultResponse` fields already
   fetched — no new backend field, no new endpoint. Depends on RAV-002 (done, Sprint 26). Sequenced
   first: it is a direct extension of `build_error_chart` in `charting.py`, and RAV-005's chart changes
   build on whatever shape RAV-004 leaves the chart-building function in.
2. **RAV-005** — Overlay the optional `client_baseline` series on both RAV-002/RAV-004's error chart and
   RAV-003's verdict chart, plus render the mandatory disclaimer copy adjacent to the chart when shown.
   Depends on RAV-002, RAV-003 (both done, Sprint 26). Sequenced second, after RAV-004: both stories
   touch `charting.py`'s `build_error_chart` and `run_detail.html`'s chart-rendering block, so doing
   RAV-004's metric-selector shape first avoids RAV-005 rebasing a third series onto a chart function
   that then changes shape underneath it.
3. **RAV-009** — Cross-run trend view for a repeated model configuration: extends `GET /runs`'s existing
   list view (or an adjacent page) to let a tenant select a `dataset_id`/`horizon` group and see a
   chosen metric across those runs, using only already-existing endpoints (`GET /runs`,
   `GET /runs/{id}/splits`). Depends on RAV-001 (done), RAV-002 (done). Sequenced third: this is Epic C,
   a separate page-level surface (`runs_list.html`, not `run_detail.html`), so it has no file overlap
   with RAV-004/005 and could in principle start in parallel with them — sequenced after only because
   RAV-010 depends on it directly and the Tech Lead may want the same implementer to carry both.
4. **RAV-010** — Consistency indicator ("beat Naive0 in N of M completed runs") computed client-side
   from the `dm_verdict` values RAV-009's view already fetches, with an explicit "no runs matched" state
   instead of a fabricated 0/0 ratio. Depends on RAV-009 (this sprint). Sequenced last, strictly after
   RAV-009 lands: it reuses RAV-009's own fetched/grouped run selection rather than issuing a second,
   separate fetch.

## Parallelization

- **RAV-004 and RAV-009 can run in parallel** once both their dependencies (RAV-001/002/003, all done)
  are confirmed: RAV-004 touches `charting.py` + `run_detail.html`; RAV-009 touches `runs_list.html` (or
  a new adjacent template) + possibly a small addition to `runs.py`'s router for client-side grouping
  support. No shared file between the two branches.
- **RAV-005 must run sequentially after RAV-004**, not in parallel — both edit `charting.py`'s
  `build_error_chart`/`build_dm_verdict_chart` and `run_detail.html`'s chart block; running them
  concurrently risks a merge collision on the exact same functions/template region Sprint 26's own
  file-overlap note already flagged for RAV-002/003.
- **RAV-010 must run sequentially after RAV-009**, not in parallel — it is a direct extension of
  whatever run-selection/grouping state RAV-009 introduces, not an independent fetch.
- Net: two tracks, Track 1 (`run_detail.html`/`charting.py`): RAV-004 → RAV-005. Track 2
  (`runs_list.html`/Epic C): RAV-009 → RAV-010. The two tracks are file-disjoint and can run fully in
  parallel with each other; only the within-track order is fixed.

## File-overlap / concurrent-work risk

- `services/dashboard-web/src/app/charting.py` — touched by RAV-004 (extend `build_error_chart` with a
  metric parameter) and RAV-005 (add a third series to both chart-building functions). Sequential
  within Track 1, per above.
- `services/dashboard-web/src/app/templates/run_detail.html` — touched by RAV-004 (selector control) and
  RAV-005 (client-baseline series + disclaimer copy). Same sequencing applies.
- `services/dashboard-web/src/app/static/style.css` — RAV-004 needs no new colors (reuses RAV-002's
  status-neutral palette across all seven metrics); RAV-005 needs one additional distinct,
  status-neutral color token for the third (client-baseline) series in both charts — added once, in
  Track 1, not duplicated in Track 2.
- `services/dashboard-web/src/app/routers/runs.py` — RAV-009 may need a small addition (e.g. exposing
  `dataset_id`/`horizon` on the existing `GET /runs` list response, if not already present) but RAV-009's
  own acceptance criteria require confirming client-side aggregation is insufficient before inventing
  anything server-side — the Tech Lead's ticket breakdown should re-confirm this before touching the
  router at all. RAV-004/005 do not touch this file, so no cross-track collision regardless.
- Sprint 24's carried-over-but-unimplemented `DASH-116/117/118` scope
  (`_crawl_status_panel.html`/`monitoring.html`) again has zero overlap with this sprint's files, per
  the same check Sprint 26 already ran — reconfirm before starting in case Sprint 24 is mid-flight
  concurrently.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

All four stories are pure `services/dashboard-web` presentation work against already-existing
`gateway-api`/`validation-service` contracts (RAV-004/005/009/010 all explicitly state "no new backend
field, no new endpoint" as an acceptance criterion, except RAV-009's narrow, conditional
`GET /runs` field addition noted above). No trigger is crossed, no `libs/naive_first_engine` or
`libs/common` change is required beyond a possible additive field on an existing contract, and no
service-boundary rule is at risk.

## Definition of done for this sprint

- RAV-004: single selector switches the RAV-002 chart among all seven metric pairs; DA/F1 labeled with
  their statistical meaning, no hit-rate/win-rate framing; same status-neutral color/positioning
  constraints as RAV-002 across every metric; test proves correct series per metric pair against a
  fixture split set.
- RAV-005: `client_baseline` series appears as a third, visually distinct series on both the error chart
  and the verdict chart only when present, with zero layout change when absent; `client_baseline.disclaimer`
  rendered as visible copy whenever the series is shown; a client-baseline split with both DM fields
  `None` renders the same "undefined for this split" treatment as the platform's own baseline; test
  proves three series when present, exactly two when absent.
- RAV-009: a tenant can select a run subset sharing `dataset_id`/`horizon` and see a chosen metric
  plotted across those runs, using only already-existing endpoints unless the story's own investigation
  concludes a new one is unavoidable (documented either way); copy frames this as backward-looking
  variation across completed runs, never a forecast; test proves correct series for a fixture run set.
- RAV-010: indicator computes "beat Naive0 in N of M completed runs" client-side from already-fetched
  `dm_verdict` values, no new backend statistic; a zero-match selection states plainly that no data
  matched, never a fabricated 0/0 ratio; test proves correct computation against a fixture verdict
  distribution.
- No green/red bull/bear color pairing introduced anywhere in either track's new UI.
- No chart/copy anywhere across all four stories implies a forecast, prediction, or trading
  recommendation — audit/backward-looking language only, matching `run_detail.html`'s and
  `runs_list.html`'s existing positioning vocabulary and ADR-0002/CLAUDE.md's core-finding framing.
- `services/dashboard-web/README.md` updated to describe the extended charts, the client-baseline
  overlay, and the new Epic C trend view/consistency indicator.
- Full `services/dashboard-web` test suite re-run with zero regressions.
- `docs/product/backlog-run-analysis-visualization.md`'s RAV-004/005/009/010 entries marked done with
  their acceptance-criteria boxes checked, superseding their current "deferred, not scheduled" status
  notes. RAV-006/007/008 left unchanged — still explicitly blocked on the storage-sizing conversation.
