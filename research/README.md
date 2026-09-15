# Applied Research (Phase 3)

Regime-sensitive models (HMM, hybrids), broader model comparison (boosting, GRU, Transformer), and per-split explainability (SHAP/feature importance) — all tested under the same purged walk-forward protocol against the naive benchmark, never as a standalone claim of predictive edge.

See [../docs/da-tese-ao-produto.md](../docs/da-tese-ao-produto.md) section 1.6.

Status: greenlit (Sprint 33, `docs/sprints/sprint-33.md`). Sprint 40 shipped MR-002
(`docs/tickets/MR-002.md`), the first real code in this directory: leakage-safe, stateless feature-
engineering functions in `research/features.py`, each operating only on a caller-supplied train-fold
`pandas.Series` (no global fit, no second Series-shaped parameter):

- `rolling_volatility(train_returns, window)` — rolling standard deviation of the fold's returns.
- `rolling_mean_return(train_returns, window)` — rolling mean of the fold's returns.
- `rolling_std_return(train_returns, window)` — rolling standard deviation of the fold's returns (kept as
  a separately named function from `rolling_volatility` for backlog-literal traceability; same primitive).
- `lagged_returns(train_returns, lags)` — one `shift(lag)` column per requested lag.

These are engineered inputs for a future candidate model, not signals — whether any of them help a model
beat the naive baseline is an open research question, answered only by MR-004/MR-005's future
Diebold-Mariano test results, not assumed by MR-002 itself. MR-004 (candidate model wiring), MR-005
(DM-test comparison against naive), and MR-006 (per-split explainability) remain not started and are not
implied by this sprint.
