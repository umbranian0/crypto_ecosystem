"""SQLAlchemy 2.0 declarative models for the `identity` schema: `Tenant`, `User`, `ApiKey`.

Backend-agnostic (portable SQLAlchemy types only) so a future SQLite
implementation (GW-004) and a future Postgres implementation (GW-012,
blocked on trigger #4) share these exact model classes -- no per-backend
model duplication (solution-design.md section 5, this ticket's AC5). Defined
once here and imported by both the repository layer (GW-004) and the
Alembic migration (migrations/versions/0001_create_identity_schema.py) so
the schema has a single source of truth.

Field list is solution-design.md section 4's `tenants`/`users`/`api_keys`
sketch, field-for-field (see this ticket's Design section).

`tenant_id` is denormalized directly onto `users` and `api_keys` (same
rationale as `SplitResult.tenant_id` in validation-service: lets
repositories filter by tenant without a join, and stops a leaked/misrouted
id from reaching cross-tenant data). `tenants` itself carries no
`tenant_id` column -- a tenant doesn't have an id to scope by yet (GW-003).

`api_keys` stores only `key_hash` (a SHA-256 hex digest, hashed by
GW-005/006 -- this ticket only defines the column). There is no
`key_plaintext`/`raw_key` column of any kind anywhere in this model -- the
raw key is never persisted, per backlog AC3. `revoked_at` is nullable:
revocation is a flag set on the row (GW-004/GW-010), not a delete.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Denormalized (module docstring): lets repositories filter by tenant
    # without a join, and stops a leaked/misrouted id reaching cross-tenant data.
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    # SHA-256 hex digest only -- GW-002 defines the column, GW-005/006 hash
    # the raw key. No raw/plaintext key column exists anywhere on this model
    # (backlog AC3), mechanically enforced by tests/test_models.py.
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
