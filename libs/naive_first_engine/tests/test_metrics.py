import numpy as np
import pandas as pd
import pytest

from naive_first_engine.metrics import (
    directional_accuracy,
    f1_directional,
    mae,
    mase,
    oos_r2,
    rmse,
    smape,
)

from .fixtures import (
    DIRECTIONAL_TOLERANCE_DA,
    DIRECTIONAL_TOLERANCE_F1,
    NAIVE0_MAE_1H,
    NAIVE0_RMSE_1H,
    OLS_DA_1H,
    OLS_DA_6H,
    OLS_F1_1H,
    OLS_F1_6H,
    OLS_MAE_1H,
    OLS_RMSE_1H,
    TOLERANCE,
    build_1h_reference_scenario,
    build_directional_reference_scenario_1h,
    build_directional_reference_scenario_6h,
)


def test_mae_matches_published_naive0_1h_number():
    scenario = build_1h_reference_scenario()
    assert mae(scenario.y_true, scenario.y_pred_naive0) == pytest.approx(
        NAIVE0_MAE_1H, abs=TOLERANCE
    )


def test_rmse_matches_published_naive0_1h_number():
    scenario = build_1h_reference_scenario()
    assert rmse(scenario.y_true, scenario.y_pred_naive0) == pytest.approx(
        NAIVE0_RMSE_1H, abs=TOLERANCE
    )


def test_mae_matches_published_ols_1h_number():
    scenario = build_1h_reference_scenario()
    assert mae(scenario.y_true, scenario.y_pred_ols) == pytest.approx(
        OLS_MAE_1H, abs=TOLERANCE
    )


def test_rmse_matches_published_ols_1h_number():
    scenario = build_1h_reference_scenario()
    assert rmse(scenario.y_true, scenario.y_pred_ols) == pytest.approx(
        OLS_RMSE_1H, abs=TOLERANCE
    )


def test_mae_raises_on_mismatched_length():
    y_true = pd.Series([1.0, 2.0, 3.0])
    y_pred = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        mae(y_true, y_pred)


def test_rmse_raises_on_mismatched_length():
    y_true = pd.Series([1.0, 2.0, 3.0])
    y_pred = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        rmse(y_true, y_pred)


def test_mae_raises_on_misaligned_index():
    y_true = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 3])
    with pytest.raises(ValueError):
        mae(y_true, y_pred)


def test_rmse_raises_on_misaligned_index():
    y_true = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 3])
    with pytest.raises(ValueError):
        rmse(y_true, y_pred)


def test_smape_bounded_in_documented_range():
    y_true = pd.Series([1.0, -2.0, 3.0, 0.5])
    y_pred = pd.Series([1.2, -1.5, -3.0, 5.0])
    value = smape(y_true, y_pred)
    assert 0.0 <= value <= 200.0


def test_smape_symmetric_under_swapping_over_under_forecast():
    y_true = pd.Series([1.0, -2.0, 3.0, 0.5])
    y_pred = pd.Series([1.2, -1.5, -3.0, 5.0])
    assert smape(y_true, y_pred) == pytest.approx(smape(y_pred, y_true))


def test_smape_raises_on_mismatched_length():
    y_true = pd.Series([1.0, 2.0, 3.0])
    y_pred = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        smape(y_true, y_pred)


def test_smape_raises_on_misaligned_index():
    y_true = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 3])
    with pytest.raises(ValueError):
        smape(y_true, y_pred)


def test_mase_returns_one_when_error_matches_naive_in_sample_benchmark():
    y_train = pd.Series([1.0, 3.0, 2.0, 5.0, 4.0])  # abs diffs [2, 1, 3, 1], mean 1.75
    y_true = pd.Series([10.0, 10.0])
    y_pred = pd.Series([11.75, 8.25])  # abs diffs both 1.75, same mean as above
    assert mase(y_true, y_pred, y_train, seasonal_period=1) == pytest.approx(1.0)


