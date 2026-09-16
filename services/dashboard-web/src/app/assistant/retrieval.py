"""AI-003: the fixed, reviewable 0-3-call retrieval pattern the backlog
requires (ticket Design section) -- no loop, no per-question-content
branching that could grow the call count.

Reuses `app.routers.runs`'s `_call_downstream` (transport-failure
translation) rather than a fourth near-identical try/except (ticket's own
DRY check note).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from naive_first_common.contracts import (
    RunDetailResponse,
    RunSummaryResponse,
    SplitResultResponse,
)

from app.routers.runs import _call_downstream

_RECENT_RUNS_LIMIT = 10


@dataclass
class AssistantContext:
    runs: list[RunSummaryResponse] = field(default_factory=list)
    detail: RunDetailResponse | None = None
    splits: list[SplitResultResponse] = field(default_factory=list)


def fetch_context(
    client: httpx.Client, headers: dict[str, str], base_url: str
) -> AssistantContext:
    """Exactly three bounded calls at most: `GET /runs?limit=10`, then, only
    for the single most recent run in that list (if any), `GET /runs/{id}`
    and `GET /runs/{id}/splits` -- zero calls beyond `GET /runs` if the
    tenant has no runs yet. `base_url` is accepted for signature parity with
    the ticket's Design section; `client` is already bound to it the same way
    every other route in this service constructs its `httpx.Client`.
    """
    response, transport_status = _call_downstream(
        client.get, "/runs", headers=headers, params={"limit": _RECENT_RUNS_LIMIT}
    )
    if transport_status is not None or response.status_code != 200:
        return AssistantContext()

    runs = [RunSummaryResponse(**item) for item in response.json()["items"]]
    if not runs:
        return AssistantContext()

    most_recent = runs[0]

    detail_response, detail_transport_status = _call_downstream(
        client.get, f"/runs/{most_recent.id}", headers=headers
    )
    detail = (
        RunDetailResponse(**detail_response.json())
        if detail_transport_status is None and detail_response.status_code == 200
        else None
    )

    splits_response, splits_transport_status = _call_downstream(
        client.get, f"/runs/{most_recent.id}/splits", headers=headers
    )
    splits = (
        [SplitResultResponse(**item) for item in splits_response.json()]
        if splits_transport_status is None and splits_response.status_code == 200
        else []
    )

    return AssistantContext(runs=runs, detail=detail, splits=splits)
