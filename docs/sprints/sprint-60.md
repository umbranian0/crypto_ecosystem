# Sprint 60 — Epic D (Run Analysis Visualization): runs-list prominence + inline split chart

Sprint goal: by the end of this sprint, a tenant browsing `dashboard-web`'s runs list sees each run's
Naive0-comparison verdict and a compact MAE sparkline at a glance, can discover the already-shipped cross-run
trend view via a visible link, and sees every rendered split's predicted-vs-actual chart directly inline on
`run_detail` instead of following a separate per-split page link.

Backlog source: `docs/product/backlog-run-analysis-visualization.md`, Epic D (`RAV-011` through `RAV-015`),
added 2026-09-25. This file re-verifies Epic D's own cited findings against current code independently, not on
trust, per this platform's standing convention that a follow-up sprint's citations get their own PM pass — the
same discipline sprint-58/59 applied to their own backlog sources.

## Verification of the backlog's cited findings (done independently, not taken on trust)

- **`runs_list.html`, read in full**: a plain `<table>` (Run / Status / Dataset / Horizon / Created at /
  Completed at columns, lines 13–19), zero chart markup, zero references to `/runs/trend` anywhere in the
  file. Confirms Epic D's own claim exactly — no visualization, no discoverable link to the already-shipped
  trend page.
- **`run_detail.html` line 115, confirmed verbatim**: `<a href="/runs/{{ run.id }}/splits/{{
  split.split_index }}/points-chart">Actual vs. predicted value</a>` — a plain text link per split row, no
  inline chart. Confirms `RAV-015`'s target exactly.
- **`services/dashboard-web/src/app/routers/runs.py`, route line numbers re-confirmed by direct grep, not
  carried from the backlog on trust**: `runs_list` decorator/def at lines 726–727 (calls only downstream `GET
  /runs`, forwards `limit`/`offset` only if the incoming request supplied them, no local default/cap — read in
  full, lines 726–769); `runs_trend` at line 1058/1059; `run_split_points_chart` at line 1131/1132; `run_detail`
  decorator/def at lines 1183–1184, with its own existing `MAX_RENDERED_SPLITS = 500` (defined line 532, applied
  lines 1228–1230) truncation already in place before this sprint. All match the backlog's own citations exactly
  (off-by-one only between decorator line and `def` line, immaterial).
