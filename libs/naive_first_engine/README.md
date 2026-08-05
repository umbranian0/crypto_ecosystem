# naive_first_engine

**Status: build now (trigger #1 — no dependencies, core IP).**

Pure, dataset-agnostic Python library implementing the leakage-aware validation protocol (docs section 1.2 / [../../docs/solution-design.md](../../docs/solution-design.md) section 3.4):

```
src/naive_first_engine/
├── splitting.py       # rolling-origin walk-forward + configurable purge gap
├── baselines.py       # Naive0, NaiveLast
├── metrics.py         # MAE, RMSE, sMAPE, MASE, DA, F1, out-of-sample R²
├── dm_test.py          # Diebold-Mariano + Harvey et al. 1997 long-run variance correction
└── report_schema.py    # typed result objects consumed by services/reporting-service
```

**Owns**: the validation algorithm only. No I/O, no database, no web framework — pip-installable standalone so it can be open-cored/licensed independently (docs [da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 2.4).

**Does not own**: dataset storage, run orchestration, report rendering — those belong to `services/validation-service` and `services/reporting-service`, which import this library.

**Contract**: public functions in each module above, fully typed. Every function must be unit-tested against the thesis's own published numbers ([da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 1.3) as a regression check before any service is allowed to depend on it.

**Source material to extract from**: the thesis scripts `run_arima_returns.py`, `run_rf_noleak.py`, `run_sarima_only.py`.
