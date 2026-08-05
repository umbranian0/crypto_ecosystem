"""Tests for naive_first_engine.report_schema.

Pure shape tests: construct instances of each dataclass and confirm fields
round-trip. No computation is exercised here (there is none in this module).
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from naive_first_engine.dm_test import DMResult
from naive_first_engine.report_schema import (
    BaselineResult,
    MetricSet,
    SplitBoundaries,
    SplitResult,
)


def _make_boundaries() -> SplitBoundaries:
    return SplitBoundaries(
        train_start=pd.Timestamp("2024-01-01"),
        train_end=pd.Timestamp("2024-01-10"),
        purge_start=pd.Timestamp("2024-01-10 01:00"),
        purge_end=pd.Timestamp("2024-01-10 23:00"),
        test_start=pd.Timestamp("2024-01-11"),
        test_end=pd.Timestamp("2024-01-12"),
    )


def _make_metric_set(offset: float = 0.0) -> MetricSet:
    return MetricSet(
        mae=1.0 + offset,
        rmse=2.0 + offset,
        smape=3.0 + offset,
        mase=4.0 + offset,
        da=5.0 + offset,
        f1=0.6 + offset,
        oos_r2=-0.1 + offset,
    )


def _make_dm_result() -> DMResult:
    return DMResult(statistic=-2.5, p_value=0.01, verdict="better")


def _make_split_result() -> SplitResult:
    return SplitResult(
        run_id="run-123",
        split_index=0,
        boundaries=_make_boundaries(),
        baseline_results={
            "model": BaselineResult(metrics=_make_metric_set(), dm_result=_make_dm_result()),
            "naive0": BaselineResult(metrics=_make_metric_set(offset=0.5), dm_result=None),
            "naive_last": BaselineResult(
                metrics=_make_metric_set(offset=1.0),
                dm_result=DMResult(statistic=1.2, p_value=0.3, verdict="no significant difference"),
            ),
        },
    )


def test_split_boundaries_fields():
    boundaries = _make_boundaries()
    assert boundaries.train_start == pd.Timestamp("2024-01-01")
    assert boundaries.purge_start == pd.Timestamp("2024-01-10 01:00")
    assert boundaries.test_end == pd.Timestamp("2024-01-12")


def test_metric_set_fields():
    metrics = _make_metric_set()
    assert metrics.mae == 1.0
    assert metrics.rmse == 2.0
    assert metrics.smape == 3.0
    assert metrics.mase == 4.0
    assert metrics.da == 5.0
    assert metrics.f1 == 0.6
    assert metrics.oos_r2 == -0.1


def test_report_schema_reuses_dm_test_dmresult():
    # DMResult must be the same type object as dm_test.DMResult, not a
    # lookalike redefinition (per dm_test.py's own docstring instruction).
    from naive_first_engine import report_schema

    assert report_schema.DMResult is DMResult


def test_split_result_holds_multiple_baselines():
    result = _make_split_result()
    assert set(result.baseline_results) == {"model", "naive0", "naive_last"}
    assert result.baseline_results["naive0"].dm_result is None
    assert result.baseline_results["model"].dm_result.verdict == "better"


def test_dataclasses_are_frozen():
    result = _make_split_result()
    with_frozen_error = False
    try:
        result.split_index = 99
    except dataclasses.FrozenInstanceError:
        with_frozen_error = True
    assert with_frozen_error


def test_split_result_roundtrips_through_asdict():
    original = _make_split_result()
    as_dict = dataclasses.asdict(original)

    rebuilt = SplitResult(
        run_id=as_dict["run_id"],
        split_index=as_dict["split_index"],
        boundaries=SplitBoundaries(**as_dict["boundaries"]),
        baseline_results={
            name: BaselineResult(
                metrics=MetricSet(**payload["metrics"]),
                dm_result=(
                    DMResult(**payload["dm_result"]) if payload["dm_result"] is not None else None
                ),
            )
            for name, payload in as_dict["baseline_results"].items()
        },
    )

    assert rebuilt == original
    assert dataclasses.asdict(rebuilt) == as_dict
