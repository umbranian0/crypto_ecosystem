# BTC/USDT 1h — Multi-Horizon Naive-First Validation Runs (2026-09-13)

Source: `CLAUDE.md` (core finding, non-negotiable positioning), `docs/adr/0007-*` / FHS-002's
`_HORIZON_TO_DAY_LABEL` horizon-mapping convention, `services/validation-service/src/app/routers/runs.py`
(RSS-004 500-split cap, `MAX_SPLIT_COUNT`), `services/dashboard-web/src/app/templates/run_new.html` (Naive0
raw-price-levels tooltip).

## What this is, and what it is not

These are six **naive-first validation runs** against a real, tenant-owned dataset
(`binance_price_btcusdt_1h`), each testing whether the platform's mandatory naive baselines
(Naive0, NaiveLast) hold up at a given horizon under leakage-free, purged walk-forward validation. They
are **not** forecasts, predictions, or trading signals, and this document does not present them as such —
consistent with `run_new.html`'s own copy ("does not generate a prediction, forecast, or trading signal")
and CLAUDE.md's core finding that no model has been shown to beat naive-first in a stable, significant way.

## Dataset

- **Source**: `binance_price_btcusdt_1h` (Binance BTC/USDT hourly close, causal connector crawl)
- **Row count**: 79,418 rows (confirmed via `GET /ingestion/datasets/binance_price_btcusdt_1h/series`,
  the live read path `validation-service`'s `IngestionServiceDatasetSource` actually uses — not the
  `GET /ingestion/datasets` listing, which reads a materialized view refreshed on a 5-minute cadence and can
  lag a just-completed crawl)
- **Date range**: 2017-08-17T04:00:00Z to 2026-09-13T13:00:00Z (full available history, hourly)
- **Field**: raw close price level (no field override supplied — dataset default)

## Horizon mapping

Per this platform's existing day-label convention (ADR-0007 / FHS-002's `_HORIZON_TO_DAY_LABEL`, reused
here rather than reinvented), day-labels map to hourly step-counts against this hourly dataset:

| Day label | Horizon (hours) |
|---|---|
| 7 days  | 168 |
| 15 days | 360 |
| 30 days | 720 |

## Run configs

Two configs per horizon ("tight" = smaller train/test windows, more splits; "wide" = larger windows, fewer
splits), six runs total — a small, deliberately non-exhaustive set per this session's "keep it simple"
convention, not a parameter grid. `purge_gap_hours` is set equal to the horizon at each row, so the purge
gap always fully covers the forecast horizon between train and test folds. Split counts were computed
up front with `generate_splits`' own formula (`floor((rows - train_window - purge_gap_hours - test_window)
/ step) + 1`) and chosen to land well under the RSS-004 500-split cap — no run needed step-size correction
after submission; every computed count matched the platform's own count exactly.

| Run | Horizon | Config | purge_gap_hours | train_window | test_window | step | Computed splits | Run ID |
|---|---|---|---|---|---|---|---|---|
| btc-1h-h168-tight | 168 (7d)  | tight | 168 | 2,000  | 500   | 1,000 | 77 | `8829344b553b4684b97cd1ccf072af14` |
| btc-1h-h168-wide  | 168 (7d)  | wide  | 168 | 8,000  | 2,000 | 4,000 | 18 | `70c815b67bc3435b9fff35290780c1ed` |
| btc-1h-h360-tight | 360 (15d) | tight | 360 | 3,000  | 800   | 1,500 | 51 | `bbab6d6256644c058b08cd35f9367dab` |
| btc-1h-h360-wide  | 360 (15d) | wide  | 360 | 10,000 | 2,500 | 5,000 | 14 | `f1648818b1ed496496580f0d05e12ef3` |
| btc-1h-h720-tight | 720 (30d) | tight | 720 | 5,000  | 1,200 | 2,500 | 29 | `08fec84ddf6f47b480d8d8fedfc94f64` |
| btc-1h-h720-wide  | 720 (30d) | wide  | 720 | 15,000 | 3,000 | 7,000 | 9  | `175c47c931b642618eaa405827e1b537` |

All six were submitted via `POST /runs` and ran synchronously to `status: "completed"` (this interim
implementation of `validation-service` executes the whole protocol within the request/response cycle — see
`runs.py`'s module docstring); no run failed or hit the 422 split-count guardrail.

## Results summary

Model columns are `naive_last`'s metrics (this schema's fixed `model_*` mapping — see
`services/validation-service/src/app/models.py`'s module docstring); `naive0_*` is the literal
predict-zero baseline. DM verdict is `naive_last` vs `naive0`, per split, counted across all splits in the
run.

| Run | Splits | Mean model (NaiveLast) MAE | Mean Naive0 MAE | Mean model RMSE | Mean Naive0 RMSE | DM verdict breakdown |
|---|---|---|---|---|---|---|
| btc-1h-h168-tight | 77 | 3,891.85 | 39,435.60 | 4,255.20 | 39,492.37 | better: 76, no sig. diff: 1 |
| btc-1h-h168-wide  | 18 | 6,347.51 | 42,001.30 | 7,342.81 | 42,309.37 | better: 18 |
| btc-1h-h360-tight | 51 | 5,903.58 | 40,200.84 | 6,334.08 | 40,288.42 | better: 49, no sig. diff: 2 |
| btc-1h-h360-wide  | 14 | 7,308.61 | 42,845.69 | 8,517.72 | 43,197.94 | better: 14 |
| btc-1h-h720-tight | 29 | 7,524.43 | 40,269.48 | 8,137.92 | 40,405.17 | better: 28, no sig. diff: 1 |
| btc-1h-h720-wide  | 9  | 10,294.28 | 45,370.24 | 11,434.92 | 45,719.64 | better: 9 |

## How to read this

- **These are backtested validation results, not forecasts.** Every number above comes from
  rolling-origin walk-forward validation on historical data already in the dataset — a train fold, a purge
  gap equal to the horizon, then a scored test fold, repeated across the series. Nothing here predicts a
  future BTC price, and no run configuration used here or elsewhere on this platform produces one.
- **Naive0 losing "near-trivially" here is a known, disclosed artifact of raw price levels — not a
  finding.** `run_new.html`'s own field tooltip already discloses this: Naive0 predicts a flat `0` for every
  test point, which is "nonsensically wrong by construction" on raw, non-stationary price levels running in
  the tens of thousands of dollars. NaiveLast (predicts "next value = last observed value") is the
  economically sensible naive baseline on a raw price series, and it beating Naive0 by roughly an order of
  magnitude in every run above reflects exactly that mismatch, not any predictive skill. The DM verdicts
  above ("better" for NaiveLast vs. Naive0 in the overwhelming majority of splits) should be read the same
  way: they confirm the known artifact, not a validated insight about the dataset or any model.
  Per CLAUDE.md's core finding, the platform's own prior work already established that even the strongest
  tested models did not beat naive-first in a stable, significant way on **returns** (the leakage-free,
  economically meaningful target) — this experiment used raw price levels and a wider set of horizons, and
  its results must not be read as contradicting or extending that finding either way.
- **A meaningful naive-first comparison on this dataset would need a returns-based field (e.g. log
  returns) and/or a genuine second model to benchmark**, neither of which this run set attempted — this was
  a deliberately minimal, "does the pipeline work end-to-end at three horizons" smoke set, not a research
  result.
- Full per-split detail (train/test boundaries, purge windows, all seven `MetricSet` fields per baseline,
  per-split DM statistic/p-value) is available via `GET /runs/{id}/splits` for each run ID above.
