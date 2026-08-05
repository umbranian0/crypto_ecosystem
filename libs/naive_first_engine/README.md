# naive_first_engine

**Status: implemented, hardened (Sprint 01 + Sprint 02 — see docs/sprints/sprint-01.md, docs/sprints/sprint-02.md, and docs/tickets/README.md for live ticket status). All backlog stories in docs/product/backlog-naive-first-engine.md are done.**

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

**Regression coverage, 6h/24h (NFE-016)**: `tests/test_regression_6h.py`/`tests/test_regression_24h.py` extend the above to the 6h/24h horizons using the same kind of documented, seeded synthetic fixtures (not the original dataset — see each file's disclosure block). Unlike the 1h suite, these two horizons specifically exercise the Harvey et al. (1997) long-run-variance correction in `dm_test.py`, which is a no-op at horizon=1 by construction.

**Standalone publishability check (NFE-017)**: [`scripts/check_standalone.py`](scripts/check_standalone.py) installs this package into a clean, throwaway venv (no `-e`, no workspace-root resolution) and runs a smoke `import naive_first_engine` + minimal `run_validation_protocol` call from inside it, proving the package is pip-installable and usable standalone. Re-run it (`python scripts/check_standalone.py` from within `libs/naive_first_engine`) whenever `pyproject.toml`'s dependencies change.

## Public API

Implementation-plan.md section 8: "for libs, the public function signatures in the README stay in sync with the code — CI should fail if they drift." The list below is machine-checked by [`scripts/check_doc_sync.py`](scripts/check_doc_sync.py) (also runnable as `tests/test_doc_sync.py`) — **re-run it after adding, removing, or renaming any public (non-underscore-prefixed) top-level function or class in any of the six modules below.** One line per public function/class, `` `name(args)` `` for functions (default-value expressions included, type annotations omitted — see the script's header comment for why) or `` `ClassName` (class) `` for classes.

### `splitting.py`
- `Split` (class)
- `generate_splits(index, train_window, test_window, step, purge_gap=DEFAULT_PURGE_GAP)`

### `baselines.py`
- `Baseline` (class)
- `Naive0` (class)
- `NaiveLast` (class)

### `metrics.py`
- `mae(y_true, y_pred)`
- `rmse(y_true, y_pred)`
- `smape(y_true, y_pred)`
- `mase(y_true, y_pred, y_train, seasonal_period)`
- `directional_accuracy(y_true, y_pred)`
- `oos_r2(y_true, y_pred, y_naive)`
- `f1_directional(y_true, y_pred)`

### `dm_test.py`
- `DMResult` (class)
- `dm_test(errors_model, errors_naive0, horizon=1)`

### `report_schema.py`
- `SplitBoundaries` (class)
- `MetricSet` (class)
- `BaselineResult` (class)
- `SplitResult` (class)

### `protocol.py`
- `ValidationConfig` (class)
- `run_validation_protocol(series, config)`
