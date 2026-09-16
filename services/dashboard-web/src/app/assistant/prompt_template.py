"""AI-003: versioned, checked-in prompt template (ticket Design section) --
mirrors `reporting-service`'s `app.narrative.prompt_template` shape one hop
over, not copied verbatim (this module answers a free-text tenant question
about their own run history, that one summarizes one specific run).

`build_prompt` only ever references fields already fetched by
`app.assistant.retrieval.fetch_context` (`RunSummaryResponse`/
`RunDetailResponse`/`SplitResultResponse` fields) -- no new data source, same
"no new data source, only already-fetched fields" discipline as
reporting-service's own template.
"""

from __future__ import annotations

from naive_first_common.contracts import (
    RunDetailResponse,
    RunSummaryResponse,
    SplitResultResponse,
)

PROMPT_TEMPLATE_VERSION = "v1"

_INSTRUCTIONS = (
    "You are answering one tenant's question about their own stored, leakage-aware, "
    "purged walk-forward validation run history for a Bitcoin return-prediction "
    "model, benchmarked against a naive baseline (Naive0). Answer in 2-4 plain-"
    "language sentences, using only the facts given below.\n"
    "Rules:\n"
    "- State only claims directly supported by the run/split data given below. "
    "Never invent a number, run id, or claim not derivable from them.\n"
    "- Do not use any of these words: signal, buy, sell, profit, trade, "
    "recommendation. Do not recommend any action.\n"
    "- Never predict or speculate about future prices or future returns -- this "
    "assistant explains backward-looking validation results only, never a "
    "forecast."
)


def _split_line(split: SplitResultResponse) -> str:
    return (
        f"- Split {split.split_index}: DM verdict={split.dm_verdict!r}, "
        f"model MAE={split.model_mae}, naive0 MAE={split.naive0_mae}"
    )


def build_prompt(
    question: str,
    runs: list[RunSummaryResponse],
    detail: RunDetailResponse | None,
    splits: list[SplitResultResponse],
) -> str:
    lines = [_INSTRUCTIONS, "", f"Tenant question: {question}", ""]

    if detail is None:
        lines.append("The tenant has no recorded validation runs.")
        return "\n".join(lines)

    lines.extend(
        [
            f"Total runs on record: {len(runs)}",
            f"Most recent run id: {detail.id}",
            f"Dataset: {detail.dataset_id}",
            f"Horizon: {detail.horizon}",
            f"Status: {detail.status}",
            "Per-split results for the most recent run:",
        ]
    )
    lines.extend(_split_line(split) for split in splits)

    return "\n".join(lines)
