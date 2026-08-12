"""Error, scale-free, directional, and naive-relative out-of-sample R^2 metrics.

Single responsibility: pure functions scoring y_true/y_pred (and, where
required, y_train/y_naive) pairs. No splitting, baseline, or DM-test logic
belongs in this module.

Type convention (binding for every function added to this module, e.g.
NFE-008/009/010): ``y_true`` and ``y_pred`` are ``pandas.Series`` sharing the
same ``Index`` (same length, same labels in the same order). Functions raise
``ValueError`` on mismatched length or misaligned index rather than silently
truncating or letting pandas auto-align and introduce NaNs.

``smape`` is bounded to [0, 200] (percentage convention). ``mase`` has no
fixed upper bound; it is scale-free and equals 1.0 when the forecast's mean
absolute error matches the in-sample seasonal-naive benchmark's.

``directional_accuracy`` is bounded to [0, 100] (percentage convention).
``f1_directional`` is bounded to [0, 1] and scores the "predicted an up-move"
binary classification only (positive class = value > 0), matching the
thesis's DA/F1 table rather than macro-averaging up and down.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _check_aligned(y_true: pd.Series, y_pred: pd.Series) -> None:
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"y_true and y_pred must have the same length, got "
            f"{len(y_true)} and {len(y_pred)}"
        )
    if not y_true.index.equals(y_pred.index):
        raise ValueError("y_true and y_pred must share the same index")


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    _check_aligned(y_true, y_pred)
    return float((y_true - y_pred).abs().mean())


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    _check_aligned(y_true, y_pred)
    return float(np.sqrt(((y_true - y_pred) ** 2).mean()))


def smape(y_true: pd.Series, y_pred: pd.Series) -> float:
    """Symmetric MAPE, expressed as a percentage bounded to [0, 200].

    Uses the standard denominator ``(|y_true| + |y_pred|) / 2``, whose
    numerator and denominator are both symmetric in ``y_true``/``y_pred``, so
    ``smape(a, b) == smape(b, a)``.
    """
    _check_aligned(y_true, y_pred)
    numerator = (y_true - y_pred).abs()
    denominator = (y_true.abs() + y_pred.abs()) / 2
    return float((numerator / denominator).mean()) * 100


def mase(
    y_true: pd.Series, y_pred: pd.Series, y_train: pd.Series, seasonal_period: int
) -> float:
    """Mean Absolute Scaled Error (Hyndman & Koehler), scaled by the in-sample
    seasonal-naive MAE computed from ``y_train`` at ``seasonal_period`` lag.
    """
    _check_aligned(y_true, y_pred)
    naive_in_sample_mae = (y_train - y_train.shift(seasonal_period)).abs().mean()
    forecast_mae = float((y_true - y_pred).abs().mean())
    # A zero in-sample seasonal-naive MAE means y_train is exactly constant at
    # seasonal_period lag over the training window -- MASE is undefined (not
    # silently inf/nan from a raw division) in that degenerate case.
    if naive_in_sample_mae == 0:
        return 0.0 if forecast_mae == 0 else float("nan")
    return forecast_mae / naive_in_sample_mae


def directional_accuracy(y_true: pd.Series, y_pred: pd.Series) -> float:
    """Percentage of points where ``y_pred``'s sign matches ``y_true``'s sign.

    Expressed on a 0-100 scale, matching the DA (%) convention in
    da-tese-ao-produto.md section 1.3.
    """
    _check_aligned(y_true, y_pred)
    matches = np.sign(y_true) == np.sign(y_pred)
    return float(matches.mean()) * 100


def oos_r2(y_true: pd.Series, y_pred: pd.Series, y_naive: pd.Series) -> float:
    """Out-of-sample R^2, defined relative to the naive benchmark's squared
    error: ``1 - SSE(y_pred) / SSE(y_naive)``, where
    ``SSE(x) = sum((y_true - x) ** 2)``.

    This is deliberately NOT scikit-learn's default R^2, which is relative to
    ``SSE(mean(y_true))`` (mean-relative). da-tese-ao-produto.md section 1.5
    reports out-of-sample R^2 as negative for every model/horizon precisely
    under the naive-relative definition, meaning trained models made the
    squared error *worse* than Naive0, not merely that they "explained
    little" of the target's variance. Using the mean-relative definition
    here would silently misrepresent that finding, since a model can beat
    the unconditional mean while still losing to the naive benchmark.
    """
    _check_aligned(y_true, y_pred)
    _check_aligned(y_true, y_naive)
    sse_pred = float(((y_true - y_pred) ** 2).sum())
    sse_naive = float(((y_true - y_naive) ** 2).sum())
    return 1 - sse_pred / sse_naive


def f1_directional(y_true: pd.Series, y_pred: pd.Series) -> float:
    """F1 score of the "predicted an up-move" binary classification.

    Positive class is ``value > 0`` (an up-move) on both series, matching the
    thesis's DA/F1 table (section 1.3), which treats direction prediction as
    a binary up/down classification rather than macro-averaging up and down.
    """
    _check_aligned(y_true, y_pred)
    actual_up = y_true > 0
    pred_up = y_pred > 0
    true_positive = float((actual_up & pred_up).sum())
    false_positive = float((~actual_up & pred_up).sum())
    false_negative = float((actual_up & ~pred_up).sum())
    # Naive0 (naive_first_engine.baselines) forecasts exactly 0 for every
    # point, so pred_up is all-False and true_positive+false_positive is
    # always 0 for it -- precision/recall are conventionally undefined-as-0
    # in that case (matches sklearn's zero_division=0), not a raised error,
    # since Naive0 must be scorable on every metric per solution-design.md
    # section 1 principle 1.
    precision = 0.0 if (true_positive + false_positive) == 0 else true_positive / (true_positive + false_positive)
    recall = 0.0 if (true_positive + false_negative) == 0 else true_positive / (true_positive + false_negative)
    return 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
