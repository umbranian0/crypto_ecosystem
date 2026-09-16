"""MR-013 -- sklearn-only stacking ensemble of `LightGBMBaseline`/`RegimeHMMBaseline`.

This is a candidate research model run through `naive_first_engine`'s
existing, unmodified leakage-aware protocol (`run_validation_protocol`) and
scored against the mandatory Naive0 baseline via Diebold-Mariano test,
exactly like every other baseline in that protocol. It is NOT a
price-prediction or trading-signal product feature -- it is a research
baseline combining two existing candidate models via a linear meta-learner;
whether it beats Naive0 is an open, honestly-reported question, not an
assumed or claimed outcome (see docs/tickets/MR-013.md and CLAUDE.md's
positioning rules).

`StackingEnsembleBaseline.predict` only ever reads from its own `train`/
`test` arguments (the `Baseline` Protocol's own structural leakage-safety
guarantee) -- no module-level state, no closure over a full series.

**The leakage guard (binding, docs/tickets/MR-013.md "The leakage guard"
section)**: the meta-learner (`sklearn.linear_model.Ridge`) must never be
fit on a base model's in-sample training predictions -- that would let the
meta-learner learn to trust an overfit base model exactly where it is
least reliable. Instead, `predict` internally:

1. Splits `train` itself, in time order (first ~80% / last ~20%, never
   shuffled -- CLAUDE.md's "no random/non-time-ordered splits" rule), into
   a base-fit portion and a meta-fit holdout portion.
2. Fits fresh `LightGBMBaseline`/`RegimeHMMBaseline` instances on the
   base-fit portion only, then calls `.predict(base_fit, holdout)` on each
   to obtain genuinely out-of-sample predictions on the holdout portion.
3. Fits the meta-learner on those two out-of-sample prediction columns vs.
   the holdout portion's own actual returns.
4. Re-instantiates and refits fresh `LightGBMBaseline`/`RegimeHMMBaseline`
   on the FULL `train` to produce base predictions on `test` (maximizing
   the base models' own training data for the real out-of-sample `test`
   prediction -- standard stacking practice: meta-learner trained on
   out-of-fold predictions, base learners refit on full training data for
   final inference).
5. Applies the fitted meta-learner to those test-set base predictions to
   produce the final ensemble prediction.

A fresh meta-learner and fresh base-model instances are constructed inside
every `predict` call -- no instance-level state persisted across calls,
matching `LightGBMBaseline`/`RegimeHMMBaseline`'s own structural invariant.
"""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import Ridge

from models.gradient_boosting import LightGBMBaseline
from models.regime_hmm import RegimeHMMBaseline

_BASE_FIT_FRACTION = 0.8


def _split_train_chronologically(train: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Splits `train` into a base-fit portion and a meta-fit holdout portion,
    strictly by position (first ~80% / last ~20%) -- never shuffled, per
    CLAUDE.md's "no random/non-time-ordered splits" rule.
    """
    split_at = int(len(train) * _BASE_FIT_FRACTION)
    base_fit_portion = train.iloc[:split_at]
    meta_fit_holdout_portion = train.iloc[split_at:]
    return base_fit_portion, meta_fit_holdout_portion


class StackingEnsembleBaseline:
    """`Baseline`-protocol-conforming stacking ensemble of `LightGBMBaseline`
    and `RegimeHMMBaseline`, combined via an `sklearn.linear_model.Ridge`
    meta-learner fit strictly on train-fold-internal out-of-sample base
    predictions (see module docstring's leakage guard).

    `.name` requirement: mirrors MR-004/MR-005's same reasoning --
    `naive_first_engine.protocol._baseline_key` keys `config.extra_baselines`
    entries by `type(baseline).__name__`, which this class's name already
    satisfies without any extra attribute. A `.name` property is added
    anyway, set to the class name, so both the literal backlog wording and
    the engine's own convention are satisfied by the same value.
    """

    name = "StackingEnsembleBaseline"

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        """Implements the 5-step leakage guard exactly (see module docstring).

        Fresh base-model instances and a fresh `Ridge` meta-learner are
        constructed here on every call; nothing is stored on `self` or
        reused across calls.
        """
        base_fit_portion, meta_fit_holdout_portion = _split_train_chronologically(train)

        holdout_lgbm_preds = LightGBMBaseline().predict(base_fit_portion, meta_fit_holdout_portion)
        holdout_hmm_preds = RegimeHMMBaseline().predict(base_fit_portion, meta_fit_holdout_portion)

        meta_features = pd.DataFrame(
            {
                "lgbm": holdout_lgbm_preds,
                "hmm": holdout_hmm_preds,
            }
        )
        meta_target = meta_fit_holdout_portion.loc[meta_features.index]

        meta_learner = Ridge()
        meta_learner.fit(meta_features, meta_target)

        test_lgbm_preds = LightGBMBaseline().predict(train, test)
        test_hmm_preds = RegimeHMMBaseline().predict(train, test)

        test_meta_features = pd.DataFrame(
            {
                "lgbm": test_lgbm_preds,
                "hmm": test_hmm_preds,
            }
        )

        ensemble_predictions = meta_learner.predict(test_meta_features)
        return pd.Series(ensemble_predictions, index=test.index)
