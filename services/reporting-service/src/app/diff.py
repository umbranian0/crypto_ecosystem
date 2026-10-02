"""RPT-004-01: pure field-level diff of two runs' per-split result values.

No I/O and no recomputation: every value is read verbatim from validation-
service's already-computed split rows (DM values are the existing Harvey-
adjusted ones). `delta` is `other - base`, a neutral arithmetic difference;
nothing here ranks, scores, or interprets a delta. The only summary is the
number of splits whose Naive0 comparison verdict category differs.
"""

from __future__ import annotations

from naive_first_common.consistency import verdict_category
from naive_first_common.contracts import RunDetailResponse, SplitResultResponse
from pydantic import BaseModel

_METRICS = ("mae", "rmse", "smape", "mase", "da", "f1", "oos_r2")
DIFFED_FIELDS: tuple[str, ...] = (
    *(f"model_{m}" for m in _METRICS),
    *(f"naive0_{m}" for m in _METRICS),
    "dm_statistic",
    "dm_pvalue",
)


class FieldDelta(BaseModel):
    base: float | None
    other: float | None
    delta: float | None


class VerdictComparison(BaseModel):
    base: str
    other: str
    changed: bool


class SplitDiff(BaseModel):
    split_index: int
    metrics: dict[str, FieldDelta]
    dm_verdict: VerdictComparison


class ReportDiffResponse(BaseModel):
    report_id: str
    other_report_id: str
    run_id: str
    other_run_id: str
    dataset_id: str
    horizon: int
    split_count: int
    verdict_changed_split_count: int
    splits: list[SplitDiff]


def comparability_failure(base: RunDetailResponse, other: RunDetailResponse) -> str | None:
    """Run-level rules (2)-(4); the first failing rule's plain reason, else None."""
    if base.dataset_id != other.dataset_id:
        return "runs use different datasets"
    if base.horizon != other.horizon:
        return "runs use different horizons"
    if base.purge_gap_hours != other.purge_gap_hours or base.split_config != other.split_config:
        return "runs use different split configurations"
    return None


def alignment_failure(
    base: list[SplitResultResponse], other: list[SplitResultResponse]
) -> str | None:
    """Rule (6): identical split_index sets and identical test windows."""
    base_by_index = {s.split_index: s for s in base}
    other_by_index = {s.split_index: s for s in other}
    if base_by_index.keys() != other_by_index.keys():
        return "runs have different split sets"
    for index, split in base_by_index.items():
        o = other_by_index[index]
        if split.test_start != o.test_start or split.test_end != o.test_end:
            return "runs have different test windows for the same split"
    return None


def _delta(base: float | None, other: float | None) -> FieldDelta:
    delta = None if base is None or other is None else other - base
    return FieldDelta(base=base, other=other, delta=delta)


def diff_splits(
    base: list[SplitResultResponse], other: list[SplitResultResponse]
) -> list[SplitDiff]:
    """Assumes `alignment_failure` already returned None for these inputs."""
    other_by_index = {s.split_index: s for s in other}
    result: list[SplitDiff] = []
    for split in sorted(base, key=lambda s: s.split_index):
        o = other_by_index[split.split_index]
        base_category = verdict_category(split)
        other_category = verdict_category(o)
        result.append(
            SplitDiff(
                split_index=split.split_index,
                metrics={
                    name: _delta(getattr(split, name), getattr(o, name)) for name in DIFFED_FIELDS
                },
                dm_verdict=VerdictComparison(
                    base=base_category,
                    other=other_category,
                    changed=base_category != other_category,
                ),
            )
        )
    return result
