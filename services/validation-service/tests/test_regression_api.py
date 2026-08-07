"""VS-011: full `POST /runs` -> `GET /runs/{id}/splits` HTTP regression gate.

============================== DISCLOSURE ==================================
1. Every scenario below drives the ACTUAL HTTP surface end to end via
   FastAPI's `TestClient`: `client.post("/runs", ...)` then
   `client.get(f"/runs/{id}/splits", ...)`. Neither test calls
   `naive_first_engine.protocol.run_validation_protocol` directly -- that is
   exactly what `test_runs_endpoint.py`/`test_splits_endpoint.py` already do
   for general wiring correctness. This file's job is narrower and specific:
   the published-numbers regression gate for that same wiring, mirroring
   `naive_first_engine/tests/test_regression_1h.py`'s own disclosure-block
   convention at the top of its file.

2. Fixture reuse (VS-011 Design section): the ticket's stated preference is
   to import `naive_first_engine.tests.fixtures` directly rather than
   re-derive its calibration math. That import was tried first, from this
   service's own `.venv`, and confirmed NOT importable:

       .venv\\Scripts\\python.exe -c "import naive_first_engine.tests.fixtures"
       -> ModuleNotFoundError: No module named 'naive_first_engine.tests'

   `naive_first_engine` is installed here as an editable path dependency of
   its `src/naive_first_engine` package; `tests/` is a sibling directory of
   that package root, not a subpackage of it, so it was never going to be on
   the import path via a normal editable install (PEP 660 only exposes the
   package's own `src` tree). This is the deviation the ticket's Design
   section anticipated and pre-authorized: rather than reaching across the
   monorepo with a `sys.path` hack into another library's test-internal
   directory (a coupling this service's own dependency boundary -- see
   README.md's "Does not own" -- does not sanction), this file re-implements,
   locally and verbatim, the two private calibration primitives it needs
   (`_calibrated_magnitudes`, `_signed`), copied from
   `libs/naive_first_engine/tests/fixtures.py` (read, not imported) with the
   same behavior, and pins them to the SAME published constants that module
   exports: `NAIVE0_MAE_1H = 0.003627`, `NAIVE0_RMSE_1H = 0.005321`,
   `TOLERANCE = 1e-6` (da-tese-ao-produto.md section 1.3). These are restated
   published numbers, not a locally-invented "close enough" substitute --
   Test 1 below fails if the service's actual HTTP response ever drifts from
   them. `naive_first_engine`'s public API is not touched by this
   workaround; only the synthetic-*data*-construction helpers (test-internal,
   not exported) are duplicated.

3. Scope: this is a wiring/integration check. It confirms Naive0's MAE/RMSE
   and NaiveLast's DM verdicts survive `run_validation_protocol` ->
   persistence (`app.models.SplitResult`) -> `GET /runs/{id}/splits`'s JSON
   response unaltered. It is explicitly NOT a re-derivation of the DM test,
   MAE, or any other metric's correctness -- that remains
   `naive_first_engine`'s own regression suite's (`test_regression_1h.py`)
   job, and nothing here re-checks math that suite doesn't already cover at
   the function/orchestrator level.

4. Test 2's construction is NEW and service-specific, not adapted from
   `fixtures.build_ols_dm_splits_1h`. That fixture's per-split (Naive0, OLS)
   error pairs assume an injectable synthetic baseline
   (`test_regression_1h.py`'s `_SyntheticOLS`, wired via
   `ValidationConfig.extra_baselines`); this service's handler
   (`app/routers/runs.py`) never passes `extra_baselines` -- it only ever
   scores the REAL `naive_first_engine.baselines.NaiveLast`
   (`predict(train, test) = train.iloc[-1]`, carried flat over the whole test
   window), with no seam to inject a different forecast series. So Test 2
   instead exploits NaiveLast's actual, documented `predict()` formula
   directly: for each split, the train segment's LAST value is pinned to a
   fixed constant `L = 10.0`; the test segment is then built as EITHER
   `L + tiny noise` OR `0.0 + tiny noise` (noise std `1e-4`):
     - test ~= L: NaiveLast's flat-`L` forecast lands almost exactly on the
       test values (tiny squared error); Naive0's flat-`0` forecast misses by
       ~`L` every point (squared error ~= L**2, ~1e5x larger) -> the DM
       loss-differential (squared_error(naive_last) - squared_error(naive0))
       is strongly, consistently negative -> verdict "better".
     - test ~= 0: the reverse -- NaiveLast misses by ~`L`, Naive0 is almost
       exact -> loss differential strongly positive -> verdict "worse".
   `L` and the noise scale are chosen only to make the two error
   populations' squared magnitudes differ by several orders of magnitude, so
   the DM test's significance threshold (p < 0.05, dm_test.py) is cleared by
   a wide, construction-guaranteed margin rather than tuned to a razor's-edge
   statistic. There is no published DM verdict count for this service to
   target -- this sprint never runs an OLS/RF/ARIMA baseline through this
   endpoint (VS-017's client-model baseline is deferred) -- so "known,
   checkable" here means "independently derived from NaiveLast's own
   predict() formula and asserted before the request is ever sent", not "one
   more published thesis number reproduced".
==============================================================================
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Published 1h numbers, da-tese-ao-produto.md section 1.3 -- the SAME
# constants `naive_first_engine/tests/fixtures.py` exports as
# `NAIVE0_MAE_1H`/`NAIVE0_RMSE_1H`/`TOLERANCE` (restated here, not
# reinvented, per disclosure point 2 above; that module isn't importable from
# this service's own venv, see disclosure point 2).
NAIVE0_MAE_1H = 0.003627
NAIVE0_RMSE_1H = 0.005321
TOLERANCE = 1e-6

_GAMMA_SHAPE = 0.8
_N = 2000
_PREAMBLE_LEN = 50
_PURGE_GAP = 24  # thesis default (da-tese-ao-produto.md section 1.2).


def _calibrated_magnitudes(seed: int, target_mean: float, target_rms: float, n: int) -> np.ndarray:
    """Non-negative array whose mean and RMS exactly equal the given targets.

    Same affine-rescale technique as
    `naive_first_engine/tests/fixtures.py`'s `_calibrated_magnitudes` (copied
    here, not imported -- see disclosure point 2): draw a seeded Gamma(0.8)
    sample, then find `a, b` such that `a*x + b` has the target mean/RMS
    exactly (up to float64 rounding).
    """
    rng = np.random.default_rng(seed)
    x = rng.gamma(shape=_GAMMA_SHAPE, scale=1.0, size=n)
    mean_x = x.mean()
    mean_sq_x = (x**2).mean()
    var_x = mean_sq_x - mean_x**2
    a = np.sqrt((target_rms**2 - target_mean**2) / var_x)
    b = target_mean - a * mean_x
    magnitudes = a * x + b
    assert magnitudes.min() >= 0, "calibration produced a negative magnitude"
    return magnitudes


def _signed(magnitudes: np.ndarray, sign_seed: int) -> np.ndarray:
    signs = np.random.default_rng(sign_seed).choice([-1.0, 1.0], size=magnitudes.shape)
    return signs * magnitudes


def _with_preamble(target: pd.Series, seed: int) -> pd.Series:
    """Prepend `_PREAMBLE_LEN + _PURGE_GAP` filler points before `target` so a
    single-split `train_window=_PREAMBLE_LEN, purge_gap=_PURGE_GAP,
    test_window=len(target), step=len(target)` request's ONE split covers
    exactly `train=filler`, `test=target`. Adapted from
    `test_regression_1h.py`'s helper of the same name/purpose (tiny seeded
    noise, not a flat constant, so `mase`'s in-sample denominator isn't a
    division-by-zero on a constant train segment; Naive0 ignores `train`
    entirely so no assertion below depends on the filler's actual values).
    """
    filler_n = _PREAMBLE_LEN + _PURGE_GAP
    filler_index = pd.date_range(
        end=target.index[0] - pd.Timedelta(hours=1), periods=filler_n, freq="h"
    )
    filler = pd.Series(
        np.random.default_rng(seed).normal(0.0, 1e-6, size=filler_n), index=filler_index
    )
    return pd.concat([filler, target])


def _to_inline_dataset(series: pd.Series) -> dict:
    return {
        "inline": {
            "timestamps": [ts.isoformat() for ts in series.index],
            "values": series.to_numpy().tolist(),
        }
    }


# ---------------------------------------------------------------------------
# Test 1: Naive0 MAE/RMSE round-trip.


def test_naive0_mae_round_trips_via_http(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    magnitudes = _calibrated_magnitudes(101, NAIVE0_MAE_1H, NAIVE0_RMSE_1H, _N)
    index = pd.date_range("2021-01-01", periods=_N, freq="h", name="timestamp")
    y_true = pd.Series(_signed(magnitudes, 1101), index=index, name="y_true")
    series = _with_preamble(y_true, seed=9001)

    payload = {
        "tenant_id": "tenant-1",
        "dataset_id": "dataset-naive0-regression",
        "dataset_reference": _to_inline_dataset(series),
        "horizon": 1,
        "purge_gap_hours": _PURGE_GAP,
        "train_window": _PREAMBLE_LEN,
        "test_window": _N,
        "step": _N,
    }

    response = client.post("/runs", json=payload)
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    splits_response = client.get(f"/runs/{run_id}/splits", params={"tenant_id": "tenant-1"})
    assert splits_response.status_code == 200, splits_response.text
    body = splits_response.json()

    assert len(body) == 1  # single-split scenario by construction (see _with_preamble)

    assert body[0]["naive0_mae"] == pytest.approx(NAIVE0_MAE_1H, abs=TOLERANCE)
    assert body[0]["naive0_rmse"] == pytest.approx(NAIVE0_RMSE_1H, abs=TOLERANCE)


# ---------------------------------------------------------------------------
# Test 2: NaiveLast-vs-Naive0 DM verdict pattern round-trip.

_DM_TRAIN_WINDOW = 30
_DM_TEST_WINDOW = 200
_DM_L = 10.0
_DM_NOISE_STD = 1e-4
_DM_TRAIN_STD = 0.01


def _dm_scenario_series(pattern: list[str]) -> pd.Series:
    """Build a multi-split series where each split's verdict is pinned by
    construction -- see disclosure point 4 above for the full derivation.
    """
    step = _DM_TRAIN_WINDOW + _PURGE_GAP + _DM_TEST_WINDOW
    total_n = len(pattern) * step
    index = pd.date_range("2024-01-01", periods=total_n, freq="h", name="timestamp")
    values = np.empty(total_n, dtype="float64")

    for k, verdict in enumerate(pattern):
        base = k * step

        train_vals = np.random.default_rng(1000 + k).normal(
            _DM_L, _DM_TRAIN_STD, size=_DM_TRAIN_WINDOW
        )
        train_vals[-1] = _DM_L  # NaiveLast.predict reads exactly this element
        values[base : base + _DM_TRAIN_WINDOW] = train_vals

        purge_vals = np.random.default_rng(2000 + k).normal(0.0, 1e-6, size=_PURGE_GAP)
        values[base + _DM_TRAIN_WINDOW : base + _DM_TRAIN_WINDOW + _PURGE_GAP] = purge_vals

        test_center = _DM_L if verdict == "better" else 0.0
        test_vals = np.random.default_rng(3000 + k).normal(
            test_center, _DM_NOISE_STD, size=_DM_TEST_WINDOW
        )
        values[base + _DM_TRAIN_WINDOW + _PURGE_GAP : base + step] = test_vals

    return pd.Series(values, index=index, name="y_true")


def test_dm_verdict_pattern_round_trips_via_http(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    client = TestClient(app)

    # Independently derived expectation (disclosure point 4), fixed BEFORE
    # the request is sent -- not read back from the response.
    pattern = ["better", "better", "worse", "worse"]
    series = _dm_scenario_series(pattern)

    payload = {
        "tenant_id": "tenant-1",
        "dataset_id": "dataset-dm-regression",
        "dataset_reference": _to_inline_dataset(series),
        "horizon": 1,
        "purge_gap_hours": _PURGE_GAP,
        "train_window": _DM_TRAIN_WINDOW,
        "test_window": _DM_TEST_WINDOW,
        "step": _DM_TRAIN_WINDOW + _PURGE_GAP + _DM_TEST_WINDOW,
    }

    response = client.post("/runs", json=payload)
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    splits_response = client.get(f"/runs/{run_id}/splits", params={"tenant_id": "tenant-1"})
    assert splits_response.status_code == 200, splits_response.text
    body = splits_response.json()

    assert len(body) == len(pattern)  # one split per pattern entry, by construction
    verdicts = [row["dm_verdict"] for row in body]
    assert verdicts == pattern  # model_*/dm_* columns map to naive_last (app.models docstring)
