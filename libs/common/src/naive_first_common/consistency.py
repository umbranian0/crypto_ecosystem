"""The "beat Naive0 in N of M" consistency rule (RAV-010, extracted by RPT-002-01).

Counts, from already-computed `dm_verdict` values only, how many runs beat
Naive0 by a documented majority rule. No DM statistic is recomputed here --
the Harvey-corrected test already ran upstream in `naive_first_engine`.
Shared by `dashboard-web` and `reporting-service` so the rule has exactly one
implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

from naive_first_common.contracts import SplitResultResponse

UNDEFINED_VERDICT_CATEGORY = "undefined for this split"


def verdict_category(split: SplitResultResponse) -> str:
    """Maps one split's existing `dm_verdict` field to one of the four chart
    categories, verbatim -- no recomputation of the verdict here, that
    already ran upstream in `naive_first_engine`/`validation-service`. The
    `None`/`None` case (a single-test-point split's genuinely undefined DM
    statistic, per `SplitResultResponse`'s own docstring) always maps to
    `UNDEFINED_VERDICT_CATEGORY`, regardless of whatever string `dm_verdict`
    happens to hold for that row -- it must never be silently dropped or
    merged into "no significant difference".
    """
    if split.dm_statistic is None and split.dm_pvalue is None:
        return UNDEFINED_VERDICT_CATEGORY
    return split.dm_verdict


@dataclass(frozen=True)
class ConsistencyIndicator:
    """`has_data` distinguishes "zero runs matched the selection" from a
    genuine "0 of 0" -- the route must render a plain "no data" message in
    the former case, never a fabricated ratio (this ticket's Implementation
    acceptance criteria).
    """

    beat_count: int
    total_count: int
    has_data: bool


def run_beats_naive0(splits: list[SplitResultResponse]) -> bool | None:
    """Majority rule (this ticket's Analysis section, documented explicitly
    per its own instruction): a run counts as having beaten Naive0 if strictly
    more of its splits fall in the "better" category than in "worse" and "no
    significant difference" *combined*. Splits whose DM statistic is
    genuinely undefined (`UNDEFINED_VERDICT_CATEGORY`, via `verdict_category`
    -- RAV-003's None/None rule) are excluded from both sides of that count,
    never counted as "worse"/"no significant difference" by default, per this
    ticket's Design section. A run with no split available for the count (all
    splits undefined, or zero splits) returns `None` -- it does not count
    toward `beat_count` or `total_count`, since there is nothing to evaluate
    a majority over.
    """
    better = 0
    other = 0
    for split in splits:
        category = verdict_category(split)
        if category == UNDEFINED_VERDICT_CATEGORY:
            continue
        if category == "better":
            better += 1
        else:
            other += 1
    if better + other == 0:
        return None
    return better > other


def compute_consistency_indicator(
    runs: list[tuple[object, list[SplitResultResponse]]],
) -> ConsistencyIndicator:
    """Counts, across the caller's already-`completed`-filtered, already-
    fetched `(run, splits)` pairs (RAV-009's own trend-view fetch -- no second
    `GET /runs/{id}/splits` call here), how many runs had a majority
    "better"-than-Naive0 verdict across their own splits, per
    `run_beats_naive0`'s documented rule.

    An empty `runs` list, or a `runs` list where every run has no evaluable
    split (all splits `UNDEFINED_VERDICT_CATEGORY`, or zero splits), returns
    `has_data=False` -- the route/template must render "no completed runs
    matched this selection" rather than a fabricated "0 of 0" (this ticket's
    Implementation acceptance criteria).
    """
    beat_count = 0
    total_count = 0
    for _run, splits in runs:
        result = run_beats_naive0(splits)
        if result is None:
            continue
        total_count += 1
        if result:
            beat_count += 1

    return ConsistencyIndicator(
        beat_count=beat_count,
        total_count=total_count,
        has_data=total_count > 0,
    )
