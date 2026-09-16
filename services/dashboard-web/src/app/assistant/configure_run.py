"""AI-004-01: `generate_run_suggestions` -- builds the prompt, calls the model
(mirrors `generation.py`'s one-retry-then-fallback shape, `_MAX_ATTEMPTS = 2`),
runs both `contains_banned_term` and `contains_overstated_certainty_claim` on
the raw model text before parsing, and falls back to `degraded=True` with an
empty suggestion list rather than raising or hanging.

`parse_suggestion_lines` enforces the fixed allowed-field set in code (never
just documented in the prompt) -- any line for a field outside `horizon`,
`purge_gap_hours`, `train_window`, `test_window`, `step`, `label` is silently
dropped, in particular `dataset_id`/`dataset_reference_*`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from naive_first_ai_assist.client import AssistClient, AssistClientError

from app.assistant.configure_run_prompt import build_configure_run_prompt
from app.assistant.fact_check import contains_banned_term, contains_overstated_certainty_claim

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2

ALLOWED_FIELDS = frozenset(
    {"horizon", "purge_gap_hours", "train_window", "test_window", "step", "label"}
)


@dataclass
class RunFieldSuggestion:
    field: str
    value: str
    explanation: str


@dataclass
class ConfigureRunResult:
    suggestions: list[RunFieldSuggestion] = field(default_factory=list)
    degraded: bool = False


def parse_suggestion_lines(text: str) -> list[RunFieldSuggestion]:
    """Parses the fixed `field: value` format, silently dropping any line for
    a field outside `ALLOWED_FIELDS` or any malformed line -- never lets the
    model introduce an unexpected field name into the response.
    """
    suggestions: list[RunFieldSuggestion] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        field_name, _, value = stripped.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()
        if field_name not in ALLOWED_FIELDS or not value:
            continue
        suggestions.append(
            RunFieldSuggestion(
                field=field_name,
                value=value,
                explanation="Suggested value based on your answer, please confirm.",
            )
        )
    return suggestions


def generate_run_suggestions(answer: str, client: AssistClient | None) -> ConfigureRunResult:
    if client is None:
        return ConfigureRunResult(suggestions=[], degraded=True)

    prompt = build_configure_run_prompt(answer)

    for attempt in range(_MAX_ATTEMPTS):
        try:
            text = client.generate(prompt)
        except AssistClientError as exc:
            logger.warning(
                "configure-run model call failed (attempt %d/%d): %s",
                attempt + 1,
                _MAX_ATTEMPTS,
                exc,
            )
            continue

        banned = contains_banned_term(text)
        if banned is not None:
            logger.warning("configure-run suggestion rejected: banned term %r", banned)
            continue

        overstated = contains_overstated_certainty_claim(text)
        if overstated is not None:
            logger.warning(
                "configure-run suggestion rejected: overstated certainty term %r", overstated
            )
            continue

        return ConfigureRunResult(suggestions=parse_suggestion_lines(text), degraded=False)

    return ConfigureRunResult(suggestions=[], degraded=True)
