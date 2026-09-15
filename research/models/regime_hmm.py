"""MR-005 -- regime-gated linear model `Baseline` (Strategy) implementation, research-only.

This is a candidate research model run through `naive_first_engine`'s
existing, unmodified leakage-aware protocol (`run_validation_protocol`) and
scored against the mandatory Naive0 baseline via Diebold-Mariano test,
exactly like every other baseline. It is NOT a price-prediction or
trading-signal product feature -- it is a research baseline testing whether a
regime-switching structure (a 2-state Gaussian HMM gating a simple linear
model per state) helps or not; whether it beats Naive0 is an open, honestly
-reported question, not an assumed or claimed outcome (see
docs/tickets/MR-005.md and CLAUDE.md's positioning rules).

`RegimeHMMBaseline.predict` only ever reads from its own `train`/`test`
arguments (the `Baseline` Protocol's own structural leakage-safety guarantee,
`libs/naive_first_engine/src/naive_first_engine/baselines.py`) -- no
module-level state, no closure over a full series. A fresh `GaussianHMM` and
fresh per-state `LinearRegression` objects are constructed and fit inside
every `predict` call, never reused/cached across splits, so each split's
regime fit and per-state fit are both strictly train-fold-only per
CLAUDE.md's leakage rule.

Light-compute scoping (sprint-42.md, non-negotiable ceiling -- see
docs/tickets/MR-005.md): state count fixed at 2, `n_iter` capped at 30,
`random_state=42`, no hyperparameter search of any kind.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from features import lagged_returns  # noqa: E402

# Fixed, non-negotiable per sprint-42.md's light-compute ceiling -- no search
# loop of any kind may vary these.
_N_STATES = 2
_HMM_N_ITER = 30
_RANDOM_STATE = 42

_LAGS = [1, 2]


def _make_features(returns: pd.Series) -> pd.DataFrame:
    """Builds a small lag feature frame from a single fold's returns only.

    Reuses `research/features.py`'s existing `lagged_returns` (MR-002) -- no
    lag/rolling logic is reimplemented here. `returns` is whatever fold
    (train or test) the caller passes; this function never sees or touches
    any other fold. `lagged_returns` already applies `shift(lag)` with
    `lag >= 1`, so no feature at row t ever contains `returns[t]` itself --
    the same same-row-target-leakage pitfall MR-004's review found and fixed
    in `gradient_boosting.py::_make_features` does not apply here because no
    current-row-inclusive `rolling(...)` primitive is used at all.
    """
    return lagged_returns(returns, _LAGS)


def _fit_predict_and_explain(train: pd.Series, test: pd.Series) -> tuple[pd.Series, dict]:
    """Fits a brand-new 2-state HMM + per-state linear model on `train` only,
    predicts `test`, and returns both the prediction Series and an
    explainability artifact (dict) read directly off the same fitted
    objects this call already built -- no second/separate fit.
    `RegimeHMMBaseline.predict` (below) and MR-006's
    `research/explainability.py::ExplainableRegimeHMM` both call this single
    function, so there is exactly one HMM fit + one linear fit per state per
    split regardless of which caller is used.

    The explainability artifact (MR-006, feature-importance-only scope, no
    SHAP -- see `docs/tickets/MR-006.md`) is:
    - `state_coefficients`: `{state: {"coef": ..., "intercept": ..., "features": [...]}}`,
      each per-state `LinearRegression`'s own fitted `.coef_`/`.intercept_`
      -- the linear model genuinely is its own explanation.
    - `test_state_assignment`: a `pd.Series` (indexed like `test`) giving the
      HMM-decoded active state for each test-fold row -- the same
      already-computed `test_state_series` this call uses to route each
      row to its per-state linear model, not a recomputation.
    This is NOT a claim this model predicts real Bitcoin returns or
    generates a trading signal -- it is instrumentation describing which
    fitted regime/linear-model combination produced a given split's forecast.

    Only `train`/`test` (this call's own arguments) are ever read -- no
    reference to any other split's data. A fresh `GaussianHMM` and fresh
    `LinearRegression` objects are constructed here on every call; nothing
    is stored on any instance or reused across calls, matching
    `LightGBMBaseline`'s same structural leakage-safety shape.

    Regime states are derived from `train`'s own observed returns only
    (`hmm.fit`/`hmm.predict` both see only `train`).

    Correction (post-MR-005-review): `test` row states are decoded from
    the already-fitted `hmm` using the LAGGED return series
    (`test.shift(1)`), not `test`'s own current-row values. The original
    version fed `test.to_numpy()` -- i.e. `return[t]` itself, the exact
    value this baseline is asked to predict at row t -- into
    `hmm.predict()` to pick which state (and therefore which per-state
    linear model) governs row t. That is target leakage: no real-time
    deployment would know `return[t]` before predicting it, so using it
    to select the regime for row t is information from the target's own
    timestamp being used to help predict that same timestamp -- the same
    leakage category MR-004's review found in `_make_features`'s rolling
    window, just surfacing here in the regime-routing step instead of a
    regression feature. The fix mirrors this file's existing lag-feature
    convention (`lagged_returns`, `shift(lag>=1)`): row t's state is
    decoded from `return[t-1]`, which is genuinely available before
    `return[t]` is observed. The first test row has no in-test lag
    available, so it is backfilled from `train`'s own last observed
    return (still train-fold-only information, available before the
    test fold starts). The per-state linear models themselves already
    only ever see lag features (`_make_features`), never the row's own
    current return, and that part was correct and is unchanged.
    """
    train_obs = train.to_numpy().reshape(-1, 1)

    hmm = GaussianHMM(
        n_components=_N_STATES,
        covariance_type="diag",
        n_iter=_HMM_N_ITER,
        random_state=_RANDOM_STATE,
    )
    hmm.fit(train_obs)
    train_states = hmm.predict(train_obs)

    train_features = _make_features(train).dropna()
    train_state_series = pd.Series(train_states, index=train.index).loc[train_features.index]
    train_target = train.loc[train_features.index]

    state_models: dict[int, LinearRegression] = {}
    for state in range(_N_STATES):
        mask = train_state_series == state
        if mask.sum() == 0:
            continue
        model = LinearRegression()
        model.fit(train_features.loc[mask], train_target.loc[mask])
        state_models[state] = model

    last_train_value = float(train.iloc[-1]) if len(train) else 0.0
    test_lagged = test.shift(1)
    test_lagged.iloc[0] = last_train_value
    test_obs = test_lagged.to_numpy().reshape(-1, 1)
    test_states = hmm.predict(test_obs)
    test_state_series = pd.Series(test_states, index=test.index)

    test_features = _make_features(test).fillna(0.0)

    predictions = np.zeros(len(test))
    fallback_value = float(train_target.mean()) if len(train_target) else 0.0
    for i, (idx, state) in enumerate(test_state_series.items()):
        model = state_models.get(state)
        if model is None:
            predictions[i] = fallback_value
            continue
        row = test_features.loc[[idx]]
        predictions[i] = model.predict(row)[0]

    pred_series = pd.Series(predictions, index=test.index)

    state_coefficients = {
        state: {
            "coef": model.coef_.tolist(),
            "intercept": float(model.intercept_),
            "features": list(train_features.columns),
        }
        for state, model in state_models.items()
    }
    artifact = {
        "state_coefficients": state_coefficients,
        "test_state_assignment": test_state_series,
    }

    return pred_series, artifact


class RegimeHMMBaseline:
    """`Baseline`-protocol-conforming 2-state Gaussian-HMM-gated linear model.

    `.name` requirement: mirrors MR-004's `LightGBMBaseline` reasoning --
    `naive_first_engine.protocol._baseline_key` keys `config.extra_baselines`
    entries by `type(baseline).__name__`, which this class's name
    (`RegimeHMMBaseline`) already satisfies without any extra attribute. A
    `.name` property is added anyway, set to the class name, so both the
    literal backlog wording and the engine's own convention are satisfied by
    the same value.
    """

    name = "RegimeHMMBaseline"

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        """Fits a brand-new 2-state HMM + per-state linear model on `train`
        only, predicts `test`.

        Delegates to `_fit_predict_and_explain` and discards the
        explainability artifact -- this method's own observable behavior
        (including the "no instance attribute is ever set" structural
        invariant MR-005's own test asserts) is unchanged by MR-006.
        """
        predictions, _ = _fit_predict_and_explain(train, test)
        return predictions
