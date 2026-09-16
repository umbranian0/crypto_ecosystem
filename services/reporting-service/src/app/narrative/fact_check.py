"""AI-002: post-generation fact-check validator (ticket Design section,
backlog AC3/AC4). A guardrail, not a full NLU fact-checker -- both functions
below are deliberately simple, deterministic, testable heuristics over the
model's raw text output, run before that text ever reaches the renderer
(`app.narrative.generation.generate_narrative_html`).

Known scope/limits (disclosed, not fixed here):
- `contains_banned_term` is a fixed-list, case-insensitive substring check.
  It will not catch a banned concept phrased without one of the listed
  words, and it may (rarely) flag a banned word used as a harmless
  substring of an unrelated word (e.g. "profitable" contains "profit" --
  treated as a hit deliberately, since "profitable" is exactly the kind of
  economic-value claim CLAUDE.md's core-finding section says this service
  must never make).
- `is_directionally_consistent` only checks one specific, well-known failure
  mode this ticket calls out explicitly: the narrative asserting the model
  "beat"/"outperformed" naive when no split's real DM verdict says
  "better". It does not attempt to verify every other claim the narrative
  might make (e.g. a fabricated number) -- that is out of scope for a
  guardrail this simple, and is exactly why graceful degradation
  (`app.narrative.generation`) exists as the backstop for anything this
  heuristic doesn't catch. A simple negation check (`_NEGATED_BEAT_PATTERN`,
  "not beat"/"not outperform" within a few words) prevents "the model did
  not beat naive" from being misread as a positive claim -- it will not
  catch every possible negation phrasing (e.g. "failed to beat" isn't
  matched), which is exactly the kind of gap graceful degradation exists to
  backstop, not a claim this heuristic is complete.
"""

from __future__ import annotations

import re

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

BANNED_TERMS = ("signal", "buy", "sell", "profit", "trade", "recommendation")

_BEAT_NAIVE_PATTERN = re.compile(
    r"\b(beat|beats|beating|outperform|outperforms|outperformed|outperforming)\b"
    r".{0,40}\bnaive\b",
    re.IGNORECASE,
)
_NAIVE_BEAT_MODEL_PATTERN = re.compile(
    r"\bnaive\b.{0,40}\b(beat|beats|beating|outperform|outperforms|outperformed|outperforming)\b",
    re.IGNORECASE,
)
_NEGATED_BEAT_PATTERN = re.compile(
    r"\bnot\b.{0,10}\b(beat|beats|beating|outperform|outperforms|outperformed|outperforming)\b",
    re.IGNORECASE,
)


def contains_banned_term(text: str) -> str | None:
    """Returns the first banned term found (case-insensitive substring
    match) in `text`, or `None` if none are present.
    """
    lowered = text.lower()
    for term in BANNED_TERMS:
        if term in lowered:
            return term
    return None


def is_directionally_consistent(
    text: str, run: RunDetailResponse, splits: list[SplitResultResponse]
) -> bool:
    """`False` iff `text` asserts the model beat/outperformed naive
    (`_BEAT_NAIVE_PATTERN`) while no split's real `dm_verdict` is `"better"`
    -- the exact contradiction the ticket's Test acceptance criteria names.
    A claim that naive beat the model (`_NAIVE_BEAT_MODEL_PATTERN`) is never
    flagged as inconsistent, since that direction can't misrepresent this
    module's core finding (CLAUDE.md).
    """
    claims_model_beat_naive = (
        bool(_BEAT_NAIVE_PATTERN.search(text))
        and not bool(_NAIVE_BEAT_MODEL_PATTERN.search(text))
        and not bool(_NEGATED_BEAT_PATTERN.search(text))
    )
    if not claims_model_beat_naive:
        return True

    any_split_better = any(split.dm_verdict == "better" for split in splits)
    return any_split_better
