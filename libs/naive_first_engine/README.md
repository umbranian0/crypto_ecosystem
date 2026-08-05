# naive_first_engine

**Status: in development (Sprint 01 — see docs/sprints/sprint-01.md and docs/tickets/README.md for live ticket status).**

Pure, dataset-agnostic Python library implementing the leakage-aware validation protocol (docs section 1.2 / [../../docs/solution-design.md](../../docs/solution-design.md) section 3.4):

```
libs/naive_first_engine/
├── pyproject.toml               # uv-managed, zero web/DB/orchestration deps (pandas/numpy/scipy only)
├── src/naive_first_engine/
│   ├── __init__.py
│   ├── splitting.py             # rolling-origin walk-forward + configurable, always-enforced purge gap
│   ├── baselines.py             # Baseline Strategy interface, Naive0, NaiveLast
│   ├── metrics.py                # MAE, RMSE, sMAPE, MASE, DA, F1, naive-relative out-of-sample R²
│   ├── dm_test.py                 # Diebold-Mariano + Harvey et al. 1997 long-run variance correction
│   ├── report_schema.py           # typed result objects (SplitBoundaries, MetricSet, DMResult, SplitResult)
│   └── protocol.py                # NFE-014: sixth file, added beyond implementation-plan.md section 3's original five-file list -- run_validation_protocol (Template Method) needs a home that isn't report_schema.py, to keep that module a pure data contract
└── tests/                        # pytest; includes regression tests vs the thesis's published 1h numbers
```

**Owns**: the validation algorithm only. No I/O, no database, no web framework — pip-installable standalone so it can be open-cored/licensed independently (docs [da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 2.4).

**Does not own**: dataset storage, run orchestration, report rendering — those belong to `services/validation-service` and `services/reporting-service`, which import this library.

**Contract**: public functions in each module above, fully typed. Every function must be unit-tested against the thesis's own published numbers ([da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 1.3) as a regression check before any service is allowed to depend on it.

**Source material to extract from**: the thesis scripts `run_arima_returns.py`, `run_rf_noleak.py`, `run_sarima_only.py`.

**Regression coverage (NFE-015)**: `tests/test_regression_1h.py` runs a synthetic, seeded 1h scenario end-to-end through `run_validation_protocol` and checks it against the thesis's published 1h Naive0/OLS/RF/ARIMA MAE/RMSE/DA/F1 numbers and the OLS Diebold-Mariano verdict count (da-tese-ao-produto.md section 1.3). The thesis's real 1h dataset and model-fitting scripts are **not** in this repo — see the disclosure block at the top of that test file for exactly which numbers are reproduced end-to-end vs. not reproduced at all (RF/ARIMA DM verdict counts).
