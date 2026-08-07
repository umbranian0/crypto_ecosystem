"""GW-002: `Tenant`/`User`/`ApiKey` models round-trip via SQLAlchemy,
`tenant_id` is non-nullable on `users`/`api_keys`, `ApiKey` has no
raw/plaintext key column, and the Alembic revision creates a schema that
matches models.py's own columns exactly.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ApiKey, Base, Tenant, User

SERVICE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _make_tenant(**overrides) -> Tenant:
    fields = dict(
        id="tenant-1",
        name="Acme Corp",
        created_at=datetime(2026, 1, 1),
    )
    fields.update(overrides)
    return Tenant(**fields)


def _make_user(**overrides) -> User:
    fields = dict(
        id="user-1",
        tenant_id="tenant-1",
        email="alice@example.com",
        role="admin",
        created_at=datetime(2026, 1, 1),
    )
    fields.update(overrides)
    return User(**fields)


def _make_api_key(**overrides) -> ApiKey:
    fields = dict(
        id="key-1",
        tenant_id="tenant-1",
        key_hash="a" * 64,
        created_at=datetime(2026, 1, 1),
        revoked_at=None,
    )
    fields.update(overrides)
    return ApiKey(**fields)


def test_tenant_round_trips_all_fields(engine) -> None:
    with Session(engine) as session:
        session.add(_make_tenant())
        session.commit()

    with Session(engine) as session:
        fetched = session.get(Tenant, "tenant-1")
        assert fetched is not None
        assert fetched.name == "Acme Corp"
        assert fetched.created_at == datetime(2026, 1, 1)


def test_user_round_trips_all_fields(engine) -> None:
    with Session(engine) as session:
        session.add(_make_tenant())
        session.add(_make_user())
        session.commit()

    with Session(engine) as session:
        fetched = session.get(User, "user-1")
        assert fetched is not None
        assert fetched.tenant_id == "tenant-1"
        assert fetched.email == "alice@example.com"
        assert fetched.role == "admin"
        assert fetched.created_at == datetime(2026, 1, 1)


def test_api_key_round_trips_all_fields_revoked_at_settable(engine) -> None:
    with Session(engine) as session:
        session.add(_make_tenant())
        session.add(_make_api_key())
        session.add(_make_api_key(id="key-2", revoked_at=datetime(2026, 2, 1)))
        session.commit()

    with Session(engine) as session:
        active = session.get(ApiKey, "key-1")
        assert active is not None
        assert active.tenant_id == "tenant-1"
        assert active.key_hash == "a" * 64
        assert active.created_at == datetime(2026, 1, 1)
        assert active.revoked_at is None

        revoked = session.get(ApiKey, "key-2")
        assert revoked.revoked_at == datetime(2026, 2, 1)


def test_user_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_tenant())
        session.add(_make_user(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_api_key_requires_tenant_id(engine) -> None:
    with Session(engine) as session:
        session.add(_make_tenant())
        session.add(_make_api_key(tenant_id=None))
        with pytest.raises(IntegrityError):
            session.commit()


def test_api_key_has_no_raw_key_column() -> None:
    # Mechanically enforced (not just eyeballed): the mapped column names
    # are exactly this set -- no key_plaintext/raw_key/etc. column exists.
    column_names = {c.name for c in ApiKey.__table__.columns}
    assert column_names == {"id", "tenant_id", "key_hash", "created_at", "revoked_at"}


def test_alembic_upgrade_head_creates_matching_schema(tmp_path) -> None:
    db_path = tmp_path / "alembic_scratch.db"
    env = {"DATABASE_URL": f"sqlite:///{db_path}"}
    import os

    full_env = {**os.environ, **env}

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"tenants", "users", "api_keys"}.issubset(tables)

    tenant_columns = {c["name"] for c in inspector.get_columns("tenants")}
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    api_key_columns = {c["name"] for c in inspector.get_columns("api_keys")}

    expected_tenant_columns = {c.name for c in Tenant.__table__.columns}
    expected_user_columns = {c.name for c in User.__table__.columns}
    expected_api_key_columns = {c.name for c in ApiKey.__table__.columns}

    assert tenant_columns == expected_tenant_columns
    assert user_columns == expected_user_columns
    assert api_key_columns == expected_api_key_columns
    engine.dispose()
