# Backlog — Run Analysis Visualization

Source: `CLAUDE.md` (core finding, non-negotiable positioning), `docs/adr/0002-declined-automated-trading-product.md`
(the precedent this backlog must not repeat), `docs/da-tese-ao-produto.md` sections 1.2/1.3/1.5/2.7 (DM test/Harvey
correction, statistical-accuracy-vs-economic-value separation), `docs/solution-design.md` (Subsystem 3/dashboard
scope), `docs/implementation-plan.md` sections 6, 7, 9 (trigger table, design patterns, DRY rules),
`services/dashboard-web/README.md`, `services/dashboard-web/src/app/templates/run_detail.html` and
`src/app/routers/runs.py` (current run-detail rendering, DASH-004), `services/dashboard-web/src/app/static/style.css`
(documented "no green/red bull/bear pairing" constraint), `libs/common/src/naive_first_common/contracts.py`
(`SplitResultResponse`/`ClientBaselineResult` — the actual fields available today), `services/validation-service/src/app/models.py`
and `src/app/repositories/interfaces.py`/`postgres_repository.py` (what is actually persisted per split), and the
existing `docs/product/backlog-dashboard-web.md` (naming/ID conventions this backlog follows without renumbering
that file's own `DASH-*` series).

Scope: adding visualizations to `services/dashboard-web`'s run detail page (and, for the trend epic, a
run-list-level view) so a tenant can visually inspect a completed validation run's model-vs-Naive0 comparison and
draw their own conclusions. Explicitly out of scope, and refused outright regardless of future requests: any
automated buy/sell signal, forecast, or trading recommendation surfaced by this platform (see the "framing" note
below and ADR-0002). Also out of scope: `services/reporting-service` (Subsystem 4, its own trigger #7, not this
backlog's concern) and `services/economic-service` (trigger #11, still deferred).

## Framing decision (binding on every story below)

This backlog exists because of two requests made back-to-back in the same conversation: first "predict to buy or
sell in short/mid/long term" (declined — this is exactly the premise ADR-0002 already rejected, and CLAUDE.md's
core finding is that no model has beaten Naive0 in a stable, significant way at any horizon, so a buy/sell
prediction feature would be selling something this platform's own research has falsified), then immediately
clarified as "add graphs on the runs so we can make our own data analysis and predictions by our own." Every story
in this backlog is written to serve the second framing only: these are **audit charts showing what already
happened in a completed validation run** — model vs. Naive0 metrics, DM-test verdicts, error distributions — styled
the same restrained, status-neutral way `run_detail.html`'s existing copy and `style.css`'s palette already are.
No story here authorizes a forecast, a recommendation, or a signal, and no future request to add one should be
treated as a small extension of this backlog — it is the same line ADR-0002 already drew.

## Key findings from reading the current code (binds scope below)

1. **Per-split aggregated metrics already exist and are already fetched.** `SplitResultResponse` (and the
   `SplitResult` table it mirrors) carries, per split: `model_*`/`naive0_*` for `mae, rmse, smape, mase, da, f1,
   oos_r2`, plus `dm_statistic, dm_pvalue, dm_verdict`, plus split boundaries (`train_start/end, purge_start/end,
   test_start/end`), plus an optional `client_baseline` (VS-017). `run_detail.html` already renders all of this as
   a table. Charting this requires **no backend or schema change** — it is a pure dashboard-web presentation
   story. This is Epic A.
2. **Raw per-point predicted/actual values are NOT persisted anywhere.** `SplitResult` (both the SQLAlchemy model
   in `services/validation-service/src/app/models.py` and `SplitResultRecord` in `repositories/interfaces.py`)
   stores only the seven aggregated `MetricSet` fields per baseline per split — there is no `predictions` or
   `actuals` array column, and no per-point table exists. `naive_first_engine`'s protocol computes predictions
   in-memory during metric aggregation but nothing downstream of that keeps the raw arrays. A "predicted vs.
   actual" line/scatter chart per data point is therefore **not possible today** without a new persistence
   capability — this is Epic B, and it is scoped as a prerequisite, not assumed away.
3. **No charting library is wired into dashboard-web today.** A grep across `services/dashboard-web` for
   `chart.js`/`plotly`/`d3`/`vega` (case-insensitive) found nothing. Given CLAUDE.md's locked-in server-rendered
   FastAPI + Jinja2/HTMX architecture (not a SPA), the choice of a client-side JS library vs. a server-rendered
   SVG/image approach is a real open decision, not a detail to leave implicit in a chart story — this is RAV-001.

## Prioritization scheme

MoSCoW (Must/Should/Could/Won't), matching this repo's existing backlogs. Each story's rationale line ties the
priority to (a) which epic it belongs to, (b) whether it depends on data/capability that already exists vs. a new
one, and (c) `services/dashboard-web`'s already-fired build-order position (trigger #8 override, already recorded
in `backlog-dashboard-web.md` — not re-litigated here) vs. `services/validation-service`'s (trigger #3, already
fired) schema-change cost for Epic B.

## Explicit scope/sequencing decisions

