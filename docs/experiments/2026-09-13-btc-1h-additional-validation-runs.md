# BTC/USDT 1h — Additional Naive-First Validation Runs (2026-09-13, follow-up batch)

Source: same house style and sources as the first batch (`docs/experiments/2026-09-13-btc-1h-multi-horizon-validation.md`,
`CLAUDE.md` core finding, ADR-0007 / FHS-002's `_HORIZON_TO_DAY_LABEL` horizon-mapping convention,
`services/validation-service/src/app/routers/runs.py`'s RSS-004 500-split cap, `run_new.html`'s Naive0
raw-price-levels tooltip). This is a **follow-up batch**, not an edit of the first file — read that file
first for full dataset/method background; this document only covers what's new here.

## What this is, and what it is not

Five more **naive-first validation runs** against the same tenant-owned dataset
(`binance_price_btcusdt_1h`), exploring two dimensions the first batch did not: (1) how the
`purge_gap_hours` choice affects the DM verdict pattern at a fixed horizon, and (2) short, sub-daily
horizons (1h and 6h ahead) instead of only the day-scale horizons (168/360/720h) used previously.
`GET /ingestion/datasets` was checked before designing this batch — this tenant still has only the one
ingested source (`binance_price_btcusdt_1h`, 79,418 rows), so no non-price comparison (on-chain,
sentiment) was possible this round. As with the first batch, these are **not** forecasts, predictions,
or trading signals — consistent with `run_new.html`'s own copy ("does not generate a prediction, forecast,
or trading signal") and CLAUDE.md's core finding that no model has been shown to beat naive-first in a
stable, significant way.

## Dataset

Same as the first batch: `binance_price_btcusdt_1h`, 79,418 rows, 2017-08-17T04:00:00Z to
2026-09-13T13:00:00Z, raw close price level (no field override).

## Run configs

All five runs use the same `train_window=2,000` / `test_window=500` / `step=1,000` "tight" shape as the
first batch's `btc-1h-h168-tight` run, so `purge_gap_hours` and `horizon` are the only variables changed
per row — deliberate, to isolate their effect rather than mixing window-size changes in too. Split counts
were computed up front with `generate_splits`'s own formula
(`floor((rows - train_window - purge_gap_hours - test_window) / step) + 1`); at this row count and
step size, every purge-gap/horizon value tried here still lands on 77 splits, well under the RSS-004
500-split cap.

**Purge-gap sweep** (horizon fixed at 168h/7d — the first batch's `btc-1h-h168-tight` run used
`purge_gap_hours=168`, i.e. gap equal to horizon; these three rows bracket that on both sides):

| Run | Horizon | purge_gap_hours | train_window | test_window | step | Computed splits | Run ID |
|---|---|---|---|---|---|---|---|
| btc-1h-h168-gap0   | 168 | 0   | 2,000 | 500 | 1,000 | 77 | `349cb25411f042fcb4349cfc91ab0c93` |
| btc-1h-h168-gap84  | 168 | 84  | 2,000 | 500 | 1,000 | 77 | `a7af36a466ab468f92c4732cc7d9ebca` |
| btc-1h-h168-gap672 | 168 | 672 | 2,000 | 500 | 1,000 | 77 | `4ef185d67b104b0b8ee5b8db80e3f8e4` |

**Short-horizon runs** (`purge_gap_hours` set equal to horizon, same convention as the first batch, so
the gap always fully covers the forecast horizon between train and test folds):

| Run | Horizon | purge_gap_hours | train_window | test_window | step | Computed splits | Run ID |
|---|---|---|---|---|---|---|---|
| btc-1h-h1-tight | 1 (1h ahead) | 1 | 2,000 | 500 | 1,000 | 77 | `b886db8235dc42bcb1261b54a6a96bb9` |
| btc-1h-h6-tight | 6 (6h ahead) | 6 | 2,000 | 500 | 1,000 | 77 | `92f3c7917714480fb7162ed8b4b84084` |

All five were submitted via `POST /runs` and ran synchronously to `status: "completed"`; no run failed or
hit the 422 split-count guardrail.

## Results summary

Same schema as the first batch: model columns are `naive_last`'s metrics; `naive0_*` is the literal
predict-zero baseline. DM verdict is `naive_last` vs `naive0`, per split, counted across all 77 splits in
each run.

