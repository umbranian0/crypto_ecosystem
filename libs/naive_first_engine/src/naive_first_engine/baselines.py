"""Baseline Strategy interface and the mandatory Naive0 / NaiveLast implementations.

Single responsibility: define how any baseline (or future client-model
adapter) turns a split's train/test data into a forecast Series, without any
knowledge of splitting, metrics, or DM-test logic.
"""

from __future__ import annotations

import typing

import pandas as pd


@typing.runtime_checkable
class Baseline(typing.Protocol):
    """Strategy interface: turn a split's train/test data into a forecast.

    `train`/`test` are already the sliced Series implied by a `Split`
    (`splitting.Split.train_start`..`train_end` / `test_start`..`test_end`),
    never the full original series plus boundaries. This is a deliberate
    signature choice, not just convention: because implementations only ever
    receive the pre-sliced `train` Series, it is structurally impossible for
    `predict` to read data beyond `train_end` -- there is no full series or
    boundary argument for it to reach past. This composes with, but does not
    replace, NFE-003's enforced purge gap in `splitting.generate_splits`,
    which guarantees `train_end` and `test_start` are never adjacent enough
    to leak information across the purge window.
    """

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series: ...


class Naive0:
    """Forecasts a forward return of zero for every test-period timestamp.

    Mandatory benchmark per solution-design.md section 1 principle 1: no
    model may be scored without clearing this floor. `train` is unused
    because the forecast is 0 by construction, not derived from data.
    """

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        return pd.Series(0.0, index=test.index)


class NaiveLast:
    """Forecasts the last train-period observation, carried forward flat.

    Mandatory benchmark per solution-design.md section 1 principle 1,
    paired with Naive0 (da-tese-ao-produto.md section 2.3.1): a persistence
    floor alongside the zero-return floor. Only `train.iloc[-1]` is read, so
    the `Baseline` protocol's pre-sliced `train`/`test` signature is enough
    on its own to guarantee nothing past `train_end` is touched.
    """

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        return pd.Series(train.iloc[-1], index=test.index)
