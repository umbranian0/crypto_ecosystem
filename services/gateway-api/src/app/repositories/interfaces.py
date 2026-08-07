"""Repository interfaces (implementation-plan.md section 7): `TenantRepository`,
`UserRepository`, `ApiKeyRepository`.

Single responsibility: declare the data-access seam between route handlers and
storage, with no storage-driver dependency of any kind, so schema-per-service
can later become DB-per-service without any call site changing.
Implementation is GW-004; this ticket (GW-003) only defines the shape.

Record types (design decision, GW-003 ticket Design section, same reasoning
as validation-service's VS-003): `TenantRecord`, `UserRecord`, `ApiKeyRecord`
below are plain `@dataclass(frozen=True)` types local to this module,
field-for-field mirrors of GW-002's `Tenant`/`User`/`ApiKey` SQLAlchemy models
(`app.models`), rather than reusing those SQLAlchemy models directly. Reusing
them would pull `sqlalchemy` into this module's import graph transitively,
which defeats the "no storage-driver import" requirement even if no
SQLAlchemy name is used directly in a method signature here. Plain
dataclasses keep `interfaces.py` importable with zero storage dependencies,
which is exactly the property the Repository pattern is meant to buy
(implementation-plan.md section 7). GW-004's implementation is responsible
for converting between these records and `app.models.Tenant`/`User`/`ApiKey`
rows.

Protocol vs ABC (design decision): all three interfaces are `typing.Protocol`
(matching VS-003's own precedent), not `abc.ABC` -- none of the three needs a
shared default method, so there is nothing an ABC would buy over a Protocol
here.

`tenant_id`-first convention (backlog AC2) and its exceptions: every method
takes `tenant_id` as its first parameter after `self`, except exactly three,
each documented individually at its own definition below because each has a
different reason a tenant isn't yet known at call time:
- `TenantRepository.create_tenant` -- a tenant has no id yet at creation time.
- `ApiKeyRepository.get_by_hash` -- GW-006's auth check must resolve a raw
  key to its tenant, not already know the tenant, so `key_hash` alone is the
  correct lookup key.
- `UserRepository.get_user_by_email` -- login-time lookup doesn't yet know
  the tenant either; `email` alone is the correct lookup key.
No other method has an exception: `create_key`, `revoke_key`, and
`create_user` all take `tenant_id` first, since in each of those cases a
tenant is already known by the caller.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TenantRecord:
    """Mirrors `app.models.Tenant`'s columns exactly (see that module's
    docstring for field rationale); kept as a separate type so this module
    never imports `app.models` (and therefore never imports `sqlalchemy`).
    """

    id: str
    name: str
    created_at: datetime


@dataclass(frozen=True)
class UserRecord:
    """Mirrors `app.models.User`'s columns exactly."""

    id: str
    tenant_id: str
    email: str
    role: str
    created_at: datetime


@dataclass(frozen=True)
class ApiKeyRecord:
    """Mirrors `app.models.ApiKey`'s columns exactly."""

    id: str
    tenant_id: str
    key_hash: str
    created_at: datetime
    revoked_at: datetime | None


@typing.runtime_checkable
class TenantRepository(typing.Protocol):
    """Repository for the `tenants` table (backlog AC2 method set)."""

    def create_tenant(self, name: str) -> TenantRecord:
        """Not `tenant_id`-first: a tenant has no id until it is created --
        the one exception documented in this module's docstring.
        """
        ...

    def get_tenant(self, tenant_id: str) -> TenantRecord | None: ...


@typing.runtime_checkable
class UserRepository(typing.Protocol):
    """Repository for the `users` table (backlog AC2 method set)."""

    def create_user(self, tenant_id: str, email: str, role: str) -> UserRecord: ...

    def get_user_by_email(self, email: str) -> UserRecord | None:
        """Not `tenant_id`-first: login-time lookup doesn't yet know the
        tenant, so `email` alone is the correct lookup key -- the second
        documented exception in this module's docstring (same spirit as
        `ApiKeyRepository.get_by_hash`).
        """
        ...


@typing.runtime_checkable
class ApiKeyRepository(typing.Protocol):
    """Repository for the `api_keys` table (backlog AC2 method set)."""

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord: ...

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        """Not `tenant_id`-first: GW-006's auth check must resolve a key to
        its tenant, not already know the tenant, so `key_hash` alone is the
        correct lookup key -- the third documented exception in this
        module's docstring (same spirit as `UserRepository.get_user_by_email`).
        """
        ...

    def revoke_key(self, tenant_id: str, key_id: str) -> None: ...