1. This backlog does not renumber or duplicate `backlog-dashboard-web.md`'s `DASH-*` series — stories here use a
   dedicated `RAV-*` prefix (Run Analysis Visualization) because this feature spans two services
   (`dashboard-web` for rendering, `validation-service`/`gateway-api` for Epic B's new persistence/API surface),
   the same cross-cutting-prefix precedent `backlog-technical-upgrades.md` set with `ARCH-*`.
2. Epic B (raw predicted-vs-actual charting) is sequenced strictly after Epic A and is **not** assumed to ship in
   the same cycle — it requires a schema change and a new API surface. **Updated 2026-09-15**: the founder has
   now resolved the storage-growth/retention question that previously gated this epic — build per-point storage
   together with a concrete, bounded retention policy in RAV-006 itself (see RAV-006's own acceptance criteria).
   Epic B (RAV-006/007/008) is Should-priority, real committed scope, no longer Could/blocked.
3. RAV-001 (chart-technology decision) blocks every other visualization story in Epic A and Epic C — none of them
   can be estimated until it resolves, so it is sequenced first and marked Must despite being a decision rather
   than a shippable feature.
4. Epic C (run-list trend view) is marked Should, not Must, per the task's own framing of it as optional — it adds
   real value (spotting whether a model configuration performs consistently over time) but is not required for
   the core "can I visually audit one run" need Epic A satisfies.

## Epic A — Per-split metrics visualization (uses data that already exists)

### RAV-001 — Decide dashboard-web's charting approach before any chart story starts [Must] — DONE (Sprint 26)
**As** dashboard-web's future implementer, **I want** a documented decision on charting technology and rendering
strategy, **so that** Epic A/C stories aren't estimated or built against an undecided foundation, and the decision
is made once, deliberately, not implicitly inside the first chart story that happens to get picked up.

Acceptance criteria:
- [x] A written decision (`docs/adr/0006-dashboard-web-charting-server-rendered-svg.md`) names the chosen charting
      approach and explicitly considers at least: (a) a client-side JS library (e.g. Chart.js) loaded as a static
      asset, consistent with HTMX's existing "progressively enhance a server-rendered page" style, vs. (b)
      server-rendered SVG/PNG generated in Python and embedded as an `<img>`/inline `<svg>`, with no new JS
      dependency at all. **Decided: (b), server-rendered inline SVG.**
- [x] The decision states explicitly that no new frontend dependency is introduced (no JS charting library, no
      Python plotting/image library either — plain string-built SVG via the existing Jinja2 templating).
- [x] The decision confirms compatibility with CLAUDE.md's locked-in server-rendered FastAPI + Jinja2/HTMX
      architecture — no SPA framework, no client-side routing.
- [x] The decision is silent on/does not touch Epic B's data question — this story is charting-technology only
      (the ADR explicitly states so in its own text).

Rationale for priority: blocking dependency for every other visualization story in this backlog; without it, RAV-002
through RAV-005 and RAV-009/RAV-010 cannot be estimated. Owned entirely within dashboard-web's existing boundary
(presentation layer only), no trigger implication.
Depends on: none

**Status: DONE (Sprint 26, `docs/tickets/RAV-001.md`, `docs/adr/0006-dashboard-web-charting-server-rendered-svg.md`).**

### RAV-002 — Model-vs-Naive0 error comparison chart across a run's splits [Must]
**As** dashboard-web, **I want** to render a chart comparing `model_mae`/`model_rmse` against `naive0_mae`/
`naive0_rmse` across all of a run's splits, **so that** a tenant can see at a glance whether/where a model's error
was lower or higher than Naive0's, instead of reading every row of the existing table.

Acceptance criteria:
- [x] `run_detail.html` renders one chart (server-rendered inline SVG bar chart, per RAV-001's decision) with
      split index on one axis and MAE on the other, plotting `model_mae` and `naive0_mae` as two distinguishable
      series over the same splits already fetched by `run_detail`'s existing `GET /runs/{id}/splits` call — no new
      backend call, no new field. (MAE only, matching the acceptance criterion's own parenthetical allowance — a
      metric selector for the other pairs is RAV-004, deferred.)
- [x] The two series use the existing status-neutral palette (`--color-accent`/`--color-accent-2`) — never a
      green/red or up/down color pairing, matching `style.css`'s own documented "no green/red bull/bear pairing
      anywhere" constraint.
- [x] The existing per-split table remains on the page, unchanged — this chart is an addition, not a replacement,
      so a tenant who wants exact values still has them.
- [x] Chart title, axis labels, and any surrounding copy describe this as "model vs. Naive0 error by split" or
      equivalent audit language — no word or phrase implies a forecast, a prediction the platform is making, or a
      trading recommendation. Matches `run_detail.html`'s existing positioning language.
- [x] A run with zero splits (e.g. still `running`) renders the existing "No per-split validation results yet"
      message, no empty/broken chart shown.
- [x] Test: chart renders correct series values for a fixture set of splits; a zero-split run does not attempt to
      render a chart. Verified additionally against a real completed run on the live stack (Sprint 26 Tech Lead
      review) — see `docs/tickets/RAV-002.md`.

Rationale for priority: this is the first, highest-value item — directly serves the request's second framing
("graphs on the runs so we can make our own data analysis") using data already fetched by DASH-004; no new
capability required. Sits squarely inside dashboard-web's existing "render what gateway-api returns" boundary.
Depends on: RAV-001

**Status: DONE (Sprint 26, `docs/tickets/RAV-002.md`).**

### RAV-003 — DM-test verdict visualization per split [Must] — DONE (Sprint 26)
**As** dashboard-web, **I want** a chart showing each split's `dm_verdict` ("better"/"worse"/"no significant
difference") across a run, **so that** a tenant can see the pattern of DM-test outcomes across the walk-forward
splits at a glance, matching how the thesis itself reports instability (CLAUDE.md's core finding: "more 'worse'
than 'better' splits ... at nearly every horizon").

Acceptance criteria:
- [x] Renders a chart (categorical bar of verdict counts, server-rendered inline SVG per RAV-001's decision) using
      each split's existing `dm_verdict` field, verbatim, from the already-fetched `SplitResultResponse` list — no
      recomputation of the verdict client-side.
- [x] A split whose `dm_statistic`/`dm_pvalue` are `null` is shown as its own distinguishable category
      ("undefined for this split"), never silently dropped or coerced into "no significant difference" — proven by
      a dedicated fixture-based unit test.
- [x] Verdict categories use distinct, status-neutral colors (`--color-status-completed-text` teal for "better",
      `--color-status-failed-text` orange for "worse", `--color-status-running-text` blue-gray for "no significant
      difference", `--color-text-muted` gray for "undefined for this split" — no green/red pairing, confirmed by a
      dedicated color-safety test).
- [x] Copy accompanying the chart states plainly that "better"/"worse" describes this split's own out-of-sample
      error relative to Naive0, under the Harvey-corrected DM test already applied upstream — never phrased as
      "the model recommends" or "predicts" (verified against the real rendered page with zero occurrences of
      prediction/forecast/signal/recommend).
- [x] Test: verdict counts/categories render correctly for a fixture set including at least one `null`-DM split.

Rationale for priority: directly visualizes the platform's core differentiator (rigorous DM testing against
Naive0) using data already returned by the existing splits endpoint; Must because it is the second half of the
"can a tenant audit a run visually" need RAV-002 only half-covers (error magnitude without significance is
incomplete).
Depends on: RAV-001

**Status: DONE (Sprint 26, `docs/tickets/RAV-003.md`).**

### RAV-004 — Extend the comparison chart to the remaining metric pairs [Should]
**As** dashboard-web, **I want** the RAV-002 chart extended (via a toggle/selector, not a full page of separate
charts) to also cover `smape`, `mase`, `da`, `f1`, and `oos_r2` model-vs-naive0 pairs, **so that** a tenant is not
limited to MAE/RMSE if a different metric matters more for their evaluation.

Acceptance criteria:
- [x] A single control (dropdown/tab set) switches the RAV-002 chart's plotted metric among all seven pairs
      already present on `SplitResultResponse` — no new backend field, no new endpoint.
- [x] Directional-accuracy (`da`) and F1 series are labeled with their statistical meaning ("directional accuracy,"
      "F1") and not reworded into anything resembling a hit-rate/win-rate trading framing.
- [x] Same status-neutral color/positioning constraints as RAV-002 apply to every metric pair, not only MAE/RMSE.
- [x] Test: switching the selector re-renders the correct series for each of the seven metric pairs against a
      fixture split set.

Rationale for priority: genuine incremental value (some tenants will care about DA/F1/OOS R2 over MAE/RMSE) but
not required for the minimum "audit a run visually" capability RAV-002/RAV-003 already deliver — a reasonable
next increment, not a blocker.
Depends on: RAV-002

**Status: DONE (Sprint 28, `docs/tickets/RAV-004.md`).**

### RAV-005 — Overlay the optional client-supplied baseline on existing charts [Should]
**As** dashboard-web, **I want** RAV-002/RAV-003's charts to include a third series/category for `client_baseline`
when a run was submitted with a `client_prediction_reference` (VS-017), **so that** a tenant who supplied their own
model's predictions can visually compare it against both Naive0 and the platform's own naive_last baseline in one
place, not just in the existing table.

Acceptance criteria:
- [x] When `SplitResultResponse.client_baseline` is present for a run's splits, RAV-002's error chart and RAV-003's
      verdict chart each gain a third, visually distinct series for it; when absent (the common case), both charts
      render exactly as RAV-002/RAV-003 already specify — no layout change for runs without a client baseline.
- [x] `client_baseline.disclaimer` (the mandatory audit disclaimer text already returned by the API, per VS-017)
      is rendered as visible copy adjacent to the chart whenever that series is shown — never omitted just because
      the information is now also in a chart.
- [x] A `client_baseline` split with `dm_statistic`/`dm_pvalue` both `None` (the documented single-point-split
      case) renders the same "undefined for this split" treatment RAV-003 already defines for the platform's own
      baseline, not a different/inconsistent treatment for the third series.
- [x] Test: chart renders three series when `client_baseline` is present across a fixture split set; renders
      exactly two (unchanged from RAV-002/003) when absent.

Rationale for priority: real value for the subset of tenants using VS-017's bring-your-own-prediction path, but
that path itself is optional/less-traveled than the always-present model/naive0 comparison — Should, not Must.
Depends on: RAV-002, RAV-003

**Status: DONE (Sprint 28, `docs/tickets/RAV-005.md`).**

## Epic B — Raw predicted-vs-actual visualization (requires new backend capability — prerequisite, not assumed)

### RAV-006 — Persist raw per-point predicted/actual values per split, with a concrete retention policy [Should]
**As** a future consumer of per-split detail (this visualization epic, and potentially `reporting-service` later),
**I want** `validation-service` to persist each split's raw per-point predicted and actual values (for both
`naive_last`/`model` and `naive0`, and `client_baseline` when present), **together with** a real, bounded
retention/pruning mechanism built in the same unit of work, **so that** a predicted-vs-actual chart becomes
possible at all — today only the seven aggregated `MetricSet` fields per baseline are stored
(`services/validation-service/src/app/models.py`'s `SplitResult` table has no such column, confirmed by reading
it), so no story downstream of this one can render a real per-point chart without it — and so that this new,
potentially large per-point table never grows unbounded from day one.

**Resolved (2026-09-15, founder decision)**: build per-point storage — but only together with a concrete
retention/pruning policy in this same ticket, not deferred. The prior acceptance criterion allowing "none yet,
revisit once storage growth is measured" as a valid answer is removed; this story is no longer blocked on a
separate storage-sizing conversation before scheduling — the storage estimate and the retention policy are now
both part of this ticket's own Definition of Done, decided up front rather than punted.

Acceptance criteria:
- [ ] A new, explicitly-scoped schema change (new table or JSON/array column, Tech Lead's call, not this backlog's)
      persists, per split per baseline, the aligned `(timestamp, predicted, actual)` triples the engine already
      computes in-memory during metric aggregation (`naive_first_engine`'s protocol) but currently discards after
      reducing to metrics.
- [ ] A written storage-growth estimate (rows = tenants × runs × splits × test-window-length × baselines-per-split)
      is still produced and presented to the Architect/Tech Lead as part of this ticket — kept from the prior
      version of this story, not dropped.
- [ ] **A concrete retention/pruning policy is specified and implemented as part of this same ticket, not left as
      a TODO or comment.** Default shape (Tech Lead may choose a different bound if the storage estimate above
      argues for it, but must state and implement one, not defer the decision): **keep per-point data only for
      the most recent 90 days OR the most recent 20 runs per tenant/dataset combination, whichever is simpler to
      implement correctly** — stated explicitly here so it is a real requirement, not an open question. The
      mechanism enforcing this bound must be **one** of the following, and must be real and testable (a passing
      test proving old per-point rows are actually gone or actually excluded, not merely a docstring claiming the
      policy exists):
      - a scheduled deletion/archival job, matching this platform's existing "standalone, operator-run" script
        convention (`scripts/backfill_from_csv.py`/`seed_tenant.py`'s precedent) — e.g.
        `scripts/prune_split_points.py --older-than-days 90` or equivalent, runnable via cron/operator invocation; or
      - a query-time cutoff enforced in the repository/query layer (e.g. the per-point read path silently excludes
        rows older than the bound, and a companion write-time or periodic delete keeps the table from growing
        unbounded regardless of whether anyone ever queries it).
- [ ] The change does not alter or weaken the existing leakage-aware protocol in any way — raw predictions are
      captured as a side-effect of the existing walk-forward computation, never by re-fitting or re-predicting
      outside a split's own train/test boundary.
- [ ] No existing `SplitResultResponse`/`SplitResultRecord` field changes shape or meaning — this is additive only
      (new field/endpoint, not a repurposing of `model_*`/`naive0_*`, matching the precedent VS-017 already set for
      `client_baseline` as its own separate, additive column).
- [ ] Test proves the retention policy actually bounds the table: a fixture with data older than the chosen
      cutoff (by age or by run-count, matching whichever bound is implemented) is excluded from `RAV-007`'s read
      path and/or physically removed by the chosen deletion mechanism — not just asserted as "the policy exists
      in code," but exercised end-to-end.

Rationale for priority: **Should**, not Must — real, founder-approved, unblocked scope (no longer gated on a
separate storage-sizing conversation, which is now folded into this ticket's own acceptance criteria), and a
genuine value-add for auditing individual splits, but Epic A (RAV-002–RAV-010, all Must/Should and already done)
already delivers this backlog's core "audit a run visually" need without per-point data — this remains the
highest-fidelity, highest-cost addition in the backlog, one step below the Must-tier stories that unlock the
platform's baseline audit capability at all. Not Could: the founder has now explicitly authorized and scoped it,
so it is real committed scope for an upcoming sprint, not a maybe.
Depends on: none (but blocks RAV-007, RAV-008)

### RAV-007 — Expose per-point predicted/actual values via the existing run/split API surface [Should]
**As** dashboard-web, **I want** a way to fetch the per-point values RAV-006 persists (a new field on
`GET /runs/{id}/splits`, or a new `GET /runs/{id}/splits/{split_index}/points`-style endpoint — Tech Lead's call),
**so that** a chart can be built against real data rather than an assumption that it already exists.

Acceptance criteria:
- [ ] The new endpoint/field is added to `validation-service` and proxied through `gateway-api`, following the
      same pass-through-only pattern `GET /runs/{id}/splits` already uses (no service reimplementing another
      service's logic, per CLAUDE.md's "no service imports another service's code" rule).
- [ ] Response shape is added to `naive_first_common.contracts` as the single canonical definition (ARCH-003's
      established convention), not a fourth hand-duplicated field list.
- [ ] Tenant scoping (RLS) applies to this new data exactly as it does to `split_results` today — no new path that
      bypasses `set_config('app.tenant_id', ...)`.
- [ ] Given the potential row volume flagged in RAV-006, this endpoint supports pagination or a per-split fetch
      granularity (not "return every point for every split in a run in one response") — sized in coordination with
      RAV-006's storage estimate, not assumed to be small.
- [ ] Reads through this endpoint respect RAV-006's retention/pruning cutoff — a request for a split whose
      per-point data has already been pruned returns the same collapsed-empty shape a zero-row split would, not an
      error, and never implies the data never existed.

Rationale for priority: cannot be estimated or built before RAV-006 lands; **Should**, matching RAV-006's revised
priority now that the founder has authorized and scoped that prerequisite — there is still no value in an API for
data that doesn't exist yet, but it is no longer speculative/Could-tier scope now that RAV-006 itself is real,
committed work.
Depends on: RAV-006

### RAV-008 — Predicted-vs-actual chart per split [Should]
**As** dashboard-web, **I want** a chart plotting a chosen split's actual values against the model's and Naive0's
predicted values over the test window, **so that** a tenant can visually see where a model tracked, over-shot, or
under-shot actual outcomes during that split's out-of-sample period.

Acceptance criteria:
- [ ] Renders per-split (not per-run — this is a detail view within a split, likely a drill-down from RAV-002's
      chart or the existing table's row), using RAV-007's endpoint, for the model, Naive0, and (when present) the
      client baseline series.
- [ ] Chart title/axis labels/copy describe this as "actual value vs. this split's predicted value, test-window
      only" — explicitly not labeled as a forecast of anything beyond that split's already-completed test window,
      and no extrapolation/trend-line/future-looking element of any kind is rendered.
- [ ] Same status-neutral color constraint as every other chart in this backlog.
- [ ] Test: chart renders correct point-for-point series for a fixture split's per-point data.

Rationale for priority: highest-fidelity chart in this backlog, still blocked on RAV-006/RAV-007 landing first
(sequencing dependency, not a priority downgrade); **Should**, matching RAV-006/RAV-007 now that the founder has
authorized that prerequisite work — Epic A (already done) validated real tenant demand for the cheaper charts
first, so this is the natural next increment once its two dependencies close, not speculative scope.
Depends on: RAV-007

## Epic C — Run-list-level trend view (optional, per task framing)

### RAV-009 — Cross-run trend view for a repeated model configuration [Should]
**As** dashboard-web, **I want** a view showing a chosen metric (e.g. model MAE, or DM verdict distribution) across
multiple runs over time for a tenant, **so that** a tenant can see whether the same model configuration performs
consistently across runs/time, not just inspect one run in isolation — directly serving the second half of the
task's own framing (a tenant analyzing trends "on their own," not a single-run snapshot).

Acceptance criteria:
- [x] Extends the existing `GET /runs` list view (`runs_list.html`/`DASH-005-01`) or adds an adjacent page, calling
      only endpoints that already exist (`GET /runs` for the run list, `GET /runs/{id}/splits` per run) — no new
      backend aggregation endpoint invented here without first confirming, in the story's own investigation, that
      client-side aggregation of already-fetched per-run summaries is insufficient.
- [x] A tenant can select a subset of runs (e.g. same `dataset_id`/`horizon`) to compare on one chart — grouping is
      explicit and visible, never an implicit "all runs ever" chart that conflates unrelated configurations.
- [x] Chart/copy frames this as "how this model configuration's validation results have varied across runs" —
      never "trend" language that implies a forecast of future runs' outcomes; this is a look backward at completed
      runs only.
- [x] Same status-neutral color constraint as every chart in this backlog.
- [x] Test: correct series rendered for a fixture set of runs sharing a `dataset_id`/`horizon`.

Rationale for priority: real value (surfaces instability or consistency across time, echoing CLAUDE.md's "honest
instability reporting" positioning) but explicitly framed by the task as optional relative to the single-run views
in Epic A — Should, not Must.
Depends on: RAV-001, RAV-002

**Status: DONE (Sprint 28, `docs/tickets/RAV-009.md`).** Implemented as a new adjacent page
(`GET /runs/trend`, `runs_trend.html`), not an extension of `runs_list.html` — dev's documented
choice per this story's own "or adds an adjacent page" allowance.

### RAV-010 — Consistency indicator: how often has this configuration beaten Naive0 [Should]
**As** dashboard-web, **I want** a simple aggregate indicator (e.g. "X of Y completed runs had a majority of
'better' DM verdicts against Naive0") for a selected group of runs, **so that** a tenant gets an honest, compact
summary of stability across runs without having to eyeball RAV-009's chart themselves.

Acceptance criteria:
- [x] Computed client-side (dashboard-web) from already-fetched `dm_verdict` values across the selected runs'
      splits — no new backend statistic invented, and no new significance test computed outside
      `naive_first_engine`'s existing Harvey-corrected DM test.
- [x] Explicitly framed as a descriptive count/ratio of past outcomes ("beat Naive0 in N of M completed runs"),
      never as a probability of future performance, a confidence score, or anything resembling a recommendation.
- [x] If zero runs match the selected grouping, states that plainly — never a fabricated 0/0 ratio rendered as
      "0% beat naive," which reads as a false negative rather than "no data."
- [x] Test: indicator computes correctly against a fixture set of runs with known verdict distributions.

Rationale for priority: small, high-clarity addition to RAV-009's chart; Should, sequenced right after it since it
reuses the same fetched data with no new capability.
Depends on: RAV-009

**Status: DONE (Sprint 28, `docs/tickets/RAV-010.md`).**

## Epic D — Runs-list visualization and chart prominence (founder-scoped closure of two specific gaps)

Source (in addition to the file-level Source line above): confirmed by direct reading on 2026-09-25 of
`services/dashboard-web/src/app/templates/run_detail.html` (per-split table; line 115 carries the current
plain-text link `<a href="/runs/{{ run.id }}/splits/{{ split.split_index }}/points-chart">Actual vs. predicted
value</a>`), `services/dashboard-web/src/app/templates/runs_list.html` (plain `<table>`, zero charts, no link to
`/runs/trend`), `services/dashboard-web/src/app/routers/runs.py` (`runs_list`, line 727 — calls only `GET /runs`,
no split data fetched; `runs_trend`, line 1059; `run_split_points_chart`, line 1131 — one split's points fetched
per call via `GET /runs/{run_id}/splits/{split_index}/points`, no batch/cross-split endpoint; `run_detail`, line
1184, with its own existing `MAX_RENDERED_SPLITS = 500` truncation at line 1230), `services/dashboard-web/src/app/
charting.py` (existing `build_error_chart`, `build_dm_verdict_chart`, `_verdict_category`/
`verdict_category_and_css_slug`, `build_headline_verdict_summary`, `build_predicted_vs_actual_chart` — the only
chart-building logic this epic may reuse, never duplicate), `docs/adr/0006-dashboard-web-charting-server-rendered-
svg.md` (binding: server-rendered inline SVG only, no new dependency), `services/gateway-api/src/app/routers/
runs.py` (`get_splits`, line 203) and `services/validation-service/src/app/routers/splits.py` (`get_splits`, line
116) — confirmed no batched/cross-run or cross-split summary endpoint exists anywhere today.

Scope: closes exactly two founder-confirmed gaps, and nothing beyond them. (1) `runs_list.html` has zero
visualization and no discoverable link to the already-shipped `/runs/trend` cross-run view. (2) `run_detail.html`
sends a tenant to a separate page per split for the predicted-vs-actual chart instead of showing it inline.
Explicitly out of scope, per the founder's own instruction: any new chart type (no residual-distribution chart, no
error-over-time chart, no metric-pair scatter plot — this epic presents already-computed/already-charted data at
new locations, it does not compute anything new), and a links-only change to `runs_list.html` (the verdict
indicator and sparkline are required scope, not optional extras). This epic does not touch `naive_first_engine`,
`services/economic-service`, or any pricing/prediction surface, and does not reopen Epic B's own scope (its
backend capability is confirmed already shipped, used as-is here — see RAV-015).

### RAV-011 — Visible link from the runs list to the existing cross-run trend view [Must]
**As** dashboard-web, **I want** `runs_list.html` to include a visible link to the already-shipped `/runs/trend`
page, **so that** a tenant browsing the plain runs list can discover the cross-run trend/consistency view without
already knowing its URL.

Acceptance criteria:
- [x] A link to `/runs/trend` (the same route `runs_trend`, `routers/runs.py` line 1059, already renders) appears
      on `runs_list.html` whenever there is at least one run to show; no broken/dead link when the run list is
      empty (the existing "No validation runs yet" branch is unaffected).
- [x] Link copy reuses `/runs/trend`'s own existing framing (RAV-009's "how this model configuration's validation
      results have varied across runs" language) — no new, independently-worded marketing copy for the same
      destination.
- [x] No new route, endpoint, or backend logic — this is a single template-level addition.
- [x] Test: rendered `runs_list.html` contains an `<a href="/runs/trend">` (or equivalent) when `runs` is
      non-empty.

Rationale for priority: trivial to ship and a real, founder-named gap (the page exists but is undiscoverable
today), but on its own it is explicitly **not** sufficient to satisfy the founder's request — grouped as Must
alongside RAV-013/RAV-014 because it is the third, smallest piece of the same "prominence" requirement, not a
substitute for the other two.
Depends on: none (links to RAV-009, already DONE)

**Status: DONE (Sprint 60, `docs/tickets/RAV-011.md`).**

### RAV-012 — Bounded per-run split-summary data available to the runs-list page [Must]
**As** dashboard-web, **I want** the `runs_list` route to have access to each displayed run's split-level verdict
and error data without turning one page load into an unbounded number of downstream calls, **so that** RAV-013's
verdict indicator and RAV-014's sparkline have real data to render, and the page stays fast regardless of how many
runs a tenant has.

This is the open design question named explicitly in this epic's own brief — the acceptance criteria below require
that one bounding approach be chosen and proven bounded; they do not prescribe which one.

Acceptance criteria:
- [ ] `runs_list` (`routers/runs.py`, currently only calling `GET /runs` at line 727) gains access, for every run
      on the currently rendered page only, to the same per-split `model_mae`/`naive0_mae` and `dm_verdict` data
      already returned by `GET /runs/{run_id}/splits` (gateway-api `routers/runs.py:get_splits`, line 203;
      validation-service `routers/splits.py:get_splits`, line 116) — reusing that existing `SplitResultResponse`
      contract shape, never a parallel/duplicate field set.
- [ ] The sprint's sequencing/Tech Lead decision picks **exactly one** bounding approach and states it explicitly
      in the ticket: (a) a new batched/summary endpoint on gateway-api + validation-service accepting a page of
      run IDs and returning per-run split-summary data in one round trip; (b) a bounded per-page N+1, with a hard,
      enforced page-size cap on `runs_list`'s own `limit` parameter, so the number of downstream calls per page
      load is capped at that same limit; or (c) a precomputed summary field persisted on the run row and kept in
      sync as splits complete. Whichever is chosen, this story does not authorize skipping the choice — one runs-
      list page load must issue a bounded, page-size-proportional number of downstream calls, never one uncapped
      call per run regardless of how many runs a tenant has accumulated.
- [ ] If (b) is chosen, `runs_list`'s `limit` parameter (already accepted today, line 731, currently unbounded)
      gets an enforced hard maximum — the bound must be real, not "usually small in practice."
- [ ] No change to `GET /runs/{run_id}/splits`'s own existing contract or behavior — this is additive only (a new
      endpoint, or a new call pattern against the existing one), never a repurposing of the per-run detail
      endpoint.
- [ ] Test: a fixture page of N runs results in a provably bounded number of downstream HTTP calls from
      dashboard-web (not O(N) uncapped, and not asserted only in a docstring).

Rationale for priority: prerequisite/enabler for RAV-013 and RAV-014 — neither can render real per-run data
without it, and this epic's own brief requires the N+1 question to be a named, resolved concern before those
stories ship rather than discovered during implementation. Must, because both of its dependents are Must.
Depends on: none (blocks RAV-013, RAV-014)

### RAV-013 — Per-run verdict indicator on the runs list [Must]
**As** dashboard-web, **I want** each row on `runs_list.html` to show a compact indicator of that run's benchmark-
comparison outcome against Naive0, **so that** a tenant scanning many runs can see which ones showed a "better"/
"worse"/"no significant difference"/undefined DM-test outcome without opening each run individually.

Acceptance criteria:
- [ ] Computes one aggregate category per run by reusing `charting.py`'s existing per-split categorization
      (`_verdict_category`/`verdict_category_and_css_slug`, and/or the same aggregation
      `build_headline_verdict_summary` already performs for a single run's "beat Naive0 on N/M splits" sentence)
      applied to RAV-012's split data — no second, independently-derived verdict rule written in the route or
      template.
- [ ] Uses the same four status-neutral categories/colors already defined for DM verdicts elsewhere
      (`--color-status-completed-text` "better", `--color-status-failed-text` "worse",
      `--color-status-running-text` "no significant difference", `--color-text-muted` "undefined") — never a
      green/red pairing, matching `style.css`'s documented constraint and every existing verdict chart in this
      backlog.
- [ ] Indicator copy reads only as a benchmark-comparison outcome for this run (e.g. "Beat Naive0 on N/M splits"
      or the equivalent compact form) — never phrased as "this model is good/bad to trade," never a buy/sell/
      signal word, matching CLAUDE.md's positioning rule and the same wording precedent
      `build_headline_verdict_summary` already sets on `run_detail.html`.
- [ ] A run with zero splits (e.g. still running, or failed before any split completed) shows a plain "no results
      yet" state in that column — never a fabricated or default verdict category.
- [ ] Server-rendered inline SVG or plain styled text/badge (Tech Lead's call between the two — either way, per
      ADR-0006, no client-side JS, no new dependency).
- [ ] Test: rendered `runs_list.html` shows the correct verdict category/label for a fixture set of runs with
      known split-verdict distributions, including a zero-split run.

Rationale for priority: the core "visualization" gap the founder named for the runs list — reuses existing
DM-verdict logic entirely (no new statistic, no new significance test); Must because the founder explicitly
declined a links-only change and named this indicator as required scope.
Depends on: RAV-012

### RAV-014 — Per-run compact error sparkline on the runs list [Must]
**As** dashboard-web, **I want** each row on `runs_list.html` to show a small sparkline of model-vs-Naive0 MAE
across that run's splits, **so that** a tenant can see the shape/stability of a run's error at a glance, consistent
with the same metric RAV-002's full-size chart already shows on `run_detail.html`.

Acceptance criteria:
- [ ] Reuses `charting.py`'s existing error-series data construction for `model_mae`/`naive0_mae` (the same
      underlying series `build_error_chart` already assembles for RAV-002 — a new compact-rendering function may
      be added to `charting.py`, but it must build on the same `Bar`/`SplitBars` data shapes, never a second
      hand-rolled MAE-series computation).
- [ ] Renders as a small server-rendered inline SVG (per ADR-0006 — no new dependency, no client-side JS charting
      library, no Python plotting library), sized for a table cell (fixed small width/height, distinct from
      RAV-002's full-size chart dimensions).
- [ ] Uses the same two-series status-neutral palette RAV-002 already uses (`--color-accent`/`--color-accent-2`)
      — no green/red pairing.
- [ ] This is a compact re-rendering of already-charted data (RAV-002's own MAE pair) at run-list scale, not a new
      chart type — no other metric pair, no new computed statistic, no interactivity (no selector/toggle at this
      scale).
- [ ] A run with zero or one split (insufficient to draw a meaningful line) renders an explicit empty/placeholder
      state in that column — never a broken or misleadingly flat SVG.
- [ ] Test: rendered `runs_list.html` contains a sparkline with correct point count/values for a fixture run's
      splits; a zero/one-split run renders the placeholder state instead.

Rationale for priority: the second half of the founder's explicitly required runs-list scope, paired with
RAV-013's verdict indicator; Must because the founder named the sparkline as required, not optional — and it
reuses data RAV-012 already makes available and logic RAV-002 already computes, so it is a small increment on top
of existing capability, not new capability.
Depends on: RAV-012

### RAV-015 — Inline predicted-vs-actual chart per split on `run_detail` [Must]
**As** dashboard-web, **I want** `run_detail.html` to render each rendered split's predicted-vs-actual chart
inline, in place of today's separate-page text link, **so that** a tenant auditing a run's splits sees the chart
directly alongside that split's row instead of navigating to a separate page per split.

Acceptance criteria:
- [x] Replaces the current text link (`run_detail.html` line 115: `<a href="/runs/{{ run.id }}/splits/
      {{ split.split_index }}/points-chart">Actual vs. predicted value</a>`) with the chart rendered inline in
      that split's own row/section, calling the exact same `build_predicted_vs_actual_chart(points)` function and
      `PredictedVsActualChartData` shape `run_split_points_chart` (`routers/runs.py` line 1131) already uses — no
      second implementation of point-series geometry.
- [x] Fetches per-split points only for the same `rendered_splits` list `run_detail` already caps at
      `MAX_RENDERED_SPLITS` (`routers/runs.py` line 1230, currently 500) — this story does not introduce a new
      unbounded call pattern beyond that existing, already-accepted cap. The sequencing decision must state
      explicitly, in the ticket, how many `GET /runs/{run_id}/splits/{split_index}/points` calls one page load
      now makes (one per rendered split) and confirm that count stays bounded by that same existing cap — the
      same N+1-awareness RAV-012 applies to the runs list applies here, even though `run_detail`'s own cap already
      exists today and is not being newly invented by this story.
- [x] The existing `PredictedVsActualChartData.has_data=False` placeholder path (already defined for a split with
      no persisted/pruned points) is rendered inline exactly as it is today — never a broken/empty `<svg>`.
- [x] Chart title/axis labels/copy carry forward the exact same "actual value vs. this split's predicted value,
      test-window only" framing the existing `split_points_chart.html` page already uses, unchanged — no
      extrapolation, no forecast language.
- [x] Same status-neutral color constraints as every other chart in this backlog (no green/red pairing).
- [x] The standalone `/runs/{run_id}/splits/{split_index}/points-chart` route/page may be kept (e.g. as a
      shareable/printable single-split view) or removed — Tech Lead's call, not this story's — but if kept, it
      must render via the same shared template partial/charting call as the new inline version, never a
      diverging second copy (DRY, per `docs/implementation-plan.md` section 9).
- [x] Test: `run_detail.html` renders the correct inline chart for a fixture split's persisted points; a split
      with no persisted points (pruned or never captured) renders the placeholder, not an error.

Rationale for priority: the second founder-named gap — surfaces an already-built chart (Epic B/RAV-006–008,
confirmed shipped in production code — `build_predicted_vs_actual_chart` and `run_split_points_chart` both exist
and are wired to a real `GET .../points` endpoint, even though this backlog file's own RAV-006/007/008 checkboxes
were never marked done; flagged here for the PM/Tech Lead to reconcile, not silently corrected by this story) on
the page a tenant is already looking at, instead of a per-split page navigation. Must, per the founder's explicit
scope.
Depends on: none (RAV-006/007/008's prerequisite backend capability is already built, confirmed by direct code
read of `charting.py` and `routers/runs.py`)

**Status: DONE (Sprint 60, `docs/tickets/RAV-015.md`). Standalone points-chart route kept (Tech Lead's call,
stated in the ticket's Outcome section).**
