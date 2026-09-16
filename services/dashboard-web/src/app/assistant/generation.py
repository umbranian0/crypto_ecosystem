"""AI-003: `answer_question` -- builds the prompt, checks the out-of-scope
refusal gate *before* any model call, calls the model (mirrors
`reporting-service`'s `generate_narrative_html` one-retry-then-fallback
shape), runs the banned-term gate on the result, and always appends a
deterministic citation footer built from the real retrieved run/split ids
(never trusted to the model's own generated text) -- so the citation
acceptance criterion holds by construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from naive_first_ai_assist.client import AssistClient, AssistClientError

from app.assistant.fact_check import contains_banned_term, is_out_of_scope
from app.assistant.prompt_template import build_prompt
from app.assistant.retrieval import AssistantContext

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2

_NO_DATA_TEXT = "You have no recorded validation runs yet, so there is nothing to summarize."
_UNAVAILABLE_TEXT = "The assistant is currently unavailable. Please try again shortly."
_OUT_OF_SCOPE_TEXT = (
    "This assistant explains your own stored validation run history -- it does not "
    "predict prices or markets, so it can't answer that question."
)
_NO_SOURCES_FOOTER = "Sources: none (you have no recorded validation runs yet)"


@dataclass
class AssistantAnswer:
    text: str
    citations: list[str]
    degraded: bool


def _build_citations(context: AssistantContext) -> list[str]:
    if context.detail is None:
        return []
    citations = [f"run {context.detail.id}"]
    citations.extend(f"split {split.split_index}" for split in context.splits)
    return citations


def _citation_footer(citations: list[str]) -> str:
    if not citations:
        return _NO_SOURCES_FOOTER
    return "Sources: " + ", ".join(citations)


def answer_question(
    question: str, context: AssistantContext, client: AssistClient | None
) -> AssistantAnswer:
    if is_out_of_scope(question):
        return AssistantAnswer(text=_OUT_OF_SCOPE_TEXT, citations=[], degraded=False)

    if context.detail is None:
        return AssistantAnswer(text=_NO_DATA_TEXT, citations=[], degraded=False)

    citations = _build_citations(context)
    footer = _citation_footer(citations)

    if client is None:
        return AssistantAnswer(text=_UNAVAILABLE_TEXT, citations=[], degraded=True)

    prompt = build_prompt(question, context.runs, context.detail, context.splits)

    for attempt in range(_MAX_ATTEMPTS):
        try:
            text = client.generate(prompt)
        except AssistClientError as exc:
            logger.warning(
                "assistant model call failed (attempt %d/%d): %s",
                attempt + 1,
                _MAX_ATTEMPTS,
                exc,
            )
            continue

        banned = contains_banned_term(text)
        if banned is None:
            return AssistantAnswer(
                text=f"{text}\n\n{footer}", citations=citations, degraded=False
            )
        logger.warning("assistant answer rejected: banned term %r", banned)

    return AssistantAnswer(text=_UNAVAILABLE_TEXT, citations=[], degraded=True)