def test_mase_raises_on_mismatched_length():
    y_true = pd.Series([1.0, 2.0, 3.0])
    y_pred = pd.Series([1.0, 2.0])
    y_train = pd.Series([1.0, 3.0, 2.0, 5.0, 4.0])
    with pytest.raises(ValueError):
        mase(y_true, y_pred, y_train, seasonal_period=1)


def test_mase_raises_on_misaligned_index():
    y_true = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 3])
    y_train = pd.Series([1.0, 3.0, 2.0, 5.0, 4.0])
    with pytest.raises(ValueError):
        mase(y_true, y_pred, y_train, seasonal_period=1)


# NFE-009: directional_accuracy / f1_directional.
#
# The 1h/6h regression targets below come from a *separate* directional
# fixture (build_directional_reference_scenario_1h/_6h in fixtures.py), not
# the shared build_1h_reference_scenario used above. That MAE/RMSE fixture's
# residual signs are independent seeded coin flips (it was calibrated on
# magnitude only), so it does not and is not meant to reproduce DA/F1 — see
# the "Directional (DA/F1) reference scenarios" section of fixtures.py for
# the full construction and why a standalone 6h fixture is also needed.


def test_directional_accuracy_matches_published_ols_1h_number():
    scenario = build_directional_reference_scenario_1h()
    assert directional_accuracy(
        scenario.y_true, scenario.y_pred_ols
    ) == pytest.approx(OLS_DA_1H, abs=DIRECTIONAL_TOLERANCE_DA)


def test_f1_directional_matches_published_ols_1h_number():
    scenario = build_directional_reference_scenario_1h()
    assert f1_directional(scenario.y_true, scenario.y_pred_ols) == pytest.approx(
        OLS_F1_1H, abs=DIRECTIONAL_TOLERANCE_F1
    )


def test_directional_accuracy_matches_published_ols_6h_number():
    scenario = build_directional_reference_scenario_6h()
    assert directional_accuracy(
        scenario.y_true, scenario.y_pred_ols
    ) == pytest.approx(OLS_DA_6H, abs=DIRECTIONAL_TOLERANCE_DA)


def test_f1_directional_matches_published_ols_6h_number():
    scenario = build_directional_reference_scenario_6h()
    assert f1_directional(scenario.y_true, scenario.y_pred_ols) == pytest.approx(
        OLS_F1_6H, abs=DIRECTIONAL_TOLERANCE_F1
    )


def test_directional_accuracy_is_exactly_50_on_uncorrelated_signs():
    # y_true's sign cycles with period 2 ([+,-,+,-,...]); y_pred's sign
    # cycles with period 4 ([+,+,-,-,+,+,-,-,...]). These two periodic
    # patterns are orthogonal over any window that is a multiple of 4: in
    # every block of 4 consecutive points exactly 2 match and 2 mismatch
    # (index0 +/+ match, index1 -/+ mismatch, index2 +/- mismatch, index3
    # -/- match), regardless of how many blocks are concatenated. So this
    # hits exactly 50.0 by construction, not because a particular random
    # draw happened to average out — no seed to cherry-pick.
    n = 40
    assert n % 4 == 0
    y_true_sign = np.resize([1.0, -1.0], n)
    y_pred_sign = np.resize([1.0, 1.0, -1.0, -1.0], n)
    index = pd.RangeIndex(n)
    y_true = pd.Series(y_true_sign, index=index)
    y_pred = pd.Series(y_pred_sign, index=index)
    assert directional_accuracy(y_true, y_pred) == 50.0


def test_directional_accuracy_raises_on_mismatched_length():
    y_true = pd.Series([1.0, -2.0, 3.0])
    y_pred = pd.Series([1.0, -2.0])
    with pytest.raises(ValueError):
        directional_accuracy(y_true, y_pred)


def test_directional_accuracy_raises_on_misaligned_index():
    y_true = pd.Series([1.0, -2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, -2.0, 3.0], index=[0, 1, 3])
    with pytest.raises(ValueError):
        directional_accuracy(y_true, y_pred)


def test_f1_directional_raises_on_mismatched_length():
    y_true = pd.Series([1.0, -2.0, 3.0])
    y_pred = pd.Series([1.0, -2.0])
    with pytest.raises(ValueError):
        f1_directional(y_true, y_pred)


