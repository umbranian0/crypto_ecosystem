"""DI seam (implementation-plan.md section 7) for GW-003's three repository
interfaces.

Single responsibility: give route handlers a `Depends()`-injectable provider
typed against `TenantRepository`/`UserRepository`/`ApiKeyRepository` (GW-003),
so handlers depend on the interface, never a concrete class, and tests can
override these providers with fakes via `app.dependency_overrides`.

GW-004 wires the repository providers to its SQLite implementation -- this
remains the only module that imports `app.repositories.sqlite_repository`
(AC2); no router/business-logic code should import it directly.

DB path: `GATEWAY_API_DB_PATH` env var, defaulting to `./gateway.db` (a local
file so tenant/user/api-key state survives a process restart). Swapping to
Postgres (GW-012) means changing only this module's provider bodies, not any
call site (backlog decision 2).
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends

from app.repositories.interfaces import ApiKeyRepository, TenantRepository, UserRepository
from app.repositories.sqlite_repository import (
    SQLiteApiKeyRepository,
    SQLiteTenantRepository,
    SQLiteUserRepository,
)

_DB_PATH_ENV_VAR = "GATEWAY_API_DB_PATH"
_DEFAULT_DB_PATH = "./gateway.db"


def _db_path() -> str:
    return os.environ.get(_DB_PATH_ENV_VAR, _DEFAULT_DB_PATH)


def get_tenant_repository() -> TenantRepository:
    return SQLiteTenantRepository(_db_path())


def get_user_repository() -> UserRepository:
    return SQLiteUserRepository(_db_path())


def get_api_key_repository() -> ApiKeyRepository:
    return SQLiteApiKeyRepository(_db_path())


TenantRepositoryDep = Annotated[TenantRepository, Depends(get_tenant_repository)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
ApiKeyRepositoryDep = Annotated[ApiKeyRepository, Depends(get_api_key_repository)]
