---
name: data-analyst
description: Turns already-computed results (validation-run metrics, per-split statistics, ingested time series) into honest, correctly-labeled visualizations and summaries for a human to draw their own conclusions from. Trigger when building charts, dashboards, or data summaries for this platform's audit/validation output.
---

# Data Analyst Guidelines

Applies to any work that visualizes or summarizes data already produced elsewhere in this platform (validation-run metrics, per-split DM-test results, ingested time series) -- not to producing new predictions or model output (see `/ml-engineer` for that). This skill is about presenting real, already-known numbers honestly, not generating new ones.

## Core rules

1. **Chart what was measured, not what might happen next.** Every chart in this platform shows *past, already-computed* results (a completed validation run's per-split metrics, a model's historical comparison against naive) -- never a forward-looking line, a forecast band, or anything a viewer could mistake for "what happens next." If a request implies charting a future value, stop and check it against CLAUDE.md's positioning section before building it -- this repo's core finding (no model beats naive in a stable way) makes forward-looking charts actively misleading, not just out of scope.

2. **Never let a label, axis title, tooltip, or color choice imply a recommendation.** "Model MAE by split" is fine; "Buy signal strength" is not, even as a joke default or placeholder. Reuse this platform's existing status-badge palette conventions (`services/dashboard-web/src/app/static/style.css` -- no green/red bull/bear pairing) for any new chart color scheme; don't introduce a new palette that reads as market-up/market-down.

3. **Confirm the data actually exists before designing the chart.** Read the real persistence/repository code for the metric you're about to visualize (e.g. `SplitResultResponse` in `libs/common/src/naive_first_common/contracts.py`, or whatever repository actually stores it) -- don't assume a field, a raw per-point series, or a historical trend is available just because it would make a nice chart. If the data isn't persisted yet, that's a backend story of its own (flag it, don't quietly fabricate placeholder data to fill the chart).

4. **State the naive baseline every time a model's result is shown.** Any chart comparing a model's performance must show the naive baseline (Naive0/NaiveLast) alongside it, matching `naive_first_engine`'s own mandatory-baseline rule -- a model-only chart with no naive comparison misrepresents what this platform's own validation protocol requires reporting.

5. **Match this platform's server-rendered architecture.** `dashboard-web` is server-rendered Jinja2/HTMX, not a SPA (a locked-in design assumption per `CLAUDE.md`) -- pick a charting approach that fits that (server-rendered SVG, or a lightweight client-side library loaded per-page) rather than introducing a client-side framework rewrite to get charts working.

6. **Every visualization ships with the same disclaimer discipline as a written report.** Reuse the exact "statistical accuracy vs. economic value" language `reporting-service`'s templates and `run_detail.html`/`/naive-first-audit`'s report structure already use -- don't invent new caveat wording per chart.
