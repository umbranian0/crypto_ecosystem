# Backlog — Forecast Horizon Summary (dashboard-web)

Source: `CLAUDE.md` (core finding, non-negotiable positioning; naive-first-as-default-baseline rule),
`docs/adr/0002-declined-automated-trading-product.md`, `docs/product/backlog-run-analysis-visualization.md`
(Epic A/B split — what data actually exists today, RAV-001's server-rendered-SVG decision), `docs/sprints/sprint-26.md`,
`libs/common/src/naive_first_common/contracts.py` (`RunRequest`/`RunDetailResponse`/`SplitResultResponse`),
`libs/naive_first_engine/src/naive_first_engine/protocol.py`, `services/validation-service/src/app/models.py`
and `repositories/interfaces.py`, `services/dashboard-web/src/app/routers/runs.py` (`run_detail`, DASH-004/RAV-002/RAV-003).

## The request, as literally asked, and why it needed rephrasing

The request was: let a user pick a horizon (7/15/30 days) and see a summary of "what the ML prediction is" for
that horizon, exportable to hand to an end user. Taken literally — "the ML prediction" as a forward-looking
number for a future date — this is **not buildable on what exists today, and not something this platform should
build even if it were**, for two separate reasons:

1. **No forward-looking inference capability exists anywhere in this codebase.** `naive_first_engine` performs
   rolling-origin *walk-forward validation on historical data* (train fold → purge gap → test fold, repeated).
   It scores a model's *already-computed* predictions on *already-known* historical outcomes; it does not run a
   trained model forward against unseen future dates. `validation-service` persists only aggregated per-split
   `MetricSet` values (MAE/RMSE/sMAPE/MASE/DA/F1/OOS-R², per baseline, per split) plus the DM statistic/p-value/
   verdict — never a raw predicted value, past or future (`docs/product/backlog-run-analysis-visualization.md`
   finding #2 already established this for historical per-point values; the future-looking case is stronger
   still, since no component even computes it). Building "the model's prediction for the next 7 days" would mean
   standing up a new live-inference service — a different subsystem than anything in `implementation-plan.md`'s
   trigger table, with its own trigger condition that has not fired.
2. **Even if that inference capability existed, presenting a single model number as "the ML prediction" violates
   CLAUDE.md's core finding directly.** No model beat Naive0 in a stable, significant way at any tested horizon;
   best directional accuracy was 52.51%, barely above chance. A screen captioned "the prediction" that a tenant
   copies and hands to an end user is exactly the trading-signal product ADR-0002 already declined, restated with
   a horizon picker.

**Resolution**: this backlog reframes the request as its closest compliant equivalent — a **per-horizon
validation-evidence summary**, built entirely from data a completed run already has. It shows the naive-first
baseline's backtested performance and the candidate model's backtested performance *side by side*, for a chosen
horizon, with the DM verdict displayed immediately next to both numbers, framed as "how this model has performed
historically" — never as a forecast for a future date. The exportable text is a *validation summary*, not a
"prediction to hand to an end user." Anyone who wants an actual forward-looking number is told, in the copy
itself, that this platform does not produce one and why (the core finding). This is the same treatment
`backlog-run-analysis-visualization.md`'s framing note gave the "predict to buy or sell" request — declined as
literally asked, honored as the workable, honest version of the underlying need (a tenant wants to know: is
this model worth trusting at this horizon?).

## Key findings from reading the current code (binds scope below)

1. **`horizon` is a fixed, run-level config field, not a per-view selector.** `RunRequest.horizon` (an `int`,
   validated `ge=1`) is set once at `POST /runs/new` submission time and stored on the run; `RunDetailResponse`
   and `SplitResultRecord` both carry it back as a single fixed value for that run's whole lifetime. There is no
   concept of "one run, multiple horizons" anywhere in `naive_first_engine`, `validation-service`, or
   `dashboard-web` today — a horizon change means a different run. A UI horizon selector of "7/15/30 days"
   therefore cannot mean "recompute this run at a different horizon"; it can only mean **"switch which existing
   run(s) at that horizon this summary is built from"** (FHS-001 below), which requires the tenant to already
   have completed runs at each of those horizon values, or requires this feature to trigger new runs — both
   consequences a story below must make explicit, not leave implicit.
2. **Horizon units are ambiguous today and must be resolved before this ships.** `RunRequest.horizon` has no
   documented unit; the thesis and `naive_first_engine`'s regression suites (`test_regression_1h.py`,
   `test_regression_6h.py`, `test_regression_24h.py`) are all sub-day (1h/6h/24h), while this request asks for
   7/15/30 **days**. Whether `horizon` is hours (making "7 days" = 168) or already day-granularity depends on
   the dataset's own sampling frequency, which is per-dataset, not fixed platform-wide. This is a real open
   question for the Tech Lead/Architect, not a detail to guess at in a story (FHS-001 flags it explicitly).
