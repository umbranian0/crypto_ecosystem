---
name: naive-first-audit
description: Generate a naive-first validation audit report for a predictive model's forecasts (crypto/financial returns). Use when the user has model predictions (or a model + backtest) they want scored against a naive benchmark under leakage-free, purged walk-forward validation — the Subsystem 4 "Reality Check" audit product of the Naive-First ecosystem. Triggers on requests like "audit this model", "run a naive-first validation", "generate an audit report", "does this model beat naive", "check this backtest for leakage".
---

# Naive-First Audit

Produce an independent, honest validation report for a client's predictive model, in the same spirit as the thesis this ecosystem is built on: **the naive benchmark is the baseline that must be beaten, not an afterthought**, and the report must state clearly when a model does *not* beat it — that is a valid, sellable finding, not a failure to hide.

Read [../../../docs/da-tese-ao-produto.md](../../../docs/da-tese-ao-produto.md) first if you haven't already — it defines the metrics, the thesis's own results (used as the calibration reference for what "normal" looks like in this asset class), and the ethical boundaries in section 2.7. Do not violate those boundaries in the report.

## Inputs needed from the user

Before producing a report, make sure you have (ask if missing — do not guess or fabricate data):

1. **Predictions**: a time series of the model's forecasts, timestamped, at the target horizon(s) (e.g. 1h/6h/24h forward return).
2. **Ground truth**: the realized values (returns) for the same timestamps.
3. **Split boundaries** (if not provided, construct them): how train/test folds were defined. If the user's pipeline used random splits, k-fold CV, or no purge gap between train and test, flag this immediately as a **leakage risk** before doing anything else — this is the single most common way models look good and aren't (thesis section 2.5).
4. **Horizon(s)** under evaluation, and whether the target is a direct return or a level/price (a level target on a random walk is another common leakage-adjacent trap worth flagging).

If the user only has a model (no precomputed predictions), you may generate predictions yourself, but the walk-forward + purge protocol below is mandatory — do not fit once and evaluate on a random holdout.

## Validation protocol (mandatory, matches thesis section 1.2)

1. **Rolling-origin walk-forward splits.** Never a single train/test split, never k-fold with shuffling on time series data.
2. **Purge gap** between the end of each training fold and the start of its test fold, sized to at least the forecast horizon (24h gap was used in the thesis for horizons up to 24h). Explain in the report what gap was used and why.
3. **Naive baselines computed on the same splits**: at minimum Naive0 (predict zero return / no change) and NaiveLast (predict the last observed value repeats). These are the bar the client's model must clear.
4. **Preprocessing fit train-only, per split.** Any scaler, imputer, or feature-selection step fit on the full dataset (including test-fold data) before splitting is a leakage bug — call it out explicitly if found, don't silently correct it.
5. **Diebold–Mariano test per split**, model vs. Naive0, two-sided, tracking how many splits are significantly "better" vs. "worse" at p<0.05 — not just an average p-value. If horizons overlap (e.g. daily predictions on hourly data), the DM variance estimate needs the Harvey et al. (1997) long-run variance correction — apply it or flag that it's missing.

## Metrics to compute per horizon

Compute for the client model AND for each naive baseline, so the comparison is apples-to-apples:

- MAE, RMSE
- sMAPE, MASE
- Directional Accuracy (DA) and F1 (does the model call up/down moves correctly, not just small errors)
- Out-of-sample R² (report if negative — this means the model is *worse* than predicting the mean/naive, not just "explains little")
- DM test result vs. Naive0: count of splits "better" (B) vs "worse" (W) at p<0.05, plus the overall verdict

## Report structure to produce

Match the format used in the thesis summary (docs section 1.3) so results are directly comparable to the reference case:

```
# Naive-First Audit Report — <client/model name>

## 1. Scope
- Asset / target: ...
- Horizon(s) evaluated: ...
- Evaluation window: ...
- Data provided by: client / reconstructed by auditor

## 2. Leakage check (pass/fail per item)
- [ ] Train/test split is time-ordered, not random or shuffled
- [ ] Purge gap present and >= horizon length
- [ ] Preprocessing fit train-only, per split
- [ ] No target leakage in features (e.g. using future-derived indicators)
Findings: ...

## 3. Results table (per horizon)
| Model | MAE | RMSE | DA (%) | F1 | R² (OOS) | DM vs Naive0 (B/W) |
|---|---|---|---|---|---|---|
| Naive0 | ... | ... | — | — | — | — |
| NaiveLast | ... | ... | ... | ... | ... | ... |
| <client model> | ... | ... | ... | ... | ... | ... |

## 4. Verdict
State plainly: does the model beat naive, on average and per-split, at each horizon? Is the effect stable across the evaluation window or concentrated in a few splits/regimes?

## 5. Statistical accuracy vs. economic value (mandatory disclaimer)
State explicitly that this audit evaluates statistical forecast accuracy only. No transaction costs, slippage, execution, or position sizing were modeled unless the client separately commissioned the economic module (Subsystem 5). A model that beats naive statistically may still be unprofitable after costs, and vice versa is not implied either.

## 6. Recommendations
Concrete next steps: fix identified leakage, extend evaluation window, add economic-module analysis, re-audit after changes, etc.
```

## Ground rules (from docs section 2.7 — do not violate)

- Never claim or imply the audited model (or this ecosystem) can reliably predict crypto/financial prices. The audit answers "does this model beat a naive benchmark under rigorous validation," nothing more.
- Never state statistical significance on overlapping-horizon DM tests without the variance correction, or without disclosing that it's missing.
- Never fold in profitability language ("this model would have made X% returns") unless the economic module (transaction costs, slippage, execution) was explicitly run — flag its absence otherwise.
- If the client's model *does* beat naive, report that plainly too — the goal is honest measurement in both directions, not a bias toward negative findings.
