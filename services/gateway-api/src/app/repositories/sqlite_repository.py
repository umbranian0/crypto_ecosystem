"""GW-004: interim SQLite-backed implementations of GW-003's repository
interfaces (`TenantRepository`, `UserRepository`, `ApiKeyRepository`),
storing GW-002's `app.models.Tenant`/`User`/`ApiKey` rows in a file-based
SQLite database so state survives a process restart. Postgres (GW-012)
replaces this class-for-class behind the same DI seam (backlog decision 2)
-- see README.md's "Storage backend" note.

Conversion between GW-002's SQLAlchemy models and GW-003's `TenantRecord`/
`UserRecord`/`ApiKeyRecord` dataclasses happens once here (`_tenant_to_record`,
`_user_to_record`, `_api_key_to_record`), per interfaces.py's docstring
instruction that GW-004 owns this conversion -- callers never build these
dataclasses by hand.

Tenant isolation: every query that has a `tenant_id` to filter by does so in
the SQL `WHERE` clause itself (`.where(Model.tenant_id == tenant_id)`), never
"fetch, then check tenant_id in Python". `get_by_hash`/`get_user_by_email`
are GW-003's two documented exceptions and correctly have no `tenant_id`
filter -- they resolve identity, they don't yet know the tenant.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select, update
from sqlalchemy.orm import Session

from app.models import ApiKey, Base, Tenant, User
from app.repositories.interfaces import ApiKeyRecord, TenantRecord, UserRecord


def _build_engine(db_path: str) -> Engine:
    """File-based (not `:memory:`) so state created before a process
    restart is still there after (backlog AC).
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine


def _tenant_to_record(tenant: Tenant) -> TenantRecord:
    return TenantRecord(id=tenant.id, name=tenant.name, created_at=tenant.created_at)


def _user_to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
    )


def _api_key_to_record(api_key: ApiKey) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=api_key.id,
        tenant_id=api_key.tenant_id,
        key_hash=api_key.key_hash,
        created_at=api_key.created_at,
        revoked_at=api_key.revoked_at,
    )


class SQLiteTenantRepository:
    """SQLite implementation of `TenantRepository` (GW-003)."""

    def __init__(self, db_path: str) -> None:
        self._engine = _build_engine(db_path)

    def create_tenant(self, name: str) -> TenantRecord:
        tenant = Tenant(id=uuid4().hex, name=name, created_at=datetime.utcnow())
        with Session(self._engine) as session:
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
            return _tenant_to_record(tenant)

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        with Session(self._engine) as session:
            tenant = session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            ).scalar_one_or_none()
            return _tenant_to_record(tenant) if tenant is not None else None


class SQLiteUserRepository:
    """SQLite implementation of `UserRepository` (GW-003)."""

    def __init__(self, db_path: str) -> None:
        self._engine = _build_engine(db_path)

    def create_user(self, tenant_id: str, email: str, role: str) -> UserRecord:
        user = User(
            id=uuid4().hex,
            tenant_id=tenant_id,
            email=email,
            role=role,
            created_at=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            return _user_to_record(user)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        # No tenant_id filter (GW-003's documented exception): login-time
        # lookup doesn't yet know the tenant.
        with Session(self._engine) as session:
            user = session.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            return _user_to_record(user) if user is not None else None


class SQLiteApiKeyRepository:
    """SQLite implementation of `ApiKeyRepository` (GW-003)."""

    def __init__(self, db_path: str) -> None:
        self._engine = _build_engine(db_path)

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:
        api_key = ApiKey(
            id=uuid4().hex,
            tenant_id=tenant_id,
            key_hash=key_hash,
            created_at=datetime.utcnow(),
            revoked_at=None,
        )
        with Session(self._engine) as session:
            session.add(api_key)
            session.commit()
            session.refresh(api_key)
            return _api_key_to_record(api_key)

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        # No tenant_id filter (GW-003's documented exception): GW-006's auth
        # check must resolve a raw key to its tenant, not already know it.
        # Exact-match WHERE, not a scan-and-compare-in-Python.
        with Session(self._engine) as session:
            api_key = session.execute(
                select(ApiKey).where(ApiKey.key_hash == key_hash)
            ).scalar_one_or_none()
            return _api_key_to_record(api_key) if api_key is not None else None

    def revoke_key(self, tenant_id: str, key_id: str) -> None:
        # Sets revoked_at, never deletes the row (GW-006/GW-010 need the
        # revoked record still resolvable via get_by_hash).
        with Session(self._engine) as session:
            session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
                .values(revoked_at=datetime.utcnow())
            )
            session.commit()
