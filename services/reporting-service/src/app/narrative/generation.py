"""AI-002: `generate_narrative_html` -- builds the prompt, calls the model,
runs both fact-check gates, and never raises out to its caller (ticket
Design section). `None` means "no narrative" -- not an exception, so
`app.generation.generate_validation_audit_report` can treat "narrative
generation didn't work out" and "no narrative client configured" identically.
"""

from __future__ import annotations

import logging

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.narrative.client import NarrativeClient, NarrativeClientError
from app.narrative.fact_check import contains_banned_term, is_directionally_consistent
from app.narrative.prompt_template import build_prompt

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2


def _is_acceptable(text: str, run: RunDetailResponse, splits: list[SplitResultResponse]) -> bool:
    banned = contains_banned_term(text)
    if banned is not None:
        logger.warning("narrative generation rejected: banned term %r", banned)
        return False
    if not is_directionally_consistent(text, run, splits):
        logger.warning(
            "narrative generation rejected for run %s: directionally inconsistent with "
            "real DM verdicts",
            run.id,
        )
        return False
    return True


def generate_narrative_html(
    run: RunDetailResponse,
    splits: list[SplitResultResponse],
    client: NarrativeClient,
) -> str | None:
    """Fed only `run`/`splits` (the same already-persisted fields the table
    renders, no new data source). Regenerates once (`_MAX_ATTEMPTS`) if the
    fact-check gates reject the first attempt, then falls back to `None`
    rather than ever shipping a rejected paragraph.
    """
    prompt = build_prompt(run, splits)

    for attempt in range(_MAX_ATTEMPTS):
        try:
            text = client.generate(prompt)
        except NarrativeClientError as exc:
            logger.warning(
                "narrative model call failed for run %s (attempt %d/%d): %s",
                run.id,
                attempt + 1,
                _MAX_ATTEMPTS,
                exc,
            )
            continue

        if _is_acceptable(text, run, splits):
            return text

    return None
