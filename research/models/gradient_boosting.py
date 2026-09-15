"""MR-004 — LightGBM `Baseline` (Strategy) implementation, research-only.

This is a candidate research model run through `naive_first_engine`'s existing,
unmodified leakage-aware protocol (`run_validation_protocol`) and scored
against the mandatory Naive0 baseline via Diebold-Mariano test, exactly like
every other baseline in that protocol. It is NOT a price-prediction or
trading-signal product feature -- it is a research baseline, and whether it
beats Naive0 is an open, honestly-reported question, not an assumed or
claimed outcome (see docs/tickets/MR-004.md and CLAUDE.md's positioning
rules).

`LightGBMBaseline.predict` only ever reads from its own `train`/`test`
arguments (the `Baseline` Protocol's own structural leakage-safety guarantee,
`libs/naive_first_engine/src/naive_first_engine/baselines.py`) -- no
module-level state, no closure over a full series. A fresh
`lightgbm.LGBMRegressor` is constructed and fit inside every `predict` call,
never reused/cached across splits, so each split's fit is strictly
train-fold-only per CLAUDE.md's leakage rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import lightgbm
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features import lagged_returns, rolling_mean_return, rolling_volatility  # noqa: E402

# Fixed, non-negotiable per sprint-41.md's light-compute ceiling -- no search
# loop of any kind may vary these.
_LGBM_PARAMS = dict(
    n_estimators=50,
    max_depth=4,
    num_leaves=15,
    learning_rate=0.1,
    min_child_samples=10,
    n_jobs=1,
    random_state=42,
    verbose=-1,
)

_LAGS = [1, 2, 3]
_ROLL_WINDOW = 5


def _make_features(returns: pd.Series) -> pd.DataFrame:
    """Builds a lag/rolling feature frame from a single fold's returns only.

    Reuses `research/features.py`'s existing rolling/lag functions (MR-002) --
    no rolling/lag logic is reimplemented here. `returns` is whatever fold
    (train or test) the caller passes; this function never sees or touches
    any other fold.
    """
    frame = lagged_returns(returns, _LAGS)
    # `rolling(window)` is current-row-inclusive, so the raw rolling value at
    # row t would contain returns[t] itself -- the exact target being
    # predicted at that row. An extra `.shift(1)` here (on top of
    # `rolling_mean_return`/`rolling_volatility`'s own correct, unmodified
    # behavior in features.py) makes the feature at row t use only
    # returns[t-5..t-1], matching `lagged_returns`'s own lag>=1 convention.
    frame["roll_mean"] = rolling_mean_return(returns, _ROLL_WINDOW).shift(1)
    frame["roll_vol"] = rolling_volatility(returns, _ROLL_WINDOW).shift(1)
    return frame


class LightGBMBaseline:
    """`Baseline`-protocol-conforming LightGBM regressor.

    `.name` requirement: the backlog AC literally asks for a `.name`
    attribute; `naive_first_engine.protocol._baseline_key` actually keys
    `config.extra_baselines` entries by `type(baseline).__name__`, which this
    class's name (`LightGBMBaseline`) already satisfies without any extra
    attribute. A `.name` property is added anyway, set to the class name, so
    both the literal backlog wording and the engine's own convention are
    satisfied by the same value.
    """

    name = "LightGBMBaseline"

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        """Fits a brand-new `LGBMRegressor` on `train` only, predicts `test`.

        Only `train`/`test` (this call's own arguments) are ever read -- no
        reference to any other split's data, matching the leakage-safety
        argument `Baseline`'s own docstring makes for `train`-only fitting.
        A fresh regressor is constructed here on every call; none is
        stored on `self` or reused across calls.
        """
        train_features = _make_features(train).dropna()
        train_target = train.loc[train_features.index]

        model = lightgbm.LGBMRegressor(**_LGBM_PARAMS)
        model.fit(train_features, train_target)

        test_features = _make_features(test)
        test_features = test_features.fillna(0.0)
        predictions = model.predict(test_features)
        return pd.Series(predictions, index=test.index)
