"""SETUP-021: `GET /diagnostics/recent-errors` -- operator-gated read of this
service's own in-process ring buffer of recent WARNING+ log records.

No tags= (ARCH-007, same reasoning as `setup.router`/`system.router`/
`tenants.router`): this router doesn't proxy to a single downstream service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies.diagnostics import RecentErrorsHandlerDep
from app.dependencies.operator_auth import get_authenticated_operator

router = APIRouter()


class RecentErrorsResponse(BaseModel):
    items: list[dict[str, str]]


@router.get("/diagnostics/recent-errors")
def recent_errors(
    handler: RecentErrorsHandlerDep,
    _operator: None = Depends(get_authenticated_operator),
) -> RecentErrorsResponse:
    return RecentErrorsResponse(items=handler.snapshot())