3. **All data this feature needs, for a run that already exists, is already fetched by `run_detail`.**
   `SplitResultResponse` carries `model_*`/`naive0_*` `MetricSet`s and `dm_statistic`/`dm_pvalue`/`dm_verdict`
   per split; `run_detail` (`services/dashboard-web/src/app/routers/runs.py`) already fetches the full splits
   list via `GET /runs/{id}/splits`. Rendering a "per-horizon summary" for a **single existing run** is pure
   dashboard-web presentation work, no backend change, same as Epic A (RAV-002/003). It only becomes a backend
   story once the feature needs to compare *across* runs at different horizons (FHS-002) or needs raw per-point
   values (out of scope — same Epic B gap RAV already flagged).
4. **No charting/export dependency gap.** `app/charting.py` (RAV-001's server-rendered-SVG decision,
   `docs/adr/0006-...`) already exists; a shareable text summary needs no charting at all, just a text/HTML
   partial — no new frontend dependency, matching RAV-001's "zero new dependency" precedent.

## Framing decision (binding on every story below)

Every story renders **naive-first baseline value + candidate-model value + DM verdict**, always together, for
the chosen horizon — never the model number alone. Copy vocabulary is restricted to "backtested performance,"
"validation result," "historical benchmark comparison"; the words "prediction," "forecast," "signal," "target,"
or "recommendation" are not used anywhere in this feature's UI or exported text, matching `run_detail.html`'s
existing docstring vocabulary (see `runs.py` DASH-004 note). Every exported/shareable summary carries a fixed
caveat sentence stating the core finding in plain language (no ML model has beaten the naive baseline in a
stable, significant way — see FHS-003's exact acceptance criterion) and is not a forecast of future performance.

## Stories

### FHS-001 — Resolve horizon-unit and cross-run-selection design questions [Must, blocking] — DONE (Sprint 27)

**Status: DONE (Sprint 27, `docs/tickets/FHS-001.md`, `docs/adr/0007-forecast-horizon-summary-unit-and-scope.md`).**

As the Tech Lead, I need `horizon`'s unit and this feature's cross-run selection model decided before any UI or
backend work starts, because both are ambiguous in the code today and every other story in this backlog depends
on the answer.

Acceptance criteria:
- Written decision (ADR or dated README section in `services/dashboard-web/README.md`) answering: (a) is
  `horizon` hours, days, or dataset-sampling-interval-relative today, confirmed against at least one real
  dataset's ingestion frequency; (b) does "7/15/30 days" map onto existing `horizon` values via a documented
  conversion, or does it require new horizon values most tenants' existing runs don't have; (c) when a tenant
  has no completed run at a selected horizon, what the UI shows (empty state with a "submit a run at this
  horizon" link into the existing `/runs/new` form vs. some other treatment) — no silent fallback to a
  different horizon's data.
- Explicitly states whether this feature is scoped to "select a horizon among a tenant's existing completed
  runs" (no backend change, Epic-A-style) or "select a horizon and this page finds/creates the right run"
  (backend change) — this decision gates FHS-002/003 the same way RAV-001 gated RAV-002/003.
- No chart/code is written until this closes.

### FHS-002 — Horizon selector on the run-list or a new "horizon summary" view [Must] — DONE (Sprint 27)

**Status: DONE (Sprint 27, `docs/tickets/FHS-002.md`).** Tech-Lead-reviewed: new `/runs/horizon-summary`
page, no new backend call beyond `GET /runs`, empty state links to `/runs/new`, banned-word grep test
passes.

As a tenant, I want to pick a horizon (7/15/30 days, or whatever FHS-001 resolves those to) and see which of my
completed runs match it, so I can get to a validation summary for the horizon I care about without hunting
through `/runs`.

Depends on: FHS-001.

Acceptance criteria:
- A horizon selector (7/15/30, each mapped per FHS-001's resolved unit) is added to `/runs` or a new
  `/runs/horizon-summary` page (decision left to the Tech Lead's ticket breakdown, consistent with this
  backlog's own "don't over-specify UI placement" precedent from RAV-002/003).
- Selecting a horizon lists only the tenant's completed runs whose `horizon` matches (using FHS-001's
  conversion), most recent first; matches `runs_list.html`'s existing `created_at DESC` convention.
- Zero matching runs renders an explicit empty state with a link to `/runs/new` (no silent empty table).
- No new backend/gateway-api/validation-service call beyond the existing `GET /runs` (already proxied) unless
  FHS-001 decided this page needs cross-run aggregation the existing list endpoint can't do — if so, flag back
  to PM before building rather than silently adding a new endpoint here.

### FHS-003 — Per-horizon validation summary panel on run detail [Must] — DONE (Sprint 27)

**Status: DONE (Sprint 27, `docs/tickets/FHS-003.md`).** Tech-Lead-reviewed: new
`_forecast_horizon_summary_panel.html` partial, reuses `UNDEFINED_VERDICT_CATEGORY`/RAV-003's four
verdict colors, `None`-DM fixture renders its own category, banned-word grep test passes.

As a tenant who has selected a run at a given horizon, I want to see the naive-first baseline's backtested
performance and the candidate model's backtested performance side by side for that horizon, with the DM verdict
immediately visible, so I understand whether the model's numbers are statistically meaningful before I act on
them.

Depends on: FHS-001, FHS-002 (reachable from the horizon list) — but is independently buildable/testable against
a single `run_id` the same way `run_detail` already is.

Acceptance criteria:
- Renders, per split (or aggregated across the run's splits — Tech Lead's call, consistent with existing
  per-split table granularity): `model_mae`/`naive0_mae` (and the run's other already-persisted metrics) next to
  each other, plus `dm_verdict` and `dm_pvalue`, using only `SplitResultResponse` fields already fetched by
  `run_detail` — no new backend call.
- A `dm_verdict` of `"no significant difference"` or a `None` DM value is rendered as its own explicit category
  (never dropped, never coerced into "better"/"worse"), matching RAV-003's existing null-handling precedent.
- Panel copy uses only "backtested performance"/"validation result"/"benchmark comparison" vocabulary; the
  words "prediction," "forecast," "signal," "target," and "recommendation" do not appear anywhere in the panel
  or its templates — grep-checked in the story's own test, same discipline as Sprint 26's DoD.
- No green/red bull/bear color pairing (existing `style.css` constraint, carried over unchanged).
- Zero-split runs render the existing "no results yet" state, not a broken/empty panel.

### FHS-004 — Exportable/shareable summary text with the honesty caveat [Must] — DONE (Sprint 27)

**Status: DONE (Sprint 27, `docs/tickets/FHS-004.md`).** Tech-Lead-reviewed: `build_shareable_summary_text`
is a pure function reusing FHS-003's already-fetched per-split data; the caveat sentence is appended verbatim
and covered by an exact-string-match regression test; the `<textarea>` is `readonly` with no UI path able to
submit a modified copy back; no new storage/persistence introduced; banned-word scan (with `{% include %}`
statements stripped) passes with the caveat's own negated "forecast" usage as the sole exception.

As a tenant, I want to copy a short, shareable text summary of a run's per-horizon validation result — including
the required caveat language — so I can hand something to an end user without that person mistaking a backtested
metric for a guaranteed outcome.

Depends on: FHS-003 (uses the same data the panel renders).

Acceptance criteria:
- A "copy summary" affordance (plain-text `<textarea>`/copy-to-clipboard HTMX partial — no new JS framework
  dependency, consistent with RAV-001's zero-new-dependency precedent) renders a fixed-format text block
  containing: dataset/run identifier, horizon (in the user-facing unit FHS-001 resolved), naive-first baseline
  metric(s), candidate-model metric(s), DM verdict and p-value, and this exact fixed caveat sentence (wording
  finalized by whoever owns product copy, but must preserve this meaning): *"This is a backtested validation
  result, not a forecast of future performance. Under this platform's own published research, no machine
  learning model has beaten a naive statistical baseline in a stable, significant way at any tested horizon —
  treat any deviation shown here as unproven until independently reconfirmed."*
- The caveat sentence is not editable/removable from the copied text through any UI path in this story.
- Unit/integration test asserts the exported text contains both the naive and model metric, the DM verdict, and
  the caveat sentence verbatim (or a documented equivalent) — regression-proofing the honesty requirement itself,
  not just the feature's happy path.
- No server-side persistence of the exported text is introduced by this story (pure render-and-copy) unless a
  later story explicitly asks for share-link persistence — out of scope here.

## Explicitly out of scope for this backlog

- Any live/forward-looking inference service that would produce an actual "prediction for the next N days" —
  this is a distinct, untriggered subsystem (no build-order trigger in `implementation-plan.md` has fired for
  it) and is not something this backlog proposes standing up. If a future request pushes for this again, it
  should be evaluated the same way ADR-0002 evaluated the buy/sell request, not treated as a small extension of
  FHS-002/003/004.
- Cross-run trend charts across horizons (that is RAV-009/010's territory, `backlog-run-analysis-visualization.md`,
  currently deferred).
- Raw per-point predicted/actual value display at any horizon — blocked on the same Epic B persistence gap RAV's
  backlog already flagged; not reopened here.
- Auto-recomputing/re-running a validation at a horizon the tenant doesn't already have a completed run for —
  FHS-002's empty state links to the existing manual `/runs/new` flow instead.

## Sequencing note

FHS-001 is a hard blocking decision story, same role RAV-001 played for RAV-002/003 — nothing else here should
be estimated or ticketed until it closes. FHS-002 and FHS-003 are independently reachable (FHS-003 can be built
and tested against a known `run_id` without FHS-002's selector existing yet) but FHS-004 strictly depends on
FHS-003's rendered data shape. Not sequenced into a sprint yet — this is backlog only, pending PM sequencing.
