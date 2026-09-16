"""naive_first_ai_assist: shared hosted-AI-model client Adapter (AI-003-REFACTOR).

See README.md for owns/does-not-own boundary and the ADR-0011 serving-pattern
rationale.
"""

from __future__ import annotations

from naive_first_ai_assist.client import (
    AssistClient,
    AssistClientError,
    HostedApiAssistClient,
    get_assist_client,
)

__all__ = [
    "AssistClient",
    "AssistClientError",
    "HostedApiAssistClient",
    "get_assist_client",
]
