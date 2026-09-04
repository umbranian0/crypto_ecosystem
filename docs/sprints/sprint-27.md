# Sprint 27 — Forecast horizon summary (dashboard-web, honesty-gated)

Sprint goal: a tenant can pick a horizon (7/15/30 days, unit resolved by FHS-001), see a
side-by-side naive-vs-model backtested validation summary with the DM verdict for a run at
that horizon, and copy a shareable text summary that carries the platform's core-finding
honesty caveat — never a bare "the ML prediction" number.

Backlog source: `docs/product/backlog-forecast-horizon-summary.md` (FHS-001 through FHS-004).

## Stories in scope, in execution order

1. **FHS-001** — Resolve horizon-unit and cross-run-selection design questions [Must, blocking].
   Sequenced first, same role RAV-001 played for Sprint 26: the backlog states every other
   story here is unbuildable/unestimable until this closes. Pure decision deliverable (ADR or
   dated `services/dashboard-web/README.md` section) — no chart, route, or template code is
   written until it does. Zero dependencies of its own.
2. **FHS-003** — Per-horizon validation summary panel on run detail [Must]. Depends on FHS-001
   only — the backlog explicitly notes it is "independently buildable/testable against a
   single `run_id`" without FHS-002's selector existing yet. Pure presentation work against
   data `run_detail` already fetches (`SplitResultResponse`'s `model_*`/`naive0_*`/`dm_*`
   fields) — no backend/schema change, same shape as Sprint 26's RAV-002/003.
3. **FHS-002** — Horizon selector on the run-list or a new horizon-summary view [Must]. Also
   depends only on FHS-001, and per the backlog is independent of FHS-003 (different page,
   same underlying data). Sequenced after FHS-003 in this list only because FHS-003 is the
   higher-value, more novel half of the capability (a selector with nothing behind it is
   inert); the Tech Lead may run FHS-002/FHS-003 in parallel once FHS-001 closes if a
   file-collision check on `runs.py`/`runs_list.html` vs. `run_detail.html` supports it (same
   call Sprint 26 left to the Tech Lead for RAV-002/003).
4. **FHS-004** — Exportable/shareable summary text with the honesty caveat [Must]. Strictly
   depends on FHS-003 (renders the same data shape the panel does) — run last.

All four are Must; none are candidates for split or partial delivery this sprint — FHS-001 is
a hard gate, and FHS-002/003/004 together are the minimum coherent slice (a selector with no
detail panel, or a panel with no way to reach it, or a panel with no exportable evidence, is
each an incomplete capability on its own).

## Stories explicitly deferred

- **FHS backlog has no Should/Could items** — all four stories are Must; nothing from this
  backlog is deferred out of this sprint.
- **RAV-004/005/009/010** (`docs/product/backlog-run-analysis-visualization.md`, Should/Could,
  deferred out of Sprint 26 with Sprint 27 named as "candidate") — **not pulled into this
  sprint**. Reasoning: (a) they compete directly for `run_detail.html`/`style.css` with FHS-003,
  the same files Sprint 26 just edited (see file-overlap section below) — landing both epics'
  work in the same window raises exactly the same-file-collision risk this repo's own
  precedent (Sprint 14 GW-016/018, Sprint 17 GW-014) tells us to avoid; (b) FHS-001..004 was
  the explicit ask for this sprint and is itself a complete, self-contained Must-only slice;
  (c) no team size/velocity was given, and this repo's convention is not to guess capacity by
  stacking two epics' Must+Should work into one sprint. Re-flagged as a candidate for Sprint
  28, after FHS ships and `run_detail.html`'s post-FHS-003 shape is known.
- **`docs/product/backlog-economic-simulator-mock-ui.md` (ECOSIM-001..012)** — **not
  scheduled**. This backlog is explicitly gated on its own open question: ECON-018/ECON-008
  reauthorization has not been confirmed by whoever owns that boundary (the backlog's own
  "Open questions" section says so plainly, and its own prioritization recommendation says not
  to slot it ahead of in-flight visualization work). Not a scheduling gap — a policy question
  that hasn't been answered. Do not sequence any ECOSIM story until that confirmation lands.
- **`docs/product/backlog-crawl-lifecycle-control.md`** — status is **CLOSED**, all 13 stories
  (INGEST-021..027, GW-027/028, DASH-116/117/118) done as of Sprint 23/24. Not a competing
  backlog for this slot. One disclosed, unfixed gap remains (cancelled-crawl restart doesn't
  resume from the true last-covered event-time, skipping the un-fetched historical gap) —
  flagged there as a recommended follow-up ticket against `ingestion-service`, not part of
  this backlog and not proposed for Sprint 27 (different module, no dependency on FHS work).

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

All four in-scope stories are pure `services/dashboard-web` presentation work (per the
backlog's own key finding #3: all data FHS-003 needs is already fetched by `run_detail` via
`GET /runs/{id}/splits`). FHS-002 needs no new backend/gateway-api/validation-service call
beyond the existing `GET /runs` **unless** FHS-001's decision requires cross-run aggregation
the existing list endpoint can't do — if the Tech Lead's ticket breakdown finds that true, flag
back to this PM before adding a new endpoint, per the backlog's own instruction; do not let a
ticket silently grow into a backend change. No `libs/naive_first_engine` or `libs/common`
change is anticipated. No new frontend dependency: FHS-004's copy-to-clipboard affordance and
FHS-002/003's rendering are plain HTMX/Jinja2 partials, matching RAV-001's zero-new-dependency
precedent (`docs/adr/0006-dashboard-web-charting-server-rendered-svg.md`) — FHS-004 needs no
charting at all, just a text/HTML partial.

