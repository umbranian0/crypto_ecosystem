"""MR-001: returns-vs-levels methodology guardrail.

`README.md`'s own VS-023 "Live-UAT finding, methodological" paragraph
disclosed a gap: `ingestion-service`'s `field` values (`close`, `value`,
`reddit_sid_com`) are raw price/metric levels, not returns -- Naive0 is
nonsensically wrong by construction on a raw level, producing an artifact
"better than naive" verdict rather than a real finding. This module is the
product decision that closes that gap: detect, then hard-reject (`422`), a
submitted series that looks like a raw level rather than a returns series.
No auto-transform is performed -- see `docs/tickets/MR-001.md`'s Design
section ("No auto-transform") for the full reasoning; this mirrors DH-003's
hard-block-not-auto-resolve precedent already established in
`dataset_source.py`.

**Why not a formal ADF (Augmented Dickey-Fuller) test**: a real ADF test
requires `statsmodels` (a new dependency this module deliberately does not
add -- confirmed absent from `pyproject.toml` at ticket time) and produces a
p-value whose pass/fail threshold is itself a judgment call, prone to being
flaky/ambiguous on the short synthetic series unit tests use. Instead, this
module uses a deterministic, dependency-free heuristic combining two classic
signatures of a non-differenced, trending price level vs. a returns series:

1. **Lag-1 autocorrelation** of the raw series close to 1 -- a price level
   moves by small increments relative to its own level, so consecutive
   values are highly correlated; a returns series is close to i.i.d. noise
   around a fixed mean, so lag-1 autocorrelation is low.
2. **Mean far from zero relative to spread** (`abs(mean) / std`) -- a
   returns series (fractional/log returns) is centered near 0 by
   construction; a price level series is not.

Both conditions must hold (AND, not OR) to flag a series as price-level-like
-- this avoids over-flagging a returns series that happens to carry a
slight, non-price-level trend. Thresholds below (`LAG1_AUTOCORR_THRESHOLD =
0.90`, `MEAN_OVER_STD_THRESHOLD = 1.0`) are conservative-by-design and
disclosed here, not silently tuned -- same convention as
`app.routers.runs.MAX_SPLIT_COUNT`/`naive_first_engine`'s
`DEFAULT_PURGE_GAP`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LAG1_AUTOCORR_THRESHOLD = 0.90
MEAN_OVER_STD_THRESHOLD = 1.0


@dataclass(frozen=True)
class LevelDetectionResult:
    is_price_level: bool
    lag1_autocorr: float
    mean_over_std: float


def detect_price_level_series(series: pd.Series) -> LevelDetectionResult:
    """Computes the two heuristic signals (module docstring) and ANDs them
    against the documented thresholds. A series with fewer than 2 points, or
    a zero-variance series, cannot support a lag-1 autocorrelation
    computation or a mean/std ratio -- both are reported as `0.0` and the
    series is never flagged in that degenerate case (there isn't enough
    signal to make a level-vs-returns call either way).
    """
    values = series.to_numpy(dtype="float64")

    if len(values) < 2:
        return LevelDetectionResult(is_price_level=False, lag1_autocorr=0.0, mean_over_std=0.0)

    std = values.std()
    if std == 0.0:
        return LevelDetectionResult(is_price_level=False, lag1_autocorr=0.0, mean_over_std=0.0)

    mean_over_std = abs(values.mean()) / std

    lag1_std_ok = values[:-1].std() > 0.0 and values[1:].std() > 0.0
    lag1_autocorr = (
        float(np.corrcoef(values[:-1], values[1:])[0, 1]) if lag1_std_ok else 0.0
    )

    is_price_level = bool(
        lag1_autocorr > LAG1_AUTOCORR_THRESHOLD and mean_over_std > MEAN_OVER_STD_THRESHOLD
    )

    return LevelDetectionResult(
        is_price_level=is_price_level,
        lag1_autocorr=lag1_autocorr,
        mean_over_std=mean_over_std,
    )
