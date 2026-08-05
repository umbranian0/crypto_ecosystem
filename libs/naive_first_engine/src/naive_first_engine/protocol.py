"""single entry point orchestrating split -> baseline -> metrics -> DM-test in fixed order

Template Method (implementation-plan.md section 7): `run_validation_protocol`
is the ONLY code path in this library that produces a `DMResult`. The order
(split, then baselines including the mandatory Naive0/NaiveLast, then metrics,
then DM test against Naive0) is fixed and not reorderable by any parameter --
this is what makes solution-design.md section 1 principle 1 ("no code path
that scores a model without [naive baselines]") true by construction.

Single responsibility: orchestration only. No splitting/baseline/metric/DM-test
math lives here -- all of that is delegated to splitting.py, baselines.py,
metrics.py, dm_test.py. This module also owns no persistence/I-O.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pandas as pd

from naive_first_engine import metrics
from naive_first_engine.baselines import Baseline, Naive0, NaiveLast
from naive_first_engine.dm_test import dm_test
from naive_first_engine.report_schema import (
    BaselineResult,
    MetricSet,
    SplitBoundaries,
    SplitResult,
)
from naive_first_engine.splitting import generate_splits

# Fixed keys for the two mandatory baselines (solution-design.md section 1
# principle 1). Any `config.extra_baselines` entry is keyed by
# `type(baseline).__name__` instead -- services/validation-service must treat
# these two strings as reserved and not reuse them for a caller-supplied
# baseline's class name.
NAIVE0_KEY = "naive0"
NAIVE_LAST_KEY = "naive_last"


@dataclass(frozen=True)
class ValidationConfig:
    train_window: int | pd.Timedelta
    test_window: int | pd.Timedelta
    step: int | pd.Timedelta
    purge_gap: int | pd.Timedelta
    horizon: int
    extra_baselines: list[Baseline] = field(default_factory=list)


def _run_id(series: pd.Series, config: ValidationConfig) -> str:
    """Deterministic run_id derived from series identity + config, not a
    random UUID or timestamp (determinism is an acceptance criterion here).
    """
    payload = "|".join(
        str(x)
        for x in (
            tuple(series.index),
            tuple(series.to_numpy().tolist()),
            config.train_window,
            config.test_window,
            config.step,
            config.purge_gap,
            config.horizon,
            tuple(type(b).__name__ for b in config.extra_baselines),
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _baseline_key(baseline: Baseline, used: set[str]) -> str:
    name = type(baseline).__name__
    key = name
    suffix = 2
    while key in used:
        key = f"{name}_{suffix}"
        suffix += 1
    return key


def _metric_set(y_true: pd.Series, y_pred: pd.Series, y_train: pd.Series, y_naive: pd.Series, horizon: int) -> MetricSet:
    return MetricSet(
        mae=metrics.mae(y_true, y_pred),
        rmse=metrics.rmse(y_true, y_pred),
        smape=metrics.smape(y_true, y_pred),
        mase=metrics.mase(y_true, y_pred, y_train, seasonal_period=horizon),
        da=metrics.directional_accuracy(y_true, y_pred),
        f1=metrics.f1_directional(y_true, y_pred),
        oos_r2=metrics.oos_r2(y_true, y_pred, y_naive),
    )


def run_validation_protocol(series: pd.Series, config: ValidationConfig) -> list[SplitResult]:
    run_id = _run_id(series, config)
    splits = generate_splits(
        series.index,
        config.train_window,
        config.test_window,
        config.step,
        purge_gap=config.purge_gap,
    )

    results: list[SplitResult] = []
    for split_index, split in enumerate(splits):
        train = series.loc[split.train_start : split.train_end]
        test = series.loc[split.test_start : split.test_end]

        naive0_pred = Naive0().predict(train, test)
        naive_last_pred = NaiveLast().predict(train, test)

        baseline_results: dict[str, BaselineResult] = {}

        baseline_results[NAIVE0_KEY] = BaselineResult(
            metrics=_metric_set(test, naive0_pred, train, naive0_pred, config.horizon),
            dm_result=None,
        )

        errors_naive0 = test - naive0_pred

        used_keys = {NAIVE0_KEY, NAIVE_LAST_KEY}
        naive_last_errors = test - naive_last_pred
        baseline_results[NAIVE_LAST_KEY] = BaselineResult(
            metrics=_metric_set(test, naive_last_pred, train, naive0_pred, config.horizon),
            dm_result=dm_test(naive_last_errors, errors_naive0, horizon=config.horizon),
        )

        for baseline in config.extra_baselines:
            key = _baseline_key(baseline, used_keys)
            used_keys.add(key)
            pred = baseline.predict(train, test)
            errors_model = test - pred
            baseline_results[key] = BaselineResult(
                metrics=_metric_set(test, pred, train, naive0_pred, config.horizon),
                dm_result=dm_test(errors_model, errors_naive0, horizon=config.horizon),
            )

        results.append(
            SplitResult(
                run_id=run_id,
                split_index=split_index,
                boundaries=SplitBoundaries(
                    train_start=split.train_start,
                    train_end=split.train_end,
                    purge_start=split.purge_start,
                    purge_end=split.purge_end,
                    test_start=split.test_start,
                    test_end=split.test_end,
                ),
                baseline_results=baseline_results,
            )
        )

    return results
