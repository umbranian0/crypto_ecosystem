"""MR-008 -- unit test for `research/real_data.py::load_real_hourly_returns`
plus the actual real-data run: `LightGBMBaseline`/`RegimeHMMBaseline`
(MR-004/MR-005, unmodified) against real `binance_price_btcusdt_1h` data at
1h/6h horizons, via the real, unmodified `run_validation_protocol`.

============================== DISCLOSURE ==================================
This is real BTC/USDT hourly close-price data (a bounded ~209-day window,
see `docs/tickets/MR-008.md`'s Compute-budget scoping section), not a
claim this model predicts real Bitcoin prices or generates a trading
signal -- it is a research baseline run through the same leakage-aware
protocol as every other baseline, and whether it beats Naive0 is an open,
honestly-reported question, not an assumed or claimed outcome (CLAUDE.md
positioning rules). No test in this file asserts either candidate model
"beats" Naive0.
==============================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from real_data import RealDataSourceError, load_real_hourly_returns  # noqa: E402

from models.gradient_boosting import LightGBMBaseline  # noqa: E402
from models.regime_hmm import RegimeHMMBaseline  # noqa: E402

from naive_first_engine.protocol import ValidationConfig, run_validation_protocol  # noqa: E402

BASE_URL = "http://127.0.0.1:8003"
TENANT_ID = "271d391dd7bf4213b3e5fb8ea6636563"
SOURCE = "binance_price_btcusdt_1h"
START = "2026-01-10T00:00:00"
END = "2026-08-07T09:00:00"

CONFIG_KWARGS = dict(train_window=500, test_window=50, step=250, purge_gap=6)


def _live_stack_reachable() -> bool:
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        return response.status_code < 400
    except httpx.HTTPError:
        return False


# ---------------------------------------------------------------------------
# Unit test: fake/mocked transport, no live network needed.
# ---------------------------------------------------------------------------


def test_load_real_hourly_returns_parses_a_canned_response():
    canned_payload = {
        "timestamps": ["2026-01-10T02:00:00Z", "2026-01-10T00:00:00Z", "2026-01-10T01:00:00Z"],
        "values": [102.0, 100.0, 101.0],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-tenant-id"] == "tenant-abc"
        assert request.url.params["start"] == "2026-01-01T00:00:00"
        assert request.url.params["end"] == "2026-01-02T00:00:00"
        return httpx.Response(200, json=canned_payload)

    transport = httpx.MockTransport(handler)
    original_get = httpx.get

    def fake_get(url, params=None, headers=None, timeout=None):
        with httpx.Client(transport=transport) as client:
            return client.get(url, params=params, headers=headers)

    import real_data as real_data_module

    real_data_module.httpx.get = fake_get
    try:
        series = load_real_hourly_returns(
            tenant_id="tenant-abc",
            source="binance_price_btcusdt_1h",
            start="2026-01-01T00:00:00",
            end="2026-01-02T00:00:00",
            base_url="http://fake-ingestion:8003",
        )
    finally:
        real_data_module.httpx.get = original_get

    assert isinstance(series, pd.Series)
    assert series.index.is_monotonic_increasing
    assert list(series.to_numpy()) == [100.0, 101.0, 102.0]


def test_load_real_hourly_returns_raises_typed_error_on_bad_response():
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    def handler_malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not_timestamps": [], "not_values": []})

    import real_data as real_data_module

    original_get = httpx.get
    try:
        transport = httpx.MockTransport(handler_500)

        def fake_get_500(url, params=None, headers=None, timeout=None):
            with httpx.Client(transport=transport) as client:
                return client.get(url, params=params, headers=headers)

        real_data_module.httpx.get = fake_get_500
        with pytest.raises(RealDataSourceError):
            load_real_hourly_returns(
                tenant_id="tenant-abc",
                source="binance_price_btcusdt_1h",
                start="2026-01-01T00:00:00",
                end="2026-01-02T00:00:00",
                base_url="http://fake-ingestion:8003",
            )

        transport = httpx.MockTransport(handler_malformed)

        def fake_get_malformed(url, params=None, headers=None, timeout=None):
            with httpx.Client(transport=transport) as client:
                return client.get(url, params=params, headers=headers)

        real_data_module.httpx.get = fake_get_malformed
        with pytest.raises(RealDataSourceError):
            load_real_hourly_returns(
                tenant_id="tenant-abc",
                source="binance_price_btcusdt_1h",
                start="2026-01-01T00:00:00",
                end="2026-01-02T00:00:00",
                base_url="http://fake-ingestion:8003",
            )
    finally:
        real_data_module.httpx.get = original_get


# ---------------------------------------------------------------------------
# Live test: real `naive-first-ingestion-service` container.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _live_stack_reachable(), reason="live ingestion-service stack not reachable")
def test_live_fetch_returns_non_trivial_row_count():
    series = load_real_hourly_returns(
        tenant_id=TENANT_ID,
        source=SOURCE,
        start=START,
        end=END,
        base_url=BASE_URL,
    )

    assert len(series) > 100
    print(f"\n[MR-008] live fetch row count for {START}..{END}: {len(series)}")


# ---------------------------------------------------------------------------
# Full MR-008 run: real data, both candidate models, both horizons.
# ---------------------------------------------------------------------------


def _load_real_returns() -> pd.Series:
    raw_series = load_real_hourly_returns(
        tenant_id=TENANT_ID,
        source=SOURCE,
        start=START,
        end=END,
        base_url=BASE_URL,
    )
    return raw_series.pct_change().dropna()


def _run_and_check(returns: pd.Series, horizon: int) -> tuple[list, dict, dict]:
    config = ValidationConfig(
        **CONFIG_KWARGS,
        horizon=horizon,
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

    return results, verdicts_by_model["LightGBMBaseline"], verdicts_by_model["RegimeHMMBaseline"]


@pytest.mark.skipif(not _live_stack_reachable(), reason="live ingestion-service stack not reachable")
@pytest.mark.parametrize("horizon", [1, 6])
def test_real_data_run_produces_split_results_with_dm_verdicts(horizon):
    returns = _load_real_returns()
    results, lgbm_verdicts, hmm_verdicts = _run_and_check(returns, horizon)

    print(f"\n[MR-008] horizon={horizon}h row_count={len(returns)}")
    print(f"[MR-008] horizon={horizon}h LightGBMBaseline DM-vs-Naive0 verdicts: {lgbm_verdicts}")
    print(f"[MR-008] horizon={horizon}h RegimeHMMBaseline DM-vs-Naive0 verdicts: {hmm_verdicts}")

    assert sum(lgbm_verdicts.values()) == len(results)
    assert sum(hmm_verdicts.values()) == len(results)
