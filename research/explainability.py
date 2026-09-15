"""MR-006 -- per-split explainability collector, research-only.

Closes the thesis's stated gap ("Explicabilidade consistente por split...
Arquivo nao guarda feature importance/SHAP por split," section 1.6) for both
candidate-model shapes already shipped in `research/`:

- `LightGBMBaseline` (MR-004): per-split `feature_importances_`.
- `RegimeHMMBaseline` (MR-005): per-split, per-state `LinearRegression`
  coefficients/intercept, plus each test-fold row's HMM-decoded active
  state.

**Scope decision (binding, see `docs/tickets/MR-006.md` and
`docs/sprints/sprint-43.md`): feature-importance only, no SHAP, no new
dependency.** Classic SHAP does not map cleanly onto an HMM-gated linear
model (no natural background-distribution/sampling scheme without inventing
one), and `LGBMRegressor.feature_importances_` already gives the tree model's
own explanation with zero new dependency. Both artifacts are read directly
off the exact fitted object(s) `_fit_predict_and_explain` (in
`models/gradient_boosting.py` / `models/regime_hmm.py`) already builds inside
the single fit its caller triggers -- there is no second, separate `.fit()`
call anywhere in this module or in the two functions it wraps.

**Where this lives (AC2, "existing report pipeline")**: `services/
reporting-service` (implementation-plan.md trigger #7) is not built yet, so
"the existing report pipeline" is read as `research/`'s existing
`SplitResult`-shaped output convention (see `research/README.md`'s MR-004/
MR-005 sections). This module attaches an `ExplainabilityRecord` per split,
keyed the same way (`split_index`) as `naive_first_engine`'s own
`SplitResult`, as a research-side sibling artifact returned alongside
`run_validation_protocol`'s real output -- not a new persistence layer, not a
raw pickle/CSV dumped to disk outside this convention, and not a premature
build-out of `reporting-service` itself.

Design note: `naive_first_engine`'s `Baseline` protocol only returns a
`pd.Series` prediction (by design -- see `baselines.py`'s own docstring on
why `predict`'s signature is deliberately narrow). Rather than touching
`naive_first_engine`'s `SplitResult`/`Baseline` machinery (a high-scrutiny
change this ticket's own scope note says to avoid unless genuinely
unworkable), `ExplainableLightGBM`/`ExplainableRegimeHMM` below are thin
`Baseline`-protocol wrapper Strategies (implementation-plan.md section 7):
each `.predict` call is *itself* the single point where the model already
gets fit for that split (called once by `run_validation_protocol`'s own
per-split loop, exactly like the unwrapped baselines), and the wrapper simply
also keeps the explainability artifact that same call already produced,
appended to `self.records` for later pairing with `run_validation_protocol`'s
own `SplitResult` list by `split_index`. This is strictly additive
instrumentation -- it does not change `run_validation_protocol`, `Baseline`,
or `SplitResult` in any way, and MR-004/MR-005's own unwrapped
`LightGBMBaseline`/`RegimeHMMBaseline` classes remain usable exactly as
before (their own `predict` methods are unchanged, still hold zero instance
state, and still pass their own existing structural leakage tests).

This is a research baseline explainability aid, not a price-prediction or
trading-signal product feature -- see CLAUDE.md's positioning rules.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models.gradient_boosting import _fit_predict_and_explain as _lgbm_fit_predict_and_explain  # noqa: E402
from models.regime_hmm import _fit_predict_and_explain as _hmm_fit_predict_and_explain  # noqa: E402


@dataclass(frozen=True)
class ExplainabilityRecord:
    """One split's explainability artifact, keyed the same way (`split_index`)
    as `naive_first_engine.report_schema.SplitResult` so the two can be
    paired by `pair_with_split_results` below.

    `artifact`'s shape depends on `baseline_name`:
    - `"LightGBMBaseline"`: a `pd.Series` of `feature_importances_`, indexed
      by feature name.
    - `"RegimeHMMBaseline"`: a `dict` with `"state_coefficients"` (per-state
      `LinearRegression` `.coef_`/`.intercept_`/feature names) and
      `"test_state_assignment"` (a `pd.Series`, indexed like that split's
      `test` fold, giving the HMM-decoded active state per row).
    """

    split_index: int
    baseline_name: str
    artifact: object


class ExplainableLightGBM:
    """`Baseline`-protocol wrapper around MR-004's `LightGBMBaseline` fit
    logic that additionally records a feature-importance
    `ExplainabilityRecord` per split.

    `.predict` calls `_fit_predict_and_explain` -- the SAME function
    `LightGBMBaseline.predict` itself delegates to -- exactly once per call.
    The feature-importance artifact is read off the `LGBMRegressor` object
    that single call already fits; there is no second `.fit()` anywhere in
    this class.
    """

    name = "LightGBMBaseline"

    def __init__(self) -> None:
        self.records: list[ExplainabilityRecord] = []

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        predictions, importances = _lgbm_fit_predict_and_explain(train, test)
        self.records.append(
            ExplainabilityRecord(
                split_index=len(self.records),
                baseline_name=self.name,
                artifact=importances,
            )
        )
        return predictions


class ExplainableRegimeHMM:
    """`Baseline`-protocol wrapper around MR-005's `RegimeHMMBaseline` fit
    logic that additionally records a per-state-coefficients +
    per-row-active-state `ExplainabilityRecord` per split.

    `.predict` calls `_fit_predict_and_explain` -- the SAME function
    `RegimeHMMBaseline.predict` itself delegates to -- exactly once per call.
    The artifact is read off the HMM/per-state `LinearRegression` objects
    that single call already fits; there is no second `.fit()` anywhere in
    this class.
    """

    name = "RegimeHMMBaseline"

    def __init__(self) -> None:
        self.records: list[ExplainabilityRecord] = []

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        predictions, artifact = _hmm_fit_predict_and_explain(train, test)
        self.records.append(
            ExplainabilityRecord(
                split_index=len(self.records),
                baseline_name=self.name,
                artifact=artifact,
            )
        )
        return predictions


def pair_with_split_results(
    split_results: list, wrapper: ExplainableLightGBM | ExplainableRegimeHMM
) -> list[tuple[object, ExplainabilityRecord]]:
    """Pairs `run_validation_protocol`'s own `SplitResult` list with the
    wrapper's collected `ExplainabilityRecord`s, by `split_index` -- the
    research-side "attach to the existing result/report path" mechanism
    this ticket's scope decision calls for, instead of a parallel ad hoc
    file dump or a `naive_first_engine` schema change.
    """
    if len(split_results) != len(wrapper.records):
        raise ValueError(
            f"split_results ({len(split_results)}) and wrapper.records "
            f"({len(wrapper.records)}) length mismatch -- wrapper must be "
            "the exact `extra_baselines` instance used for this run."
        )
    paired = []
    for split_result, record in zip(split_results, wrapper.records):
        if split_result.split_index != record.split_index:
            raise ValueError(
                f"split_index mismatch: SplitResult.split_index="
                f"{split_result.split_index} vs record.split_index="
                f"{record.split_index}"
            )
        paired.append((split_result, record))
    return paired
