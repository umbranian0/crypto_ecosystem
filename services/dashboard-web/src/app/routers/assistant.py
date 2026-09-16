"""AI-003: natural-language Q&A over a tenant's own stored run data.

New, dedicated router module (`operator.py`/`settings.py`'s "one fresh module
per distinct concern" convention) -- the model call lives only in
`POST /assistant/ask` below, never retrofitted onto `runs.py`'s existing
routes (ADR-0011's unsafe-extension-point list).

`GET /assistant` renders the question form (`assistant.html`); it depends on
`DownstreamHeadersDep` (redirect-to-`/login` for an anonymous visitor) even
though it makes no downstream call itself, since the feature is tenant-scoped
and gated behind the same nav-link convention every other authenticated route
uses.

`POST /assistant/ask` makes exactly the fixed 0-3-call retrieval
(`app.assistant.retrieval.fetch_context`, reusing `runs.py`'s
`_call_downstream`) plus one model call (`app.assistant.generation
.answer_question`, via `libs/ai_assist`'s `get_assist_client()` -- imported,
not reimplemented, AI-003-REFACTOR). `get_assist_client()` itself returns
`None` for an unconfigured deployment rather than raising, and
`answer_question` never lets `AssistClientError`/a banned-term/out-of-scope
question reach the caller as an exception -- so this route can never raise or
hang beyond the same bounded `httpx` timeout `libs/ai_assist`'s client
already enforces. Renders `_assistant_answer.html`, the HTMX-swapped fragment
`assistant.html`'s form targets (same pattern `_crawl_trigger_result.html`/
`_report_trigger_result.html` established, DASH-110).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Form, Request
from naive_first_ai_assist.client import get_assist_client

from app.assistant.generation import answer_question
from app.assistant.retrieval import fetch_context
from app.dependencies.downstream import DownstreamHeadersDep, GatewayApiUrlDep
from app.dependencies.http_client import DOWNSTREAM_HTTP_TIMEOUT_SECONDS
from app.main import templates

router = APIRouter()


@router.get("/assistant")
def assistant_form(request: Request, headers: DownstreamHeadersDep):
    return templates.TemplateResponse(request, "assistant.html", {})


@router.post("/assistant/ask")
def assistant_ask(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    question: str = Form(""),
):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        context = fetch_context(client, headers, base_url)

    answer = answer_question(question, context, get_assist_client())

    return templates.TemplateResponse(request, "_assistant_answer.html", {"answer": answer})
