"""ADMIN-002-01: operator-only `GET /operator-audit-log`, the read half of
this ticket's audit trail (the write half lives in `tenants.py`'s
`create_tenant`/`revoke_api_key`).

Deliberately a new module (same "one disjoint module per distinct concern"
precedent `tenants.py`/`diagnostics.py` both already state in their own
docstrings).

Gated by `get_authenticated_operator` (SETUP-010's existing gate -- the
exact one `ADMIN-002-02`'s `dashboard-web` page already expects), never a
new auth mechanism. `limit`/`offset` default to `20`/`0`, matching
`GET /runs`'s own defaults (same pagination convention, per the backlog
AC's own "same convention" instruction).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.dependencies.operator_auth import get_authenticated_operator
from app.dependencies.repositories import OperatorAuditLogRepositoryDep

router = APIRouter()


class OperatorAuditLogEntryResponse(BaseModel):
    id: str
    action: str
    target_tenant_id: str | None
    correlation_id: str
    at: datetime


class OperatorAuditLogListResponse(BaseModel):
    items: list[OperatorAuditLogEntryResponse]
    limit: int
    offset: int
    total: int


@router.get("/operator-audit-log")
def list_operator_audit_log(
    audit_log_repository: OperatorAuditLogRepositoryDep,
    _operator: None = Depends(get_authenticated_operator),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
) -> OperatorAuditLogListResponse:
    entries, total = audit_log_repository.list_entries(limit, offset)
    items = [
        OperatorAuditLogEntryResponse(
            id=entry.id,
            action=entry.action,
            target_tenant_id=entry.target_tenant_id,
            correlation_id=entry.correlation_id,
            at=entry.at,
        )
        for entry in entries
    ]
    return OperatorAuditLogListResponse(items=items, limit=limit, offset=offset, total=total)