## Decision-work vs. buildable work (for the Tech Lead's ticket breakdown)

- **FHS-001 is decision-work, not buildable work.** Its output is a written ADR/README
  section answering three specific questions (horizon unit/conversion; whether "7/15/30 days"
  maps onto existing `horizon` values or needs new ones; the no-completed-run-at-horizon empty
  state) and one scope decision (Epic-A-style "select among existing runs" vs. a backend
  change that finds/creates a run). Do not ticket FHS-002/003/004's acceptance criteria in
  concrete terms until this is written down — their acceptance criteria in the backlog are
  already conditional on FHS-001's answer (e.g. "7/15/30, each mapped per FHS-001's resolved
  unit").
- **FHS-002/003/004 are buildable work once FHS-001 closes.** Each has concrete, testable
  acceptance criteria in the backlog and reuses already-fetched data — no research spike
  needed. FHS-004's honesty-caveat test (asserting the caveat sentence is present verbatim, or
  a documented equivalent, in exported text) should be written test-first given this repo's
  own emphasis on regression-proofing the honesty requirement, not just the happy path.

## Risk notes

- **File-overlap with Sprint 26's uncommitted work.** As of this sprint's planning,
  `services/dashboard-web/src/app/routers/runs.py`, `templates/run_detail.html`, and
  `static/style.css` all show uncommitted modifications from Sprint 26's RAV-001/002/003 work
  (not yet committed to `main`). FHS-003 will edit `run_detail.html` and likely `runs.py`
  again. **The Tech Lead must confirm Sprint 26's changes are committed (or explicitly
  rebased onto) before starting any FHS-003 ticket** — do not build FHS-003 against a
  pre-RAV-002/003 version of `run_detail.html`, and do not let FHS-003 and any lingering
  uncommitted RAV edits land as a merge conflict. Same discipline Sprint 26 itself applied
  when checking its own overlap against Sprint 24's `_crawl_status_panel.html` changes.
- **Copy-vocabulary discipline is the highest-value/highest-risk part of this sprint, not the
  UI mechanics.** The backlog's framing decision (naive + model + DM verdict always together;
  "prediction"/"forecast"/"signal"/"target"/"recommendation" never used; a fixed, non-editable
  caveat sentence in every export) is a direct extension of CLAUDE.md's core positioning
  constraint. Every story's grep-checked vocabulary test (FHS-003) and the caveat-verbatim
  test (FHS-004) should get the same extra Tech Lead scrutiny Sprint 26 gave RAV-003's
  null-DM-handling and this repo's history gives every honesty-adjacent gate (see ECON-005's
  precedent, referenced in the ECOSIM backlog).
- **FHS-001's unit-conversion answer could reveal that most tenants have zero completed runs
  at any of 7/15/30-day horizons**, since the regression suites are all sub-day (1h/6h/24h).
  If so, FHS-002's "empty state links to `/runs/new`" behavior becomes the majority-case UX,
  not an edge case — flag this to the Tech Lead as a reason to test the empty state thoroughly,
  not treat it as a rarely-hit path (same lesson the ECOSIM backlog already drew for its own
  "not eligible" screen being the expected common case).
- **No backend change is currently in scope**, but FHS-001 could conclude one is needed for
  FHS-002 (cross-run aggregation). If that happens mid-sprint, per the backlog's own
  instruction, escalate back to this PM before adding an endpoint — do not silently absorb it
  into FHS-002's ticket scope.

## Definition of done for this sprint

- FHS-001's decision is written down (ADR or a dated `services/dashboard-web/README.md`
  section) and explicitly answers all three of its own acceptance-criteria questions plus the
  Epic-A-style-vs-backend-change scope call.
- FHS-002, FHS-003, and FHS-004 all fully implemented per their acceptance criteria, including:
  zero-matching-runs empty state with a link to `/runs/new` (FHS-002); a `dm_verdict` of "no
  significant difference" or `None` rendered as its own explicit category, never dropped or
  coerced (FHS-003, mirroring RAV-003's precedent); zero occurrences of "prediction," "forecast,"
  "signal," "target," or "recommendation" anywhere in this feature's templates (grep-checked
  test, FHS-003); the fixed caveat sentence present verbatim (or a documented equivalent) and
  not editable/removable through any UI path (FHS-004); no green/red bull-bear color pairing
  anywhere (existing `style.css` constraint, carried over unchanged).
- Tests specified in each story's own acceptance criteria pass against fixture data, including
  the null-DM-verdict fixture case and the caveat-verbatim assertion.
- `services/dashboard-web/README.md` updated to describe FHS-001's decision, the new
  horizon-selector view/route, the new summary panel, and the export affordance.
- Full `services/dashboard-web` test suite re-run with zero regressions, including Sprint 26's
  RAV-001/002/003 tests (confirms no collision damage from touching the same files again).
- `docs/product/backlog-forecast-horizon-summary.md`'s FHS-001..004 entries marked done with
  acceptance-criteria boxes checked.
