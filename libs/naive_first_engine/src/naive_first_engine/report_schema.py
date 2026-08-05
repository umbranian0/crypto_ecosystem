"""Typed, framework-free output contract: SplitBoundaries, MetricSet, DMResult, SplitResult.

Single responsibility: define the shape of a validation run's output so
downstream services (e.g. services/reporting-service, services/validation-service)
can consume it without re-deriving the structure. No computation belongs in
this module — every field here is populated by callers from splitting.py,
metrics.py, and dm_test.py; this module only imports the *types* those
modules return (dm_test.DMResult), never their functions.

Field-to-column mapping (solution-design.md section 4 `split_results` table):
    run_id, split_index                          -> SplitResult.run_id, .split_index
    train_start/end, purge_start/end, test_*      -> SplitResult.boundaries (SplitBoundaries)
    model_mae/rmse/da/f1, naive0_mae/rmse/...      -> SplitResult.baseline_results[name].metrics (MetricSet)
    dm_statistic, dm_pvalue, dm_verdict            -> SplitResult.baseline_results[name].dm_result (DMResult)
`id` (the row's DB surrogate primary key) is deliberately not modeled here —
it is assigned at persistence time, not a property of the domain object.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from naive_first_engine.dm_test import DMResult

__all__ = ["SplitBoundaries", "MetricSet", "DMResult", "BaselineResult", "SplitResult"]


@dataclass(frozen=True)
class SplitBoundaries:
    """Mirrors splitting.Split's fields exactly, but is its own type rather than
    a re-export: Split is an internal working dataclass of splitting.py (mutable,
    free to change shape as the splitter evolves), while this is a frozen output
    contract other services persist and rely on. Keeping them separate also means
    report_schema.py has zero import dependency on splitting.py.
    """

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    purge_start: pd.Timestamp | None
    purge_end: pd.Timestamp | None
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass(frozen=True)
class MetricSet:
    mae: float
    rmse: float
    smape: float
    mase: float
    da: float
    f1: float
    oos_r2: float


@dataclass(frozen=True)
class BaselineResult:
    """One baseline's (Naive0, NaiveLast, or a client model) metrics plus its
    DM-test verdict for a single split. A mapping of baseline name -> this type
    (see SplitResult.baseline_results) is what lets SplitResult scale beyond
    exactly two baselines without changing its own shape.
    """

    metrics: MetricSet
    dm_result: DMResult | None


@dataclass(frozen=True)
class SplitResult:
    run_id: str
    split_index: int
    boundaries: SplitBoundaries
    baseline_results: dict[str, BaselineResult]