| Run | Splits | Mean model (NaiveLast) MAE | Mean Naive0 MAE | Mean model RMSE | Mean Naive0 RMSE | DM verdict breakdown |
|---|---|---|---|---|---|---|
| btc-1h-h168-gap0   | 77 | 2,944.00 | 39,229.91 | 3,442.84 | 39,299.47 | better: 77 |
| btc-1h-h168-gap84  | 77 | 3,493.24 | 39,360.05 | 3,894.56 | 39,422.67 | better: 77 |
| btc-1h-h168-gap672 | 77 | 5,782.64 | 39,765.83 | 6,127.29 | 39,824.08 | better: 77 |
| btc-1h-h1-tight    | 77 | 2,952.24 | 39,231.80 | 3,449.15 | 39,301.30 | better: 77 |
| btc-1h-h6-tight    | 77 | 2,991.71 | 39,241.24 | 3,479.81 | 39,310.50 | better: 77 |

## What this batch shows (and doesn't)

- **The DM verdict pattern is unchanged across every purge-gap value tried.** `naive_last` beat `naive0`
  on all 77/77 splits at `purge_gap_hours` = 0, 84, and 672 (versus 76/1 "no sig. diff" at gap=168 in the
  first batch) — the gap choice did not flip, or meaningfully soften, the verdict pattern at this horizon.
  What it did move is the error magnitude: mean model MAE rose monotonically with gap size (2,944 → 3,493
  → 5,783 as gap went 0 → 84 → 672), which is the mechanical effect of a wider purge window pushing the
  test fold further from the most recent training observation on a trending, non-stationary price series —
  not evidence about gap "correctness."
- **Shrinking the horizon to 1h or 6h did not change the verdict pattern either**, and barely moved the
  error magnitude relative to the day-scale runs (mean model MAE ~2,950–2,990 for h1/h6 versus ~2,944–7,524
  across the first batch's 168–720h runs). On raw price levels, `naive_last`'s "predict next = last
  observed" mechanically tracks the series closely regardless of horizon length, so this comparison mostly
  confirms that the raw-price-level artifact described below dominates at every horizon tried so far, short
  or long — it is not evidence that short-horizon prediction is any easier or harder than long-horizon here.
- **No non-price dataset was available to compare against.** `GET /ingestion/datasets` for this tenant
  returned only `binance_price_btcusdt_1h` at the time this batch was run — the "compare against another
  ingested source" dimension mentioned as a candidate for this batch could not be exercised and is deferred
  to whenever a second source (on-chain, sentiment) is actually ingested for this tenant.

## How to read this

- **These are backtested validation results, not forecasts.** Every number above comes from
  rolling-origin walk-forward validation on historical data already in the dataset — a train fold, a purge
  gap, then a scored test fold, repeated across the series. Nothing here predicts a future BTC price, and
  no run configuration used here or elsewhere on this platform produces one.
- **Naive0 losing near-trivially here is the same known, disclosed raw-price-levels artifact flagged in
  the first batch — not a new finding.** `run_new.html`'s own field tooltip already discloses this: Naive0
  predicts a flat `0` for every test point, which is nonsensically wrong by construction on raw,
  non-stationary price levels running in the tens of thousands of dollars. NaiveLast beating Naive0 by an
  order of magnitude in every run above, at every purge gap and every horizon tried, reflects that same
  mismatch — not predictive skill, and not something that varying purge gap or shrinking the horizon could
  have been expected to change, since neither touches the underlying field choice. Per CLAUDE.md's core
  finding, the platform's own prior work already established that even the strongest tested models did not
  beat naive-first in a stable, significant way on **returns** (the leakage-free, economically meaningful
  target) — this batch, like the first, used raw price levels, and its results must not be read as
  contradicting or extending that finding either way.
- **A meaningful naive-first comparison on this dataset would still need a returns-based field (e.g. log
  returns) and/or a genuine second model to benchmark**, neither of which this batch attempted either —
  this remains a deliberately minimal, "does the pipeline behave consistently across purge-gap and horizon
  choices" exploration, not a research result.
- Full per-split detail (train/test boundaries, purge windows, all seven `MetricSet` fields per baseline,
  per-split DM statistic/p-value) is available via `GET /runs/{id}/splits` for each run ID above.
