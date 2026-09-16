"""AI-004-01: versioned, checked-in prompt template for the conversational
configure-run helper (ticket Design section) -- mirrors `prompt_template.py`'s
"versioned, checked-in template, only fields already available to this route"
convention.

`build_configure_run_prompt` only ever references the tenant's free-text
answer already passed into `POST /assistant/configure-run` -- no new data
source. The model is only ever asked about, and may only suggest, exactly the
six fields this story is scoped to: `horizon`, `purge_gap_hours`,
`train_window`, `test_window`, `step`, `label`. `dataset_id` and
`dataset_reference_*` are explicitly NOT suggested -- the model has no
knowledge of the tenant's actual ingested datasets, so suggesting a
`dataset_id`/source would be a fabricated claim (ticket Design section).
"""

from __future__ import annotations

CONFIGURE_RUN_PROMPT_VERSION = "v1"

_ALLOWED_FIELDS_LINE = "horizon, purge_gap_hours, train_window, test_window, step, label"

_INSTRUCTIONS = (
    "You are helping one tenant fill in the configuration for a new leakage-aware, "
    "purged walk-forward validation run for a Bitcoin return-prediction model, "
    "benchmarked against a naive baseline (Naive0).\n"
    "Rules:\n"
    "- You may only suggest values for exactly these fields: "
    f"{_ALLOWED_FIELDS_LINE}. Never suggest a dataset id or data source -- you have "
    "no knowledge of the tenant's actual ingested datasets.\n"
    "- Never suggest disabling, omitting, or shortening the purge gap. The purge gap "
    "is a leakage-prevention control and must always be present.\n"
    "- Never suggest omitting the naive baselines. Every run must always be "
    "benchmarked against the naive baselines.\n"
    "- Do not use any of these words: signal, buy, sell, profit, trade, "
    "recommendation. Do not recommend any action.\n"
    "- Never claim that a specific value is \"optimal\", \"best\", or \"correct\". "
    "Suggestions are starting points for the tenant to confirm, not certainties.\n"
    "- Respond with one line per suggested field, in the fixed format "
    "'field: value', for example 'horizon: 24'. Do not include any other text."
)


def build_configure_run_prompt(answer: str) -> str:
    lines = [_INSTRUCTIONS, "", f"Tenant's description of what they want to validate: {answer}"]
    return "\n".join(lines)