def test_f1_directional_raises_on_misaligned_index():
    y_true = pd.Series([1.0, -2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, -2.0, 3.0], index=[0, 1, 3])
    with pytest.raises(ValueError):
        f1_directional(y_true, y_pred)


def test_f1_directional_is_one_when_all_up_moves_predicted_correctly():
    y_true = pd.Series([1.0, 2.0, -1.0, -2.0])
    y_pred = pd.Series([0.5, 1.0, -0.5, -1.0])
    assert f1_directional(y_true, y_pred) == pytest.approx(1.0)


def test_f1_directional_is_zero_not_a_zero_division_error_when_pred_never_predicts_up():
    # Naive0 (baselines.Naive0) forecasts exactly 0 for every point, so
    # pred_up is all-False; precision/recall must be defined as 0, not raise.
    y_true = pd.Series([1.0, -2.0, 3.0, -4.0])
    y_pred = pd.Series([0.0, 0.0, 0.0, 0.0])
    assert f1_directional(y_true, y_pred) == pytest.approx(0.0)


# NFE-010: oos_r2.


def test_oos_r2_is_one_when_pred_is_perfect():
    y_true = pd.Series([1.0, 2.0, 3.0, 4.0])
    y_pred = pd.Series([1.0, 2.0, 3.0, 4.0])
    y_naive = pd.Series([0.0, 0.0, 0.0, 0.0])
    assert oos_r2(y_true, y_pred, y_naive) == pytest.approx(1.0)


def test_oos_r2_is_zero_when_pred_matches_naive_error():
    y_true = pd.Series([1.0, 2.0, 3.0, 4.0])
    y_naive = pd.Series([0.5, 1.5, 2.5, 3.5])  # SSE = 4 * 0.25 = 1.0
    y_pred = pd.Series([1.5, 2.5, 3.5, 4.5])  # SSE = 4 * 0.25 = 1.0, same as naive
    assert oos_r2(y_true, y_pred, y_naive) == pytest.approx(0.0)


def test_oos_r2_is_negative_when_pred_squared_error_exceeds_naive():
    # Matches "modelos treinados pioraram o erro quadrático relativo ao
    # benchmark" (da-tese-ao-produto.md section 1.5): a model whose squared
    # error is strictly worse than the naive benchmark's must score < 0.
    y_true = pd.Series([1.0, 2.0, 3.0, 4.0])
    y_naive = pd.Series([1.0, 2.0, 3.0, 3.0])  # SSE = 1.0
    y_pred = pd.Series([3.0, 5.0, 6.0, 9.0])  # SSE = 4+9+9+25 = 47.0, much worse
    value = oos_r2(y_true, y_pred, y_naive)
    assert value < 0.0
    assert value == pytest.approx(1 - 47.0 / 1.0)


def test_oos_r2_matches_hand_derived_formula_on_synthetic_example():
    y_true = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0])
    y_pred = pd.Series([1.0, 5.0, 5.0, 10.0, 9.0])
    y_naive = pd.Series([2.0, 2.0, 4.0, 6.0, 8.0])
    sse_pred = sum((t - p) ** 2 for t, p in zip(y_true, y_pred))
    sse_naive = sum((t - n) ** 2 for t, n in zip(y_true, y_naive))
    expected = 1 - sse_pred / sse_naive
    assert oos_r2(y_true, y_pred, y_naive) == pytest.approx(expected)


def test_oos_r2_raises_on_mismatched_length():
    y_true = pd.Series([1.0, 2.0, 3.0])
    y_pred = pd.Series([1.0, 2.0, 3.0])
    y_naive = pd.Series([1.0, 2.0])
    with pytest.raises(ValueError):
        oos_r2(y_true, y_pred, y_naive)


def test_oos_r2_raises_on_misaligned_index():
    y_true = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    y_pred = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    y_naive = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 3])
    with pytest.raises(ValueError):
        oos_r2(y_true, y_pred, y_naive)
