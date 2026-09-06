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
   the same cycle — it requires a schema change, a storage-growth sizing conversation, and a new API surface, none
   of which this backlog authorizes on its own (see RAV-006's explicit note to the Architect/Tech Lead).
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

### RAV-006 — Persist raw per-point predicted/actual values per split [Could]
**As** a future consumer of per-split detail (this visualization epic, and potentially `reporting-service` later),
**I want** `validation-service` to persist each split's raw per-point predicted and actual values (for both
`naive_last`/`model` and `naive0`, and `client_baseline` when present), **so that** a predicted-vs-actual chart
becomes possible at all — today only the seven aggregated `MetricSet` fields per baseline are stored
(`services/validation-service/src/app/models.py`'s `SplitResult` table has no such column, confirmed by reading
it), so no story downstream of this one can render a real per-point chart without it.

Acceptance criteria:
- [ ] A new, explicitly-scoped schema change (new table or JSON/array column, Tech Lead's call, not this backlog's)
      persists, per split per baseline, the aligned `(timestamp, predicted, actual)` triples the engine already
      computes in-memory during metric aggregation (`naive_first_engine`'s protocol) but currently discards after
      reducing to metrics.
- [ ] This story's acceptance explicitly requires a written storage-growth estimate (rows = tenants × runs ×
      splits × test-window-length × baselines-per-split) presented to the Architect/Tech Lead for sizing **before**
      implementation — this is per-tenant, per-run, per-split, per-point data, potentially a large multiplier on
      current row counts, and this backlog does not authorize skipping that sizing conversation.
- [ ] The change does not alter or weaken the existing leakage-aware protocol in any way — raw predictions are
      captured as a side-effect of the existing walk-forward computation, never by re-fitting or re-predicting
      outside a split's own train/test boundary.
- [ ] No existing `SplitResultResponse`/`SplitResultRecord` field changes shape or meaning — this is additive only
      (new field/endpoint, not a repurposing of `model_*`/`naive0_*`, matching the precedent VS-017 already set for
      `client_baseline` as its own separate, additive column).
- [ ] Retention/pruning policy for this new data is explicitly named (even if the answer is "none yet, revisit
      once storage growth is measured") — not left undecided in the schema itself.

Rationale for priority: this is a real, non-trivial backend capability with a genuine storage-cost tradeoff, not a
frontend-only chart story — Could, not Must/Should, until the Architect/Tech Lead confirms the storage sizing is
acceptable at expected tenant/run volumes. Explicitly sequenced as this epic's prerequisite per this backlog's own
framing note; nothing in Epic B can start before this closes.
Depends on: none (but blocks RAV-007, RAV-008)

**Status: BLOCKED, not scheduled into any sprint.** Sprint 26 (`docs/sprints/sprint-26.md`) confirmed this remains
gated on the storage-growth sizing conversation (rows = tenants × runs × splits × test-window-length ×
baselines-per-split) and a retention/pruning policy, per this story's own acceptance criteria — neither has
happened. Same treatment already given to `DBOPT-008`. Do not schedule RAV-006/RAV-007/RAV-008 until that
conversation concludes with an explicit go/no-go.

### RAV-007 — Expose per-point predicted/actual values via the existing run/split API surface [Could]
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

Rationale for priority: cannot be estimated or built before RAV-006 lands; Could, matching RAV-006's priority,
since there is no value in an API for data that doesn't exist yet.
Depends on: RAV-006

### RAV-008 — Predicted-vs-actual chart per split [Could]
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

Rationale for priority: highest-fidelity chart in this backlog but fully blocked on RAV-006/RAV-007; Could until
those close, and even then it should be re-evaluated for real tenant demand once Epic A ships and gets feedback —
building the most expensive chart first, before cheaper Epic A charts are validated with real users, would be
premature.
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
