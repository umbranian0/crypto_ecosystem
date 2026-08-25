"""VS-017: `ClientPredictionBaseline`, a Strategy implementation of
`naive_first_engine.baselines.Baseline` backed by a client-supplied
prediction series, plus the mandatory audit-positioning disclaimer.

Single responsibility: turn an already-materialized `pd.Series` of
client predictions into the `Baseline.predict(train, test) -> pd.Series`
shape `naive_first_engine.protocol.run_validation_protocol` expects for any
`config.extra_baselines` entry -- see that module's docstring (`_baseline_key`,
the `config.extra_baselines` loop) for how this plugs in. No changes to
`naive_first_engine` itself are needed or made; this class only reuses the
`Baseline` Protocol it already defines.

The client series is loaded once, up front, via the existing `DatasetSource`
seam (`app.dataset_source`, `DatasetSourceDep` in `runs.py`) -- this module
does not define a second dataset-loading mechanism. `predict` then only ever
indexes into that pre-loaded, already-materialized `pd.Series`; it never
calls back into anything client-supplied, imports anything dynamically, or
executes anything beyond a `.loc[...]` lookup. This is what "no arbitrary
client code execution" means concretely for this ticket (VS-018).
"""

from __future__ import annotations

import pandas as pd

# Exact wording per VS-017's Design section -- both required clauses (audits
# the comparison, not the provenance) must appear verbatim (or a materially
# equivalent framing) in any response surface built on a client baseline.
CLIENT_PREDICTION_AUDIT_DISCLAIMER = (
    "This platform validates the comparison between the client-supplied "
    "prediction series and the naive baselines (Naive0/NaiveLast), computed "
    "honestly under the leakage-aware protocol. It does not certify the "
    "provenance of the client's own predictions -- a client-supplied series "
    "could itself have been produced with knowledge of test-period outcomes, "
    "and that is the client's own leakage, not this platform's."
)


class ClientPredictionBaseline:
    """`Baseline` Strategy backed by a pre-loaded client prediction series.

    `predict(train, test)` looks up every timestamp in `test.index` inside
    the pre-loaded series and returns exactly those values, in `test.index`
    order. `train` is unused (the client series already carries its own
    predictions, computed however the client computed them -- this class
    audits the comparison, not the client's own process, per the disclaimer
    above); it is still part of the signature only because `Baseline.predict`
    requires it.
    """

    def __init__(self, client_series: pd.Series) -> None:
        self._client_series = client_series

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        missing = test.index.difference(self._client_series.index)
        if not missing.empty:
            raise ValueError(
                "client prediction series is missing required test-period "
                f"timestamps: {list(missing)}"
            )
        return self._client_series.loc[test.index]
