"""ADMIN-005-02: tenant self-service API key rotation -- `GET/POST /me/api-keys`,
`POST /me/api-keys/{key_id}/revoke`.

The tenant id comes only from the authenticating key (`get_authenticated_key`),
never from a path/body parameter. No key hash or raw key appears in any
response except the one-time `api_key` in the `POST` 201 body.

Revoke order: 404 (key not in caller's tenant) -> 409 (it is the key
authenticating this request, so a request by a different working key is
required) -> guarded revoke (409 if it would leave zero active keys; atomic
in the repository). Audit rows (`api_key.self_*`, reusing `operator_audit_log`)
are written on every 200/201, including the already-revoked no-op, never on
404/409.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from naive_first_common.logging import correlation_id_var

from app.dependencies.auth import get_authenticated_key
from app.dependencies.repositories import ApiKeyRepositoryDep, OperatorAuditLogRepositoryDep
from app.provisioning import mint_api_key
from app.repositories.interfaces import LAST_ACTIVE, NOT_FOUND, ApiKeyRecord
from app.routers.tenants import ApiKeySummary

router = APIRouter()

CallerKey = Annotated[ApiKeyRecord, Depends(get_authenticated_key)]


class MyApiKeySummary(ApiKeySummary):
    current: bool


class MyApiKeyListResponse(BaseModel):
    items: list[MyApiKeySummary]


class MyApiKeyCreateResponse(BaseModel):
    id: str
    created_at: datetime
    api_key: str


class MyApiKeyRevokeResponse(BaseModel):
    key_id: str
    revoked_at: datetime


@router.get("/me/api-keys")
def list_my_api_keys(
    caller: CallerKey, api_key_repository: ApiKeyRepositoryDep
) -> MyApiKeyListResponse:
    return MyApiKeyListResponse(
        items=[
            MyApiKeySummary(
                id=key.id,
                created_at=key.created_at,
                revoked_at=key.revoked_at,
                current=key.id == caller.id,
            )
            for key in api_key_repository.list_api_keys(caller.tenant_id)
        ]
    )


@router.post("/me/api-keys", status_code=201)
def create_my_api_key(
    response: Response,
    caller: CallerKey,
    api_key_repository: ApiKeyRepositoryDep,
    audit_log_repository: OperatorAuditLogRepositoryDep,
) -> MyApiKeyCreateResponse:
    record, raw_key = mint_api_key(caller.tenant_id, api_key_repository)
    audit_log_repository.record("api_key.self_create", caller.tenant_id, correlation_id_var.get())
    response.headers["Cache-Control"] = "no-store"
    return MyApiKeyCreateResponse(id=record.id, created_at=record.created_at, api_key=raw_key)


@router.post("/me/api-keys/{key_id}/revoke")
def revoke_my_api_key(
    key_id: str,
    caller: CallerKey,
    api_key_repository: ApiKeyRepositoryDep,
    audit_log_repository: OperatorAuditLogRepositoryDep,
) -> MyApiKeyRevokeResponse:
    tenant_id = caller.tenant_id
    if not any(key.id == key_id for key in api_key_repository.list_api_keys(tenant_id)):
        raise HTTPException(status_code=404, detail="not found")
    if key_id == caller.id:
        raise HTTPException(
            status_code=409, detail="cannot revoke the key authenticating this request"
        )

    outcome = api_key_repository.revoke_key_if_not_last_active(tenant_id, key_id)
    if outcome == NOT_FOUND:
        raise HTTPException(status_code=404, detail="not found")
    if outcome == LAST_ACTIVE:
        raise HTTPException(status_code=409, detail="cannot revoke the last active key")

    matched = next(
        key for key in api_key_repository.list_api_keys(tenant_id) if key.id == key_id
    )
    audit_log_repository.record("api_key.self_revoke", tenant_id, correlation_id_var.get())
    return MyApiKeyRevokeResponse(key_id=key_id, revoked_at=matched.revoked_at)
