"""MDF-004-01 / ADR-0010: additive, multi-column candidate-model interface.

This module is intentionally separate from `baselines.py`. `Baseline.predict`
(train: pd.Series, test: pd.Series) governs only the mandatory Naive0/NaiveLast
benchmarks and, by construction, the error Series `dm_test.py` consumes --
it is not, and per ADR-0010 does not need to become, the call shape for a
candidate model that consumes a multi-column feature `DataFrame` (e.g.
`services/validation-service`'s `feature_dataset.py`, MDF-003) to produce a
prediction on the same target. `CandidateModel` below is that additive
interface: same Strategy pattern, same pre-sliced-input leakage guarantee,
different (DataFrame-shaped) input type.

Not wired into `protocol.py`'s `run_validation_protocol` or any other call
site -- this ticket is interface-design-only (MDF-004-01's scope). Nothing
in this library or any service imports or calls this module today.
"""

from __future__ import annotations

import typing

import pandas as pd


@typing.runtime_checkable
class CandidateModel(typing.Protocol):
    """Strategy interface: turn a split's train/test *feature DataFrames*,
    plus the split's train-period target Series, into a forecast Series on
    the same target.

    `train_features`/`test_features` are already the pre-sliced DataFrames
    implied by a `Split` (the same `train_start..train_end` /
    `test_start..test_end` boundaries `Baseline.predict` receives, just
    applied to a multi-column feature table instead of a single Series --
    e.g. `FeatureDatasetAssembler.assemble(...).feature_dataframe.loc[split
    boundaries]` in services/validation-service). `train_target` is the
    train-period target Series (also pre-sliced to `train_start..train_end`)
    a model needs to fit against; there is deliberately no `test_target`
    parameter, so it is structurally impossible for `predict` to read the
    test period's own target values, matching `Baseline`'s existing
    leakage-safety argument: implementations only ever receive data that is
    already sliced to a boundary, never the full frame/series plus a
    boundary they could read past. This composes with, but does not
    replace, `splitting.generate_splits`'s enforced purge gap, which
    guarantees `train_end` and `test_start` are never adjacent enough to
    leak information across the purge window -- exactly as it does for
    `Baseline` today, since `generate_splits` produces the same `Split`
    boundaries regardless of what is later sliced from them (see
    `tests/test_candidate_model.py::test_generate_splits_same_regardless_of_model_input_shape`).
    """

    def predict(
        self,
        train_features: pd.DataFrame,
        train_target: pd.Series,
        test_features: pd.DataFrame,
    ) -> pd.Series: ...
