"""Diebold-Mariano test against Naive0, per split.

This module implements the core Diebold-Mariano test (Diebold & Mariano,
1995): the loss-differential statistic, its asymptotic p-value, and a
better/worse/no-significant-difference verdict. For overlapping forecasts
(``horizon > 1``) it always applies the Harvey et al. (1997) long-run-variance
correction — this is a hard requirement (da-tese-ao-produto.md secs 2.3.1,
2.7; CLAUDE.md), not an opt-in: there is no parameter to bypass it.

Single responsibility: turn per-split forecast errors into a statistical
significance verdict. No splitting, baseline, or metric computation belongs
in this module.

Interim result type: ``DMResult`` below is a minimal local dataclass
(``statistic``, ``p_value``, ``verdict``) defined here only for this ticket.
NFE-013 re-homes this shape into ``report_schema.py`` when the library's
typed result objects are consolidated there — the next dev agent should
import/extend that version rather than defining a second ``DMResult``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

Verdict = Literal["better", "worse", "no significant difference"]

_ALPHA = 0.05


@dataclass(frozen=True)
class DMResult:
    statistic: float
    p_value: float
    verdict: Verdict


def dm_test(
    errors_model: pd.Series | np.ndarray,
    errors_naive0: pd.Series | np.ndarray,
    horizon: int = 1,
) -> DMResult:
    """Diebold-Mariano test of ``errors_model`` vs ``errors_naive0`` for one split.

    Both arguments are pre-computed per-point forecast errors (e.g.
    ``y_true - y_pred``) for a single split — never raw price/return data.
    This is a leakage-prevention constraint, not just style: the function has
    no way to reach into future data because it never receives any.

    Loss differential ``d_t = g(errors_model_t) - g(errors_naive0_t)`` uses
    squared error for ``g``, matching RMSE's role as the primary error
    metric elsewhere in this library (``metrics.py``). The statistic is the
    standard DM construction:

        statistic = mean(d) / sqrt(long_run_variance / n)

    ``horizon`` is the forecast horizon that produced ``d``. Forecasts with
    ``horizon > 1`` overlap (each ``d_t`` shares information with its
    ``horizon - 1`` neighbours), which induces autocorrelation that the plain
    sample variance ignores. ``long_run_variance`` is therefore always the
    Harvey et al. (1997) long-run-variance estimator:

        long_run_variance = gamma_0 + 2 * sum_{k=1}^{h-1} (1 - k/h) * gamma_k

    where ``gamma_k`` is the k-th sample autocovariance of ``d`` and
    ``h = horizon``. This is applied automatically — there is no flag to skip
    it — because it is a correctness requirement, not a tuning knob (see
    da-tese-ao-produto.md secs 2.3.1, 2.7). For ``horizon == 1`` the sum has
    zero terms by construction (``range(1, 1)`` is empty), so
    ``long_run_variance`` reduces exactly to ``gamma_0``, i.e. the population
    (ddof=0) variance of ``d`` — no separate no-op branch is needed.

    Harvey/Leybourne/Newbold (1997) additionally recommend a small-sample
    correction factor applied to the raw DM statistic:

        sqrt((n + 1 - 2h + h(h-1)/n) / n)

    This factor is always applied alongside the variance term. At ``h == 1``
    it equals ``sqrt((n - 1) / n)``, which exactly cancels the ddof=0 vs
    ddof=1 population/sample-variance gap between ``gamma_0`` above and the
    plain ``d.var(ddof=1)`` estimator, so the fully corrected statistic is
    exactly equal (not merely close) to the original uncorrected one for
    ``horizon == 1``.

    The p-value is two-sided, computed from the standard normal distribution
    (``scipy.stats.norm``), matching the DM test's original asymptotic
    normality result (Diebold & Mariano, 1995) rather than a t-distribution.

    ``verdict`` is "better" when the model's mean loss is significantly lower
    than Naive0's (statistic < 0, p < 0.05), "worse" when significantly
    higher (statistic > 0, p < 0.05), else "no significant difference".
    """
    errors_model = np.asarray(errors_model, dtype=float)
    errors_naive0 = np.asarray(errors_naive0, dtype=float)
    if errors_model.shape != errors_naive0.shape:
        raise ValueError(
            f"errors_model and errors_naive0 must have the same shape, got "
            f"{errors_model.shape} and {errors_naive0.shape}"
        )
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    d = errors_model**2 - errors_naive0**2
    n = d.shape[0]
    d_mean = d.mean()
    d_centered = d - d_mean

    gamma_0 = np.dot(d_centered, d_centered) / n
    autocovariance_sum = sum(
        (1 - k / horizon) * (np.dot(d_centered[k:], d_centered[:-k]) / n)
        for k in range(1, horizon)
    )
    long_run_variance = gamma_0 + 2 * autocovariance_sum

    small_sample_factor = np.sqrt(
        (n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n
    )
    statistic = (d_mean / np.sqrt(long_run_variance / n)) * small_sample_factor
    p_value = 2 * stats.norm.sf(abs(statistic))

    if p_value < _ALPHA and statistic < 0:
        verdict: Verdict = "better"
    elif p_value < _ALPHA and statistic > 0:
        verdict = "worse"
    else:
        verdict = "no significant difference"

    return DMResult(statistic=float(statistic), p_value=float(p_value), verdict=verdict)
