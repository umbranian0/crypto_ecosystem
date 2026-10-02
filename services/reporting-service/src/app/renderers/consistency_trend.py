"""RPT-002-02: `ConsistencyTrendRenderer` -- an archivable snapshot of "beat
Naive0 in N of M completed runs" for one (dataset_id, horizon) group.

The majority rule and the per-split categorisation live only in
`naive_first_common.consistency` (shared with dashboard-web); this module
calls them and renders their results. Nothing is recomputed here.
"""

from __future__ import annotations

from naive_first_common.consistency import (
    UNDEFINED_VERDICT_CATEGORY,
    compute_consistency_indicator,
    run_beats_naive0,
    verdict_category,
)
from naive_first_common.contracts import RunSummaryResponse, SplitResultResponse
from naive_first_common.disclosures import (
    METHODOLOGY_FACTS,
    METHODOLOGY_INTRO,
    NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE,
)

from app.renderers.base import TrendReportRenderer
from app.renderers.jinja_env import env

_OUTCOME_LABELS = {True: "beat Naive0", False: "did not beat Naive0", None: "not evaluable"}


def _split_counts(splits: list[SplitResultResponse]) -> dict[str, int]:
    categories = [verdict_category(split) for split in splits]
    return {
        "better": categories.count("better"),
        "worse": categories.count("worse"),
        "undefined": categories.count(UNDEFINED_VERDICT_CATEGORY),
        "no_significant": sum(
            1 for c in categories if c not in ("better", "worse", UNDEFINED_VERDICT_CATEGORY)
        ),
    }


class ConsistencyTrendRenderer(TrendReportRenderer):
    def render(
        self,
        dataset_id: str,
        horizon: int,
        runs_with_splits: list[tuple[RunSummaryResponse, list[SplitResultResponse]]],
    ) -> str:
        indicator = compute_consistency_indicator(runs_with_splits)
        rows = [
            {
                "run": run,
                "outcome": _OUTCOME_LABELS[run_beats_naive0(splits)],
                "counts": _split_counts(splits),
            }
            for run, splits in runs_with_splits
        ]
        return env.get_template("consistency_trend.html.jinja").render(
            dataset_id=dataset_id,
            horizon=horizon,
            indicator=indicator,
            rows=rows,
            methodology_facts=METHODOLOGY_FACTS,
            methodology_intro=METHODOLOGY_INTRO,
            not_beating_naive_note=NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE,
        )
