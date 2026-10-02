"""ONB-002: "Try a demo run" -- `GET`/`POST /demo-run`.

Submits one fixed, illustrative validation run against the tenant's sample
price dataset so a new tenant can see the protocol mechanics end to end. The
target is hourly traded volume, not a return series: stored price levels are
rejected by validation-service's returns guardrail. Reuses the submit/error
helpers from `app.routers.runs`; no new downstream endpoint.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from naive_first_common.contracts import RunRequest, RunResponse

from app.dependencies.downstream import DownstreamHeadersDep, GatewayApiUrlDep
from app.dependencies.http_client import DOWNSTREAM_HTTP_TIMEOUT_SECONDS
from app.main import templates
from app.routers.runs import (
    _call_downstream,
    _fetch_ingestion_datasets,
    _render_error_for_status,
)

router = APIRouter()

DEMO_SOURCE = "binance_price_btcusdt_1h"
DEMO_FIELD = "volume"
DEMO_START = "2024-01-01T00:00:00"
DEMO_END = "2024-03-01T00:00:00"
DEMO_LABEL = "Demo run: demo configuration -- not a recommended default for your own data"

DEMO_RUN_REQUEST = RunRequest(
    dataset_id=f"demo-{DEMO_SOURCE}-{DEMO_FIELD}",
    dataset_reference={
        "source": DEMO_SOURCE,
        "field": DEMO_FIELD,
        "start": DEMO_START,
        "end": DEMO_END,
    },
    horizon=1,
    purge_gap_hours=24,
    train_window=500,
    test_window=100,
    step=100,
    label=DEMO_LABEL,
)

_SAMPLE_DATA_MISSING_MESSAGE = (
    "Sample data is not loaded for this tenant. Ask your operator to seed it."
)


def _render_page(request: Request, *, available: bool, message: str | None = None):
    return templates.TemplateResponse(
        request,
        "demo_run.html",
        {"demo": DEMO_RUN_REQUEST, "available": available, "message": message},
    )


@router.get("/demo-run")
def demo_run_form(request: Request, headers: DownstreamHeadersDep):
    return _render_page(request, available=True)


@router.post("/demo-run")
def demo_run_submit(
    request: Request, headers: DownstreamHeadersDep, base_url: GatewayApiUrlDep
):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        datasets = _fetch_ingestion_datasets(client, headers)
        if not any(d.source == DEMO_SOURCE for d in datasets):
            return _render_page(
                request, available=False, message=_SAMPLE_DATA_MISSING_MESSAGE
            )

        response, transport_status = _call_downstream(
            client.post, "/runs", json=DEMO_RUN_REQUEST.model_dump(), headers=headers
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code >= 300:
            return _render_error_for_status(request, response.status_code)

        run = RunResponse(**response.json())

    return RedirectResponse(url=f"/runs/{run.id}", status_code=303)
