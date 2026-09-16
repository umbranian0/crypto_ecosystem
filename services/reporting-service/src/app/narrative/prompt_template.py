"""AI-002: versioned, checked-in prompt template (ticket Design section,
backlog AC2) -- not a hidden runtime string.

`build_prompt` only ever references `run`/`splits` fields already rendered
by `templates/validation_audit.html.jinja` (`run.id`/`run.dataset_id`/
`run.horizon`/`run.purge_gap_hours`/`split.dm_verdict`/`split.model_*`/
`split.naive0_*` etc.) -- no new data source, no raw tenant upload content.

The model must never be asked to invent a claim this run's own numbers don't
support, and must avoid every term this service's banned-term test checks
for (`app.narrative.fact_check.contains_banned_term`) -- this is a validation/
audit summary, not trading advice (CLAUDE.md "Product positioning").
"""

from __future__ import annotations

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

PROMPT_TEMPLATE_VERSION = "v1"

_INSTRUCTIONS = (
    "You are summarizing the results of one leakage-aware, purged walk-forward "
    "validation run for a Bitcoin return-prediction model, benchmarked against a "
    "naive baseline (Naive0). Write a short, plain-language paragraph (3-5 "
    "sentences) describing only what the numbers below actually show.\n"
    "Rules:\n"
    "- State only claims directly supported by the per-split Diebold-Mariano (DM) "
    "verdicts and metrics given below. Never invent a number or claim not derivable "
    "from them.\n"
    "- Do not use any of these words: signal, buy, sell, profit, trade, "
    "recommendation. Do not recommend any action.\n"
    "- Do not make any claim about future prices or future returns -- this is a "
    "backward-looking statistical accuracy summary only, not a forecast.\n"
    "- State plainly whether the model beat naive, and on how many of the splits "
    "evaluated, using the DM verdict counts given below (never re-derive your own "
    "verdict from raw metrics)."
)


def _split_line(split: SplitResultResponse) -> str:
    return (
        f"- Split {split.split_index}: DM verdict={split.dm_verdict!r}, "
        f"model MAE={split.model_mae}, naive0 MAE={split.naive0_mae}, "
        f"model RMSE={split.model_rmse}, naive0 RMSE={split.naive0_rmse}, "
        f"model DA={split.model_da}, naive0 DA={split.naive0_da}, "
        f"DM statistic={split.dm_statistic}, DM p-value={split.dm_pvalue}"
    )


def build_prompt(run: RunDetailResponse, splits: list[SplitResultResponse]) -> str:
    better_count = sum(1 for split in splits if split.dm_verdict == "better")
    worse_count = sum(1 for split in splits if split.dm_verdict == "worse")
    no_diff_count = sum(
        1 for split in splits if split.dm_verdict == "no significant difference"
    )

    lines = [
        _INSTRUCTIONS,
        "",
        f"Run id: {run.id}",
        f"Dataset: {run.dataset_id}",
        f"Horizon: {run.horizon}",
        f"Purge gap (hours): {run.purge_gap_hours}",
        f"Splits evaluated: {len(splits)}",
        f"DM verdict counts: {better_count} better, {worse_count} worse, "
        f"{no_diff_count} no significant difference",
        "Per-split results:",
    ]
    lines.extend(_split_line(split) for split in splits)

    return "\n".join(lines)