- **`services/gateway-api/src/app/routers/runs.py`, re-confirmed**: `get_splits` at line 202/203 — a pure
  pass-through (`client.get(f"/runs/{run_id}/splits")`, no reimplementation of validation-service's logic).
  `list_runs` (line 175/176) itself passes `limit: int = Query(default=20)` **with no upper-bound
  (`le=`) constraint** — worth flagging explicitly: the runs-list page has no enforced page-size ceiling
  today, independent of which `RAV-012` mechanism is chosen (see sequencing call below).
- **`services/validation-service/src/app/routers/splits.py`, re-confirmed**: `get_splits` at line 115/116
  (mirrors gateway-api's pass-through), and a second route at line 163 — `GET
  /runs/{run_id}/splits/{split_index}/points` — confirming Epic B's backend capability (`RAV-006`/`007`/`008`)
  is genuinely already live, exactly as `RAV-015`'s own note states.
- **`services/dashboard-web/src/app/charting.py`, read for its full function inventory**: `build_error_chart`,
  `build_dm_verdict_chart`, `_verdict_category`, `verdict_category_and_css_slug`, `build_headline_verdict_summary`,
  `build_trend_chart`, `compute_consistency_indicator`, and `build_predicted_vs_actual_chart` all exist exactly
  as the backlog names them — confirming every story in this epic has real, already-built logic to reuse rather
  than a name it assumes exists.
- **Backlog hygiene discrepancy, confirmed and flagged (not corrected here — not this sprint's story to fix)**:
  `RAV-006`/`007`/`008`'s acceptance-criteria checkboxes in `backlog-run-analysis-visualization.md` are still
  unchecked, but the backend capability they describe (per-point persistence, the `GET
  .../points` endpoint, `build_predicted_vs_actual_chart`) is confirmed live in production code by this pass's
  own re-read. `RAV-015`'s own text already names this for reconciliation; this file repeats the flag for
  whoever next has backlog-editing authority (Product Owner) to correct the checkboxes — out of scope for a
  Tech Lead ticket and out of scope for this PM pass to silently edit.
- **`services/gateway-api/src/app/routers/system.py`'s `GET /system/runs-summary` (`SETUP-022`), read in full
  as the one existing precedent for a genuinely aggregate/cross-entity endpoint in this platform** (as opposed
  to the many single-resource pass-through endpoints): operator-authenticated, it loops over every known tenant
  server-side and calls `validation-service`'s `GET /runs` once per tenant internally, but exposes exactly **one**
  HTTP round trip to its own caller. This is the platform's live precedent for "hide N downstream calls behind
  one caller-facing endpoint when the alternative is a caller doing N calls itself" — directly relevant to
  `RAV-012`'s sequencing call below, even though its own shape (cross-tenant counts, operator-scoped) differs
  from what `RAV-012` needs (per-tenant, per-run split detail).
- **File-overlap check, done by reading every target file in full rather than assumed from module names.**
  `RAV-011`, `RAV-012`, `RAV-013`, and `RAV-014` all touch `services/dashboard-web/src/app/templates/
  runs_list.html` and/or `services/dashboard-web/src/app/routers/runs.py`'s `runs_list` function region (lines
  726–769 today, before this sprint's edits). `RAV-013` and `RAV-014` additionally touch `charting.py`. `RAV-015`
  touches a different file region of the same `routers/runs.py` file (`run_detail`, lines 1183+) plus
  `run_detail.html` and (if it adds a compact/shared rendering helper) `charting.py` again. **Net: this sprint
  has real same-file concurrent-work risk that sprint-58's two-story, zero-overlap sprint did not** — see the
  dedicated risk section below.

## Sequencing call: RAV-012's bounding mechanism, decided here, not left open for the Tech Lead

The backlog names three candidate mechanisms without picking one and explicitly requires this sprint plan to
pick one deliberately. **Decision: mechanism (a) — a new batched summary endpoint spanning
`validation-service` (owns the data) and `gateway-api` (pass-through), accepting the current page's run IDs and
returning each run's per-split data (the same `SplitResultResponse`-shaped list `GET /runs/{run_id}/splits`
already returns, batched across the page's runs in one round trip) — not (b) a hard-capped per-page N+1, and
not (c) a precomputed field persisted on the run row.**

Rationale, weighed against this platform's actual precedents rather than defaulting to the least-work option:

- **This is not a case where N+1-with-a-cap is "honestly sufficient."** The runs list is very likely this
  platform's highest-traffic dashboard-web page (it's the landing view for "show me my runs"), and unlike a
  one-time page load, its latency cost under mechanism (b) is paid on *every* visit, forever, proportional to
  whatever cap is chosen — not a bounded one-off cost. Each of those calls is two network hops today
  (`dashboard-web` → `gateway-api` → `validation-service`), made synchronously in the existing `httpx.Client`
  pattern this router already uses; even a modest cap (e.g. 20–50, matching gateway-api's existing
  `Query(default=20)`) means 20–50 sequential downstream round trips stacked onto one page load's response
  time, indefinitely.
- **A real, live precedent for "hide N calls behind one endpoint" already exists in this exact codebase**:
  `GET /system/runs-summary` (`SETUP-022`, verified above) was built for precisely this reason — a caller-facing
  page needed cross-entity data that would otherwise require the caller to make many calls itself, and this
  platform's own engineers chose to build a small aggregate endpoint rather than accept that cost. `RAV-012`'s
  situation is structurally the same shape (many entities on one page, each needing a downstream detail call),
  just tenant-scoped rather than cross-tenant.
- **The new endpoint is a small, disciplined addition, not new architectural surface.** It follows the exact
  pass-through pattern `GET /runs/{run_id}/splits` (gateway-api `runs.py:203`, validation-service
  `splits.py:116`) already establishes — same response shape reused (`SplitResultResponse`, per `RAV-012`'s own
  AC: "never a parallel/duplicate field set"), just parameterized over a page of run IDs instead of one. Two
  small new endpoints (one per service), both following an established shape, is a modest, well-precedented
  cost against a permanent, page-load-proportional latency saving — this is the "genuinely better-designed
  answer," not gold-plating, per this sprint's own read of the "keep it simple" standing preference: simplicity
  here means the runs-list page keeps making exactly one summary-data call regardless of page size, not that
  the backend adds zero new lines of code.
- **Mechanism (c) (a precomputed field on the run row) is rejected** as real over-engineering for this scope:
  it requires a write-time sync mechanism (updating the run row every time a split completes) that doesn't
  exist today and would need its own consistency story (what happens if a split write and the run-row sync
  disagree) — meaningfully more design surface than either (a) or (b) for a page that only needs to read, not
  maintain, derived state. Not proportionate to what this epic asks for.
- **This decision does not require also capping `GET /runs`'s own `limit` parameter as part of this sprint.**
  That gap (no `le=` bound on gateway-api's `list_runs`, flagged in verification above) is real but pre-existing
  and orthogonal to `RAV-012`'s AC, which only mandates a hard cap "if (b) is chosen." Since (a) is chosen
  instead, enforcing a `limit` ceiling is a reasonable defensive addition the Tech Lead may still choose to make
  (an unbounded `limit` would still make the new batched endpoint's own request/response large), but it is not
  mandated scope here — flagged as an implementation-level judgment call, not a sprint-level requirement, so
  this sprint stays focused on Epic D's two founder-named gaps rather than quietly absorbing a third, unrelated
  hardening story.
- **Module-boundary check**: both touched services (`gateway-api`, `validation-service`) are already-live
  (triggers #5 and #3 respectively, implementation-plan.md section 6) — no trigger question. The new endpoint
  stays inside each service's own boundary and follows section 2's rule (`dashboard-web` reaches this data only
  through gateway-api's HTTP API, never validation-service's schema directly).

**Standalone `/runs/{run_id}/splits/{split_index}/points-chart` route — recommendation, not a decision, left
open per the backlog's own framing.** This sprint plan recommends **keeping** the standalone route as a
shareable/printable single-split view once `RAV-015` makes it redundant for normal in-page browsing — it costs
nothing extra to keep (the AC already requires that, if kept, it renders via the same shared template
partial/charting call as the new inline version, never a diverging second copy), and removing it would break
any already-shared/bookmarked URL for no offsetting benefit. This is a recommendation only; the backlog's own
AC explicitly leaves the final call to the Tech Lead, and this file does not override that.

## Stories in scope, in execution order

1. **RAV-011** — Visible link from `runs_list.html` to `/runs/trend`.
   - Modules touched: `services/dashboard-web` only — `templates/runs_list.html` (template-only addition, no
     new route/backend logic per the AC).
   - No dependency on any other story this sprint. Sequenced first: it is the smallest, lowest-risk change
     to `runs_list.html`, and landing it before `RAV-012`–`014`'s heavier edits to the same template/file
     minimizes the number of stories touching that file's in-flight diff at once.
   - Constraint carried into the ticket: link copy must reuse `/runs/trend`'s own existing framing (RAV-009's
     "how this model configuration's validation results have varied across runs" language) — no new,
     independently-worded copy for the same destination.

2. **RAV-012** — Bounded per-run split-summary data for the runs-list page.
   - Modules touched: `services/validation-service` (new batched endpoint, per the sequencing decision above),
     `services/gateway-api` (pass-through of the same), `libs/common` (`naive_first_common.contracts` gains
     the new endpoint's response shape as the single canonical definition, reusing `SplitResultResponse` inside
     it rather than a fourth hand-duplicated field list, per `ARCH-003`'s established convention), and
     `services/dashboard-web` (`routers/runs.py`'s `runs_list`, currently lines 726–769, calls the new endpoint
     for the page's run IDs).
   - No dependency on any other RAV story; it blocks `RAV-013` and `RAV-014`, both of which need this data —
     must land before either.
   - **Mechanism decided above: (a), a new batched endpoint. Carry this into the ticket as settled, not open.**
   - Constraint carried into the ticket: no change to `GET /runs/{run_id}/splits`'s own existing contract or
     behavior — this is additive only, per the AC.

3. **RAV-013** — Per-run verdict indicator on the runs list.
   - Modules touched: `services/dashboard-web` only — `templates/runs_list.html` (new column) and
     `routers/runs.py`'s `runs_list` (consumes `RAV-012`'s data), reusing `charting.py`'s existing
     `_verdict_category`/`verdict_category_and_css_slug`/`build_headline_verdict_summary` logic applied per run
     — no second, independently-derived verdict rule in the route or template, per the AC.
   - Depends on `RAV-012` (needs its per-run split data). Sequenced immediately after it.
   - Constraint carried into the ticket: four status-neutral categories/colors only (`--color-status-completed-
     text` "better", `--color-status-failed-text` "worse", `--color-status-running-text` "no significant
     difference", `--color-text-muted` "undefined") — never green/red, matching `style.css`'s documented
     constraint; copy reads only as benchmark-comparison outcome, never "good/bad to trade" or any buy/sell/
     signal word (CLAUDE.md positioning rule, binding on this story specifically since it is the new label most
     likely to be misread as a trading signal if worded carelessly); a zero-split run shows a plain "no results
     yet" state, never a fabricated verdict.

4. **RAV-014** — Per-run compact error sparkline on the runs list.
   - Modules touched: `services/dashboard-web` only — `templates/runs_list.html` (new column),
     `routers/runs.py`'s `runs_list` (consumes `RAV-012`'s data), and `charting.py` (a new compact-rendering
     function is permitted, but must build on the same `Bar`/`SplitBars` data shapes `build_error_chart` already
     uses for `RAV-002` — no second hand-rolled MAE-series computation, per the AC).
   - Depends on `RAV-012`. No dependency on `RAV-013`, but sequenced after it (both edit `runs_list.html`'s row
     markup and `runs_list`'s same function region — doing them as two back-to-back, non-overlapping-in-time
     edits rather than parallel dispatch avoids a same-file merge conflict; see risk section below).
   - Constraint carried into the ticket: server-rendered inline SVG only, sized for a table cell, distinct
     dimensions from `RAV-002`'s full-size chart; same `--color-accent`/`--color-accent-2` two-series palette,
     no green/red; a run with zero or one split renders an explicit placeholder, never a broken or misleadingly
     flat SVG.

5. **RAV-015** — Inline predicted-vs-actual chart per split on `run_detail`.
   - Modules touched: `services/dashboard-web` only — `templates/run_detail.html` (line 115's link replaced
     with inline chart markup) and `routers/runs.py`'s `run_detail` (lines 1183+, a distinct function region
     from `runs_list`), reusing the exact same `build_predicted_vs_actual_chart(points)` function and
     `PredictedVsActualChartData` shape `run_split_points_chart` already uses (no second implementation of
     point-series geometry, per the AC).
   - No dependency on any other story this sprint (Epic B's prerequisite backend capability is already live,
     confirmed above). Sequenced last: it touches a different file region (`run_detail`, not `runs_list`) and a
     different template, so it carries no ordering constraint relative to `RAV-011`–`014` — placed last here
     purely because it is the second, independent founder-named gap, not because anything blocks it.
   - Constraint carried into the ticket: fetches per-split points only for `run_detail`'s existing
     `rendered_splits` list (already capped at `MAX_RENDERED_SPLITS = 500`, line 532/1230) — the ticket must
     state explicitly how many `GET .../points` calls one page load now makes (one per rendered split) and
     confirm that count stays bounded by the existing cap, the same N+1-awareness `RAV-012` applies to the runs
     list, even though this cap already exists and is not newly invented here. The existing
     `PredictedVsActualChartData.has_data=False` placeholder path must render inline exactly as it does today —
     never a broken/empty `<svg>`. Standalone route recommendation: see above (kept, Tech Lead's final call).

## Module/dependency note for the Tech Lead (implementation-plan.md sections 2 and 6)

All five stories touch only already-live modules — `services/dashboard-web` (trigger #8), `services/gateway-api`
(trigger #5), and `services/validation-service` (trigger #3) all fired long ago; `RAV-012` additionally touches
`libs/common` (trigger #2, already live, shared schemas). No new service, no new `libs/*` package, no touch to
`libs/sdk` (trigger #9), a new ingestion connector (trigger #10), or `services/economic-service` (trigger #11)
— none of those triggers have fired, consistent with this epic's own explicit out-of-scope statement. Per
section 2's module boundary rule: `dashboard-web` reaches `RAV-012`'s new batched data only through
`gateway-api`'s HTTP API, never `validation-service`'s schema directly; `gateway-api`'s new endpoint is a
pass-through only, never a reimplementation of `validation-service`'s own aggregation logic (CLAUDE.md's "no
service imports another service's code" rule).

## Stories explicitly deferred

- **ADMIN-005** (self-serve API key rotation, Epic C of `docs/product/backlog-trust-and-admin-ops.md`) —
  still deferred, not dropped. Sprint 59's own "Next" section already records why it isn't scheduled: the
  founder redirected Sprint 60 to this new visualization work before `ADMIN-005` was picked up. Its
  lockout-guard design risk and the `/grilling`-before-implementation recommendation sprint-58/59 already
  flagged are unchanged and not re-litigated here — see `docs/sprints/sprint-59.md`'s "Next" section for the
  full standing rationale.
- No `RAV-*` story is deferred out of this sprint — Epic D is exactly five stories (`RAV-011`–`RAV-015`), all
  five are in scope above. Epic B (`RAV-006`/`007`/`008`) is not "deferred" in the usual sense — its backend
  capability is already shipped (see verification above); only its backlog checkboxes remain stale, a
  Product-Owner-level hygiene fix, not sprint scope. New chart types and a links-only minimal fix are not
  deferred — they are explicitly out of scope per the founder's own instruction, not a "maybe later."

## File-overlap / concurrent-work risk

- **Real overlap exists this sprint, unlike sprint-58's zero-overlap two-story sprint.**
  `services/dashboard-web/src/app/templates/runs_list.html` is touched by `RAV-011`, `RAV-013`, and `RAV-014`
  (and read, unmodified, by `RAV-012`'s data-availability change). `services/dashboard-web/src/app/
  routers/runs.py`'s `runs_list` function (lines 726–769 today) is touched by `RAV-011`, `RAV-012`, `RAV-013`,
  and `RAV-014`. `services/dashboard-web/src/app/charting.py` is touched by `RAV-013` (reads only, reuses
  existing functions) and `RAV-014` (adds a new compact-rendering function).
  **Recommendation: these four stories should not be dispatched to parallel dev tracks — sequence them as
  serial edits to the same file/function region in the execution order above**, not because of a data
  dependency in every case (`RAV-011` has none), but to avoid simultaneous in-flight diffs to the same
  function/template colliding. `RAV-015` is the one story this sprint safe to run as a fully independent,
  parallel track — it touches a different function (`run_detail`, lines 1183+) and a different template
  (`run_detail.html`), with only an incidental, non-conflicting touch to `charting.py` if a new shared helper
  is added there (additive, not editing `RAV-013`/`014`'s new code).
- `libs/common/src/naive_first_common/contracts.py` is touched by `RAV-012` only this sprint (new response
  shape) — no other in-flight or immediately-next-sprint story is known to touch it.
- No story this sprint touches `naive_first_engine`, any migration, or any other service's schema — confirmed
  by the verification above; this keeps the sprint's blast radius entirely inside `dashboard-web` +
  a small, additive `gateway-api`/`validation-service`/`libs/common` surface for `RAV-012` alone.

## Definition of done for this sprint

- `RAV-011` through `RAV-015`'s acceptance criteria (verbatim from
  `docs/product/backlog-run-analysis-visualization.md`) are checked off in their respective tickets.
- Required tests, specifically: `RAV-011` — rendered `runs_list.html` contains a link to `/runs/trend` when
  `runs` is non-empty. `RAV-012` — a fixture page of N runs results in a provably bounded number of downstream
  HTTP calls (one batched call, not O(N)), asserted in a test, not only a docstring claim. `RAV-013` — correct
  verdict category/label for a fixture set of runs including a zero-split run. `RAV-014` — correct sparkline
  point count/values for a fixture run's splits, and the explicit placeholder for a zero/one-split run.
  `RAV-015` — correct inline chart for a fixture split's persisted points, and the placeholder (not an error)
  for a split with no persisted/pruned points.
- Positioning check (CLAUDE.md) explicitly re-verified in review for every new visual/label added this sprint:
  no price-prediction or trading-signal framing anywhere in `RAV-013`'s verdict indicator or any other new
  copy; naive-first stays the default benchmark in every new chart/label; directional accuracy/F1 (where
  touched) keep their real statistical names, never hit-rate/win-rate language; no green/red bull-bear color
  pairing anywhere in any new element; `RAV-013`'s verdict indicator specifically reads as benchmark-comparison-
  outcome only, never "good/bad to trade" — reviewed against the actual rendered HTML, not just the ticket
  text.
- ADR-0006 compliance explicitly re-verified: every new chart element this sprint (verdict indicator if
  rendered as SVG, sparkline, inline predicted-vs-actual chart) is server-rendered inline SVG only — no new
  client-side JS charting library, no Python plotting library, all built through `charting.py` as the single
  source of chart-building logic (no diverging second implementation of point-series geometry or MAE-series
  computation anywhere).
- `services/dashboard-web/README.md`, `services/gateway-api/README.md`, and
  `services/validation-service/README.md` updated to record the new batched endpoint (`RAV-012`), the new
  runs-list columns (`RAV-013`/`014`), the new trend-page link (`RAV-011`), and the inline chart replacing the
  per-split link (`RAV-015`) as shipped, per this repo's README-current standing convention.
- `libs/common/README.md` (or its contract-listing section) updated to record the new response shape
  `RAV-012` adds to `naive_first_common.contracts`.
- `docs/product/backlog-run-analysis-visualization.md`'s `RAV-011`–`RAV-015` entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket files. (The `RAV-006`/`007`/`008` stale-checkbox
  discrepancy flagged above is a separate Product Owner action, not blocking this sprint's own sign-off.)
- `docs/tickets/README.md` gets a new Sprint 60 section (Tech Lead updates this when tickets are
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- **QA gate (mandatory, per this platform's standing rule): the Tech Lead raises the `qa` agent
  (`/qa-validation`) after all five tickets are Tech-Lead-verified done, before sign-off.** QA scope
  specifically, independently verifies, against the real `naive-first-*` Docker containers (not host-run
  scripts, which hit a stale local SQLite copy per this project's known topology gotcha, and not accepted from
  dev/Tech-Lead self-report alone):
  - `runs_list.html` renders correctly for runs with zero splits, one split, and many splits — no error, no
    misleading verdict (a zero-split run must show "no results yet," never a fabricated category), for both the
    verdict indicator (`RAV-013`) and the sparkline (`RAV-014`).
  - The inline predicted-vs-actual chart on `run_detail` (`RAV-015`) does not blow up page weight or load time
    for a many-split run — measured against a real run with a large split count (up to `MAX_RENDERED_SPLITS`),
    not just a small fixture.
  - No new label added this sprint violates positioning rules — re-checked against the real rendered pages,
    grepping for prediction/forecast/signal/recommend/hit-rate/win-rate language and for any green/red color
    pairing in the new markup.
  - `RAV-012`'s batched endpoint is confirmed to keep the runs-list page's downstream call count bounded
    against the real stack (not just the unit-test fixture) — e.g. by observing request counts/logs while
    loading a runs-list page with a realistic number of runs.

## Next (explicitly not this sprint, roadmap note for continuing this backlog)

With `RAV-011`–`RAV-015` shipped, Epic D (and this backlog's entire scoped set of stories, Epic A through D) is
complete — `backlog-run-analysis-visualization.md` has no remaining open story as of this sprint's completion,
modulo the `RAV-006`/`007`/`008` checkbox-hygiene item flagged above, which is a Product Owner correction, not
new work. The next PM pass, whenever it picks up a new sprint, should: (1) confirm with the Product Owner
whether that checkbox correction has been made, and (2) re-open `docs/sprints/sprint-59.md`'s "Next" section for
`ADMIN-005` (self-serve API key rotation, Epic C of `backlog-trust-and-admin-ops.md`) as the standing deferred
candidate, still carrying its own flagged lockout-guard risk and the recommendation for a `/grilling` pass on
the mint-then-confirm-then-revoke flow before implementation starts — unless the requester redirects scope
again, that discipline should not be skipped when `ADMIN-005` is finally scheduled. This sprint's own PM pass
re-verified all of Epic D's citations against then-current code before handing off to the Tech Lead, same
discipline sprint-58/59 already established, and the next sprint's PM pass should do the same rather than carry
this file's findings forward on trust.
