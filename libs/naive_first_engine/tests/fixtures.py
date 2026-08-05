"""Shared synthetic "1h reference scenario" fixture for regression tests.

IMPORTANT: this is a SYNTHETIC, deterministically-constructed fixture, NOT
real BTC data. The thesis's real 1h dataset is not part of this repo (known,
accepted limitation — see docs/tickets/NFE-015.md for the disclosure rule).
The series below are built purely from seeded numpy distributions and
calibrated so that ``mae()``/``rmse()`` (from ``naive_first_engine.metrics``)
applied to them reproduce, to within ``TOLERANCE``, the published 1h numbers
from docs/da-tese-ao-produto.md section 1.3:

    Naive0: MAE 0.003627, RMSE 0.005321
    OLS:    MAE 0.003683, RMSE 0.005367

Construction, in brief (see ``build_1h_reference_scenario`` for the exact
code): Naive0's forecast is the zero vector, so its residuals are ``y_true``
itself. We draw ``y_true``'s absolute values from a seeded Gamma(shape=0.8)
sample and rescale them with an affine transform (``a * x + b``) chosen so
the sample's mean and root-mean-square land exactly on the Naive0 MAE/RMSE
targets, then assign seeded random signs. The OLS residuals are built the
same way (independent seed) so their mean/RMS land on the OLS MAE/RMSE
targets, and ``y_pred_ols = y_true - ols_residual``. The Gamma shape (0.8)
was chosen because it is the smallest tested shape whose affine-rescaled
sample stays non-negative for both target (mean, RMS) pairs — required
because these are absolute residual magnitudes.

**Reuse this fixture** — do not build a second synthetic 1h scenario.
NFE-005 (Naive0 baseline regression test), NFE-009, NFE-011, and NFE-015 must
all import ``build_1h_reference_scenario`` (or the target constants below)
from this module so the "Naive0 1h MAE" figure can never drift between test
files.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Published 1h numbers, da-tese-ao-produto.md section 1.3.
NAIVE0_MAE_1H = 0.003627
NAIVE0_RMSE_1H = 0.005321
OLS_MAE_1H = 0.003683
OLS_RMSE_1H = 0.005367

# Regression tolerance for reproducing the numbers above from the synthetic
# fixture. Construction is exact analytically; this only absorbs float64
# rounding, so it is kept far tighter than the tolerance that would be
# needed for a fit to real (non-exact-by-construction) data.
TOLERANCE = 1e-6

_N = 2000
_SEED_Y_TRUE_MAGNITUDE = 7
_SEED_Y_TRUE_SIGN = 1007
_SEED_OLS_RESIDUAL_MAGNITUDE = 11
_SEED_OLS_RESIDUAL_SIGN = 1011
_GAMMA_SHAPE = 0.8


def _calibrated_magnitudes(seed: int, target_mean: float, target_rms: float) -> np.ndarray:
    """Non-negative array whose mean and RMS exactly equal the given targets."""
    rng = np.random.default_rng(seed)
    x = rng.gamma(shape=_GAMMA_SHAPE, scale=1.0, size=_N)
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


@dataclass(frozen=True)
class ReferenceScenario1h:
    y_true: pd.Series
    y_pred_naive0: pd.Series
    y_pred_ols: pd.Series


def build_1h_reference_scenario() -> ReferenceScenario1h:
    """Build the shared synthetic 1h y_true/Naive0/OLS series.

    All three Series share the same DatetimeIndex (hourly, arbitrary start),
    matching the ``y_true``/``y_pred`` convention documented in
    ``naive_first_engine.metrics``.
    """
    index = pd.date_range("2021-01-01", periods=_N, freq="h", name="timestamp")

    y_true_magnitudes = _calibrated_magnitudes(
        _SEED_Y_TRUE_MAGNITUDE, NAIVE0_MAE_1H, NAIVE0_RMSE_1H
    )
    y_true = pd.Series(
        _signed(y_true_magnitudes, _SEED_Y_TRUE_SIGN), index=index, name="y_true"
    )

    y_pred_naive0 = pd.Series(0.0, index=index, name="y_pred_naive0")

    ols_residual_magnitudes = _calibrated_magnitudes(
        _SEED_OLS_RESIDUAL_MAGNITUDE, OLS_MAE_1H, OLS_RMSE_1H
    )
    ols_residual = pd.Series(
        _signed(ols_residual_magnitudes, _SEED_OLS_RESIDUAL_SIGN), index=index
    )
    y_pred_ols = (y_true - ols_residual).rename("y_pred_ols")

    return ReferenceScenario1h(
        y_true=y_true, y_pred_naive0=y_pred_naive0, y_pred_ols=y_pred_ols
    )


# ---------------------------------------------------------------------------
# Directional (DA/F1) reference scenarios — NFE-009.
#
# IMPORTANT: also SYNTHETIC, deterministically-constructed, NOT real BTC data
# (same disclosure as above / docs/tickets/NFE-015.md).
#
# The 1h fixture above is calibrated on MAGNITUDE (Gamma-distributed absolute
# residuals) and was never built with directional accuracy or F1 in mind — its
# residual signs are independent seeded coin flips, so it does not reproduce
# the thesis's DA/F1 numbers and is intentionally left untouched here.
#
# Directional accuracy and F1 depend only on which of four SIGN quadrants
# each point falls into, not on magnitude:
#   TP = actual up   & predicted up      TN = actual down & predicted down
#   FP = actual down & predicted up      FN = actual up   & predicted down
# With n points and a balanced actual base rate (n/2 up, n/2 down — a
# reasonable assumption for short-horizon returns, and the natural
# unconstrained choice given the thesis reports only DA/F1, not the up/down
# base rate), DA and F1 depend on exactly two free counts (TP, TN):
#   DA = (TP + TN) / n * 100
#   F1 = 2*TP / (2*TP + FP + FN) = 2*TP / (TP - TN + n)
# Solving both equations for TP and TN given target DA/F1 and n=10000 yields
# non-integer counts; each is rounded to the nearest whole point (unavoidable
# since real points can't be fractional). n=10000 was chosen because it makes
# n*DA/100 land exactly on an integer for both published DA figures (51.33,
# 52.51), so only the F1 equation needs rounding at all. The resulting
# rounding error is tiny — checked empirically to be <= 2e-4 in F1 for both
# the 1h and 6h targets below — hence DIRECTIONAL_TOLERANCE_DA is kept tight
# (DA is exact) while DIRECTIONAL_TOLERANCE_F1 absorbs that rounding.
#
# Given the four quadrant counts, each point's y_true/y_pred SIGN is fixed by
# which quadrant it belongs to; magnitudes are arbitrary positive draws from
# a seeded uniform distribution (only the sign matters for DA/F1, and no
# magnitude claim is being made or tested here).

# Published DA (%) / F1 numbers, da-tese-ao-produto.md section 1.3, OLS rows.
OLS_DA_1H = 51.33
OLS_F1_1H = 0.528
OLS_DA_6H = 52.51
OLS_F1_6H = 0.526

# DA reproduces exactly by construction (n*DA/100 is an integer for both
# targets above); F1 only reproduces up to the quadrant-count rounding
# described above, empirically <= 2e-4 for both horizons here.
DIRECTIONAL_TOLERANCE_DA = 1e-6
DIRECTIONAL_TOLERANCE_F1 = 2.5e-4

_DIR_N = 10000

# Quadrant counts solving the DA/F1 equations above for n=10000, rounded to
# the nearest integer point.
_DIR_COUNTS_1H = {"TP": 2722, "TN": 2411, "FP": 2589, "FN": 2278}
_DIR_COUNTS_6H = {"TP": 2635, "TN": 2616, "FP": 2384, "FN": 2365}

_SEED_DIR_SHUFFLE_1H = 2101
_SEED_DIR_TRUE_MAGNITUDE_1H = 2102
_SEED_DIR_PRED_MAGNITUDE_1H = 2103
_SEED_DIR_SHUFFLE_6H = 2601
_SEED_DIR_TRUE_MAGNITUDE_6H = 2602
_SEED_DIR_PRED_MAGNITUDE_6H = 2603


@dataclass(frozen=True)
class DirectionalReferenceScenario:
    y_true: pd.Series
    y_pred_ols: pd.Series


def _build_directional_scenario(
    counts: dict[str, int],
    seed_shuffle: int,
    seed_true_magnitude: int,
    seed_pred_magnitude: int,
) -> DirectionalReferenceScenario:
    labels = np.array(
        ["TP"] * counts["TP"]
        + ["TN"] * counts["TN"]
        + ["FP"] * counts["FP"]
        + ["FN"] * counts["FN"]
    )
    assert len(labels) == _DIR_N, "quadrant counts must sum to _DIR_N"
    np.random.default_rng(seed_shuffle).shuffle(labels)

    true_up = np.isin(labels, ["TP", "FN"])
    pred_up = np.isin(labels, ["TP", "FP"])

    true_magnitude = np.random.default_rng(seed_true_magnitude).uniform(
        0.1, 1.0, size=_DIR_N
    )
    pred_magnitude = np.random.default_rng(seed_pred_magnitude).uniform(
        0.1, 1.0, size=_DIR_N
    )

    index = pd.date_range("2021-01-01", periods=_DIR_N, freq="h", name="timestamp")
    y_true = pd.Series(
        np.where(true_up, true_magnitude, -true_magnitude), index=index, name="y_true"
    )
    y_pred_ols = pd.Series(
        np.where(pred_up, pred_magnitude, -pred_magnitude),
        index=index,
        name="y_pred_ols",
    )
    return DirectionalReferenceScenario(y_true=y_true, y_pred_ols=y_pred_ols)


def build_directional_reference_scenario_1h() -> DirectionalReferenceScenario:
    """Synthetic 1h y_true/OLS-prediction pair calibrated so that
    ``directional_accuracy``/``f1_directional`` applied to it reproduce the
    published OLS 1h DA/F1 numbers (``OLS_DA_1H``/``OLS_F1_1H``) within
    ``DIRECTIONAL_TOLERANCE_DA``/``DIRECTIONAL_TOLERANCE_F1``. See the module
    docstring above for the construction. Independent of, and does not reuse,
    ``build_1h_reference_scenario`` (that fixture's signs are uncalibrated).
    """
    return _build_directional_scenario(
        _DIR_COUNTS_1H,
        _SEED_DIR_SHUFFLE_1H,
        _SEED_DIR_TRUE_MAGNITUDE_1H,
        _SEED_DIR_PRED_MAGNITUDE_1H,
    )


def build_directional_reference_scenario_6h() -> DirectionalReferenceScenario:
    """Synthetic 6h y_true/OLS-prediction pair calibrated so that
    ``directional_accuracy``/``f1_directional`` applied to it reproduce the
    published OLS 6h DA/F1 numbers (``OLS_DA_6H``/``OLS_F1_6H``) within
    ``DIRECTIONAL_TOLERANCE_DA``/``DIRECTIONAL_TOLERANCE_F1``. There is no
    shared 6h MAE/RMSE fixture to reuse (NFE-005/007's fixture is 1h-specific,
    per its own docstring), so this is a standalone fixture built the same
    way as the 1h one above, with an independent seed family.
    """
    return _build_directional_scenario(
        _DIR_COUNTS_6H,
        _SEED_DIR_SHUFFLE_6H,
        _SEED_DIR_TRUE_MAGNITUDE_6H,
        _SEED_DIR_PRED_MAGNITUDE_6H,
    )


# ---------------------------------------------------------------------------
# Per-split OLS-vs-Naive0 error pairs for the DM-test regression check —
# NFE-011.
#
# IMPORTANT: also SYNTHETIC, deterministically-constructed, NOT real BTC data
# (same disclosure as above / docs/tickets/NFE-015.md).
#
# Why a NEW fixture instead of reusing build_1h_reference_scenario: that
# fixture's y_true/y_pred_naive0/y_pred_ols were chunked into contiguous
# pieces (2/3/4/.../53 chunks were all tried) and each chunk's DM test was
# run. Every chunk came back "no significant difference", at every chunk
# count. This is a real, checked property of that fixture, not a bug: it is
# calibrated so OLS's overall MAE/RMSE is only ~1.55% worse than Naive0's
# (matching the thesis's published magnitude), and that small a gap, with
# the fixture's independently-seeded residual signs, needs either a far
# larger sample or point-wise correlation between the two forecasts' errors
# to reach p<0.05 — see below.
#
# Real per-split DM power comes from exactly that correlation: Naive0 and
# OLS forecast the SAME underlying series, so their errors move together,
# and it is the *difference* of squared errors (not either error on its
# own) that has low variance when the errors are correlated. This fixture
# makes that correlation explicit rather than relying on independent draws:
# for each split, Naive0's error e0 is a seeded Normal(0, NAIVE0_RMSE_1H)
# draw, and OLS's error is e1 = K * e0 + noise, with:
#   - K = 1.02: OLS's error runs 2% larger in magnitude than Naive0's, same
#     direction (worse) as the thesis's published OLS 1h RMSE gap, though
#     not calibrated to match that gap's exact size (only its sign) — the
#     goal here is reproducing the published B/W *verdict counts*, not
#     re-deriving the MAE/RMSE numbers a second time (build_1h_reference_
#     scenario already does that).
#   - noise = independent seeded Normal(0, 0.05 * NAIVE0_RMSE_1H), a small
#     decorrelating nudge so e1 is not a literal scalar multiple of e0.
# n=500 points/split, 4 splits, independent seeds per split. n and K were
# chosen empirically (see NFE-011 self-review) so every split's |statistic|
# lands comfortably past the p<0.05 boundary (~7-8, not a near-miss) and
# all four come back "worse" (K>1 consistently), reproducing the published
# OLS 1h DM verdict count of 0 better / 4 worse (da-tese-ao-produto.md
# section 1.3). This is NOT a claim that these are the thesis's actual 4
# splits — only that this disclosed synthetic construction reproduces the
# aggregate published pattern.
#
# RF (0/13) and ARIMA (0/53) are not attempted here: no RF- or ARIMA-shaped
# fixture exists in this file yet (only Naive0/OLS series have been built so
# far, per NFE-005/007/009's scope), so reconstructing either would mean
# inventing an RF/ARIMA error-generating process from nothing but a single
# published MAE/RMSE row — out of scope for this ticket, which only needs
# one full B/W pair.

_DM_SPLIT_N = 500
_DM_SPLIT_K = 1.02
_DM_SPLIT_NOISE_FRACTION = 0.05
_DM_NUM_SPLITS = 4
_DM_SPLIT_SEED_BASE = 5100


@dataclass(frozen=True)
class DMSplitErrors:
    errors_naive0: pd.Series
    errors_model: pd.Series


def build_ols_dm_splits_1h() -> list[DMSplitErrors]:
    """Four synthetic per-split (Naive0, OLS) forecast-error pairs for 1h.

    See the module comment above this function for the full construction
    rationale and why it exists separately from ``build_1h_reference_scenario``.
    """
    splits = []
    for i in range(_DM_NUM_SPLITS):
        rng = np.random.default_rng(_DM_SPLIT_SEED_BASE + i)
        errors_naive0 = rng.normal(0.0, NAIVE0_RMSE_1H, size=_DM_SPLIT_N)
        noise = rng.normal(
            0.0, _DM_SPLIT_NOISE_FRACTION * NAIVE0_RMSE_1H, size=_DM_SPLIT_N
        )
        errors_model = _DM_SPLIT_K * errors_naive0 + noise
        index = pd.RangeIndex(_DM_SPLIT_N, name="point")
        splits.append(
            DMSplitErrors(
                errors_naive0=pd.Series(errors_naive0, index=index, name="errors_naive0"),
                errors_model=pd.Series(errors_model, index=index, name="errors_model"),
            )
        )
    return splits
