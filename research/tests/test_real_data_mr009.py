"""MR-009 -- extends MR-008's real-data run (`LightGBMBaseline`/
`RegimeHMMBaseline`, unmodified) to the 24h horizon, on the identical
bounded `binance_price_btcusdt_1h` window MR-008 already fetched, via the
same real, unmodified `run_validation_protocol` -> `dm_test` call path.

============================== DISCLOSURE ==================================
Same real BTC/USDT hourly close-price window MR-008 used (see
`docs/tickets/MR-008.md`'s Compute-budget scoping section), not a claim this
model predicts real Bitcoin prices or generates a trading signal -- it is a
research baseline run through the same leakage-aware protocol as every
other baseline, and whether it beats Naive0 is an open, honestly-reported
question, not an assumed or claimed outcome (CLAUDE.md positioning rules).
No test in this file asserts either candidate model "beats" Naive0.

Purge-gap decision (see `docs/tickets/MR-009.md` "Explicit purge-gap
decision for 24h"): this run uses `purge_gap=24`, wider than MR-008's
`purge_gap=6`, matching `libs/naive_first_engine`'s own thesis-regression
suite convention and the minimum requirement to keep a 24-hours-ahead
target window from overlapping into the next split's training rows.
==============================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from real_data import load_real_hourly_returns  # noqa: E402

from models.gradient_boosting import LightGBMBaseline  # noqa: E402
from models.regime_hmm import RegimeHMMBaseline  # noqa: E402

from naive_first_engine.protocol import ValidationConfig, run_validation_protocol  # noqa: E402

BASE_URL = "http://127.0.0.1:8003"
TENANT_ID = "271d391dd7bf4213b3e5fb8ea6636563"
SOURCE = "binance_price_btcusdt_1h"
START = "2026-01-10T00:00:00"
END = "2026-08-07T09:00:00"

# purge_gap=24 (not MR-008's 6) -- explicit 24h-horizon decision, see module
# docstring and docs/tickets/MR-009.md.
CONFIG_KWARGS = dict(train_window=500, test_window=50, step=250, purge_gap=24)
HORIZON = 24


def _live_stack_reachable() -> bool:
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        return response.status_code < 400
    except httpx.HTTPError:
        return False


def _load_real_returns() -> pd.Series:
    raw_series = load_real_hourly_returns(
        tenant_id=TENANT_ID,
        source=SOURCE,
        start=START,
        end=END,
        base_url=BASE_URL,
    )
    return raw_series.pct_change().dropna()


@pytest.mark.skipif(not _live_stack_reachable(), reason="live ingestion-service stack not reachable")
def test_real_data_run_24h_produces_split_results_with_dm_verdicts():
    returns = _load_real_returns()

    config = ValidationConfig(
        **CONFIG_KWARGS,
        horizon=HORIZON,
        extra_baselines=[LightGBMBaseline(), RegimeHMMBaseline()],
    )
    results = run_validation_protocol(returns, config)

    assert len(results) > 0

    verdicts_by_model = {
        "LightGBMBaseline": {"better": 0, "worse": 0, "no significant difference": 0},
        "RegimeHMMBaseline": {"better": 0, "worse": 0, "no significant difference": 0},
    }
    for split_result in results:
        for model_name in ("LightGBMBaseline", "RegimeHMMBaseline"):
            assert model_name in split_result.baseline_results
            baseline_result = split_result.baseline_results[model_name]

            metrics = baseline_result.metrics
            assert metrics.mae is not None
            assert metrics.rmse is not None
            assert metrics.da is not None
            assert metrics.f1 is not None

            assert baseline_result.dm_result is not None
            verdicts_by_model[model_name][baseline_result.dm_result.verdict] += 1

    lgbm_verdicts = verdicts_by_model["LightGBMBaseline"]
    hmm_verdicts = verdicts_by_model["RegimeHMMBaseline"]

    assert sum(lgbm_verdicts.values()) == len(results)
    assert sum(hmm_verdicts.values()) == len(results)

    print(f"\n[MR-009] horizon={HORIZON}h row_count={len(returns)} n_splits={len(results)}")
    print(f"[MR-009] horizon={HORIZON}h LightGBMBaseline DM-vs-Naive0 verdicts: {lgbm_verdicts}")
    print(f"[MR-009] horizon={HORIZON}h RegimeHMMBaseline DM-vs-Naive0 verdicts: {hmm_verdicts}")


def test_harvey_correction_branch_fires_for_horizon_24():
    """Structural check that `dm_test`'s Harvey long-run-variance correction
    (`libs/naive_first_engine/src/naive_first_engine/dm_test.py`, the
    ``for k in range(1, horizon)`` autocovariance-sum branch) actually
    executes additional terms for `horizon=24`, as opposed to the
    `horizon == 1` no-op case (`range(1, 1)` is empty -- no correction
    applied). This does not re-derive the DM statistic by hand; it confirms
    the code path taken differs between horizon=1 and horizon=24, matching
    `test_regression_24h.py`'s own precedent for how this repo verifies the
    correction fires without hand-computing the corrected variance.
    """
    from naive_first_engine.dm_test import dm_test

    rng_errors_a = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.005, 0.02, -0.01] * 5)
    rng_errors_b = pd.Series([0.02, -0.01, 0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.02] * 5)

    result_h1 = dm_test(rng_errors_a.to_numpy(), rng_errors_b.to_numpy(), horizon=1)
    result_h24 = dm_test(rng_errors_a.to_numpy(), rng_errors_b.to_numpy(), horizon=24)

    # Same input series, different horizon -> the Harvey-corrected long-run
    # variance (horizon=24) must differ from the uncorrected variance
    # (horizon=1, empty autocovariance sum), so the DM statistic differs too.
    assert result_h1.statistic != pytest.approx(result_h24.statistic)
