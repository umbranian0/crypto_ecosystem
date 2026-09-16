"""AI-003-REFACTOR: this module is now a thin backward-compatible re-export
of `naive_first_ai_assist.client` -- the `NarrativeClient`/`NarrativeClientError`/
`HostedApiNarrativeClient`/`get_narrative_client` names AI-002 originally
shipped here now alias the shared `libs/ai_assist` Adapter, so every existing
import site (`app.narrative.generation`, `app.subscriber`) and every existing
test under `tests/narrative/` keeps working unmodified. See
`libs/ai_assist/README.md` and `docs/tickets/AI-003-refactor-ai-assist.md`
for why this was extracted.
"""

from __future__ import annotations

from naive_first_ai_assist.client import (
    AssistClient as NarrativeClient,
    AssistClientError as NarrativeClientError,
    HostedApiAssistClient as HostedApiNarrativeClient,
    get_assist_client as get_narrative_client,
)

__all__ = [
    "NarrativeClient",
    "NarrativeClientError",
    "HostedApiNarrativeClient",
    "get_narrative_client",
]
