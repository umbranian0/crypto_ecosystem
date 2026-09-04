---
status: accepted
---

# Forecast horizon summary: `horizon` is dataset-sampling-interval-relative; this feature selects among a tenant's existing completed runs, no backend change

`docs/product/backlog-forecast-horizon-summary.md` (FHS-001) asks for three decisions before any
UI/backend work starts: (a) what unit `RunRequest.horizon` is in today, confirmed against a real
dataset; (b) whether "7/15/30 days" maps onto existing `horizon` values via a documented
conversion or needs new ones most tenants' existing runs don't have; (c) what the UI shows when a
tenant has no completed run at a selected horizon. It also requires an explicit scope call:
"select among existing runs" (no backend change) vs. "this page finds/creates the right run" (a
backend change).

## (a) `horizon`'s unit today

**`horizon` is an integer count of the dataset's own sampling steps, not a fixed hour/day
constant.** Confirmed two ways:

1. `libs/naive_first_engine/src/naive_first_engine/protocol.py`'s `_metric_set` passes
   `config.horizon` straight into `metrics.mase(..., seasonal_period=horizon)` and `dm_test(...,
   horizon=horizon)` — nothing in the engine converts it from/to a time unit; it is a step count
   over whatever index the input series carries.
2. The engine's own regression fixtures make the step-vs-real-time distinction explicit:
   `tests/test_regression_1h.py` builds an hourly (`freq="h"`) index and uses `horizon=1` (one
   hour ahead); `tests/test_regression_6h.py` and `test_regression_24h.py` build the *same*
   hourly index and use `horizon=6`/`horizon=24` respectively (`_HORIZON`) — i.e. "6h"/"24h" in
   those file names is a real-time label the test author attached to the *step count*, and it
   only means 6/24 hours because the fixture index is hourly. Nothing in `naive_first_engine`
   enforces that; a series ingested at a different frequency would give `horizon=6` a different
   real-world meaning.
3. Confirmed against a real dataset: `services/ingestion-service/src/app/routers/connectors.py`'s
   only configured price connector is `BINANCE_SOURCE_NAME = "binance_price_btcusdt_1h"` — hourly.
   For every run built from that source today, `horizon` **is** hours (1 unit = 1 hour), but that
   is a fact about this one connector's sampling frequency, not a platform-wide guarantee — a
   future daily-sampled source would make the same `horizon=7` mean 7 days instead of 7 hours.

## (b) Does "7/15/30 days" map onto existing `horizon` values?

**Yes, via a documented, source-frequency-aware conversion — not a fixed platform constant.**
Because `horizon` is sampling-interval-relative (finding (a)), "N days" cannot be hardcoded as a
single integer platform-wide (e.g. "30 days always means `horizon=30`" would be wrong the moment
a non-hourly source exists). The conversion this feature uses:

```
horizon_for(days, source_sampling_interval_hours) = days * 24 / source_sampling_interval_hours
```

For the one real source today (`binance_price_btcusdt_1h`, 1-hour sampling), this resolves to
7/15/30 days → `horizon` 168/360/720. **This feature hardcodes the hourly case for its first
release**: `services/dashboard-web`'s horizon selector presents 7/15/30 *days* to the tenant and
converts to `horizon` 168/360/720 for filtering, with the conversion constant
(`HOURS_PER_DAY = 24`, `ASSUMED_SAMPLING_INTERVAL_HOURS = 1`) named and commented in code, not
buried as a magic number — the assumption is disclosed, not silently generalized. `naive_first_engine`/
`validation-service`/`libs/common` are untouched by this decision: no schema/contract field
changes, since a run's `horizon` value is already an `int` and this feature only interprets it at
render time, in `dashboard-web` alone.

**Explicitly not solved**: per-run source-frequency lookup for non-hourly sources (there are none
today). If/when a second connector at a different sampling frequency exists,
`ASSUMED_SAMPLING_INTERVAL_HOURS` must become a per-dataset lookup rather than a hardcoded `1` —
flagged here for whoever builds that connector, not solved speculatively now (YAGNI, and this
repo's own precedent of not building for an untriggered case).

## (c) No-completed-run-at-horizon empty state

**Explicit empty state, no silent fallback to a different horizon's data.** Selecting a horizon
with zero matching completed runs renders a plain "no completed runs at this horizon yet" message
with a link into the existing `/runs/new` form — never substitutes the nearest available horizon's
run, never shows a different horizon's numbers unlabeled. Per the backlog's own risk note, this is
expected to be the **common case initially** (the engine's own regression suites are all sub-day;
most tenants' existing runs are unlikely to already sit at exactly `horizon` 168/360/720) — FHS-002's
ticket must test this path as a primary case, not an edge case.

## Scope decision: select among existing runs, no backend change

**This feature is scoped to "select a horizon among a tenant's existing completed runs"
(Epic-A-style), the same shape RAV-001 chose for charting.** It does **not** find-or-create a run
at a horizon the tenant lacks. Rationale:

- `RunDetailResponse`/`SplitResultResponse` (via `GET /runs/{id}` and `GET /runs/{id}/splits`,
  already called by `run_detail` in `services/dashboard-web/src/app/routers/runs.py`) carry every
  field FHS-003/004 need — `model_*`/`naive0_*` `MetricSet`s, `dm_statistic`/`dm_pvalue`/
  `dm_verdict`, `horizon` itself. Nothing here requires a new backend field.
- `GET /runs` (gateway-api `GW-016`, proxying `validation-service`'s `VS-022`) already returns
  every run's `horizon`; filtering "runs whose `horizon` equals 168/360/720" is a client-side
  (dashboard-web) filter over an already-fetched list — **no new query parameter, no new
  aggregation endpoint**. `RunSummaryResponse` (the shared contract `runs_list` already parses)
  carries `horizon`, confirmed by `runs.py`'s existing `RunSummaryResponse` import and
  `runs_list.html`'s existing horizon column.
- Auto-recomputing/creating a run at a horizon the tenant doesn't have is explicitly out of scope
  per the backlog itself ("Explicitly out of scope" section) and per (c) above — the empty state
  points at the existing manual `/runs/new` flow instead.

**Conclusion for the sprint's dependency chain: no backend change is required for FHS-002, FHS-003,
or FHS-004.** All three stay pure `services/dashboard-web` presentation/filtering work, matching
the PM's own expectation in `docs/sprints/sprint-27.md`. `libs/naive_first_engine`, `libs/common`,
`validation-service`, and `gateway-api` are untouched by this decision and by every ticket it
gates.

## Consequence for future readers

- `services/dashboard-web`'s horizon-to-`horizon`-field conversion constant
  (`ASSUMED_SAMPLING_INTERVAL_HOURS`) is a disclosed, hourly-only assumption — the first thing to
  revisit if a non-hourly-sampled dataset source is ever added (`implementation-plan.md`'s trigger
  table has no such trigger fired today).
- If a future request asks this feature to also handle multiple sampling frequencies, or to
  auto-create a run at a missing horizon, both are scope changes requiring their own decision
  (the second explicitly re-opens the "declined as literally asked" territory `ADR-0002` already
  established for forward-looking inference requests) — neither is authorized by this ADR.
