"""Engineered feature-engineering functions for future candidate models (MR-002).

This is a research question, not a guaranteed improvement -- MR-004/MR-005 answer
whether these features help a candidate model beat the naive baseline via
Diebold-Mariano test results. MR-002's own scope stops at "the function exists and
is leakage-safe"; it makes no claim that any of these engineered inputs already
improve on naive.

Every function here takes only a train-fold `pandas.Series` (plus a plain
`int`/`list[int]` window/lag parameter) as input. There is no module-level mutable
state, no closure over a "full dataset" object, and no second Series-shaped
parameter -- each function computes only from the fold it is handed, per the
train-only-preprocessing rule in CLAUDE.md and the leakage-aware protocol
`naive_first_engine` already enforces at the split level.
"""

from __future__ import annotations

import pandas as pd


def rolling_volatility(train_returns: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation of `train_returns`.

    Caller must pass only the training fold -- no fit/computation is performed
    against any other data. Uses `Series.rolling(window).std()` with no
    `min_periods` override, so the first `window - 1` output positions are
    `NaN`; no value is ever backfilled from data outside `train_returns`.
    """
    return train_returns.rolling(window).std()


def rolling_mean_return(train_returns: pd.Series, window: int) -> pd.Series:
    """Rolling mean of `train_returns`.

    Caller must pass only the training fold -- no fit/computation is performed
    against any other data. Uses `Series.rolling(window).mean()` with no
    `min_periods` override, so the first `window - 1` output positions are
    `NaN`; no value is ever backfilled from data outside `train_returns`.
    """
    return train_returns.rolling(window).mean()


def rolling_std_return(train_returns: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation of `train_returns` themselves.

    Caller must pass only the training fold -- no fit/computation is performed
    against any other data. Same `.rolling(window).std()` primitive as
    `rolling_volatility`, kept as a separately named function for backlog-literal
    traceability (the backlog lists "rolling volatility" and "rolling std of
    returns" as two separate deliverables) -- see MR-002's Design section.
    """
    return train_returns.rolling(window).std()


def lagged_returns(train_returns: pd.Series, lags: list[int]) -> pd.DataFrame:
    """One `shift(lag)` column per entry in `lags`, named `f"lag_{lag}"`.

    Caller must pass only the training fold -- no fit/computation is performed
    against any other data. Each column's first `lag` rows are `NaN`; no value
    is ever backfilled from data outside `train_returns`.
    """
    return pd.DataFrame(
        {f"lag_{lag}": train_returns.shift(lag) for lag in lags},
        index=train_returns.index,
    )
