"""GW-025: confirms `ix_api_keys_key_hash` (0003_add_api_keys_key_hash_index.py)
exists on `identity.api_keys` after `alembic upgrade head` against a real
Postgres `DATABASE_URL` -- an index-only-scan/query-plan-shape assertion
cannot be proven against sqlite (no comparable planner), so this, like
`tests/test_postgres_repository.py`, runs against real Postgres rather than
a mock/sqlite stand-in.

Follows `tests/test_postgres_repository.py`'s own live-Postgres convention
exactly, not a new one: a module-scoped fixture runs this service's real
`alembic upgrade head` via subprocess and `pytest.fail`s with the captured
stdout/stderr if that fails (e.g. no reachable Postgres) -- there is no
separate `pytest.mark.skipif`, since a hard, readable failure with the actual
alembic output already tells a developer running this locally without
Compose up exactly what's missing, matching what `test_postgres_repository.py`
already does for the exact same "is real Postgres reachable" precondition.

GW-026 extends this same file (rather than a second, parallel migration-test
harness, per that ticket's own DRY check) with the equivalent cases for
`ix_users_email` (0004_add_users_email_index.py), plus a live enforcement
proof (Test AC, "prove it live" standard) that the unique constraint is
actually rejected at the database level, not merely present in the schema.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Tenant, User

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Same literal IPv4 loopback address as tests/test_postgres_repository.py --
# see that module's docstring for why "localhost" can hang indefinitely on
# this platform's Windows/Docker Desktop dev setup.
POSTGRES_TEST_URL = os.environ.get(
    "GATEWAY_API_TEST_DATABASE_URL",
    "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first",
)


@pytest.fixture(scope="module")
def migrated_engine():
    env = {**os.environ, "DATABASE_URL": POSTGRES_TEST_URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head against real Postgres "
            f"({POSTGRES_TEST_URL}) failed:\n{result.stdout}\n{result.stderr}"
        )

    engine = create_engine(POSTGRES_TEST_URL)
    yield engine
    engine.dispose()


def test_ix_api_keys_key_hash_exists_and_is_unique(migrated_engine) -> None:
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'identity' AND tablename = 'api_keys' "
                "AND indexname = 'ix_api_keys_key_hash'"
            )
        ).all()

    assert len(rows) == 1, (
        "expected exactly one ix_api_keys_key_hash index on "
        f"identity.api_keys, found {rows!r}"
    )
    indexname, indexdef = rows[0]
    assert indexname == "ix_api_keys_key_hash"
    assert "UNIQUE INDEX" in indexdef
    assert "(key_hash)" in indexdef


def test_downgrade_then_upgrade_round_trips_the_index_cleanly(migrated_engine) -> None:
    """GW-026 note: this originally used `alembic downgrade -1` (correct back
    when `0003` was head). Now that `0004_add_users_email_index.py` (GW-026)
    stacks a further revision on top, a relative `-1` from `head` targets
    `0004`'s own index, not `0003`'s -- it would no longer isolate this
    migration's contribution at all. Targeting the explicit revision id
    below keeps this test meaningful regardless of how many later revisions
    are layered on top, and `upgrade head` (not `upgrade 0003`) at the end
    restores the full head schema the later tests in this module still
    expect.
    """
    env = {**os.environ, "DATABASE_URL": POSTGRES_TEST_URL}

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0002"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    with migrated_engine.connect() as conn:
        after_downgrade = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'identity' "
                "AND tablename = 'api_keys' AND indexname = 'ix_api_keys_key_hash'"
            )
        ).all()
    assert after_downgrade == []

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    with migrated_engine.connect() as conn:
        after_upgrade = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'identity' "
                "AND tablename = 'api_keys' AND indexname = 'ix_api_keys_key_hash'"
            )
        ).all()
    assert len(after_upgrade) == 1


def test_ix_users_email_exists_and_is_unique(migrated_engine) -> None:
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'identity' AND tablename = 'users' "
                "AND indexname = 'ix_users_email'"
            )
        ).all()

    assert len(rows) == 1, (
        "expected exactly one ix_users_email index on identity.users, "
        f"found {rows!r}"
    )
    indexname, indexdef = rows[0]
    assert indexname == "ix_users_email"
    assert "UNIQUE INDEX" in indexdef
    assert "(email)" in indexdef


def test_users_email_downgrade_then_upgrade_round_trips_the_index_cleanly(
    migrated_engine,
) -> None:
    env = {**os.environ, "DATABASE_URL": POSTGRES_TEST_URL}

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    with migrated_engine.connect() as conn:
        after_downgrade = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'identity' "
                "AND tablename = 'users' AND indexname = 'ix_users_email'"
            )
        ).all()
    assert after_downgrade == []

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    with migrated_engine.connect() as conn:
        after_upgrade = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'identity' "
                "AND tablename = 'users' AND indexname = 'ix_users_email'"
            )
        ).all()
    assert len(after_upgrade) == 1


def test_duplicate_email_insert_is_rejected_by_the_database(migrated_engine) -> None:
    """Live enforcement proof (Test AC): the unique index actually rejects a
    second row with the same `email`, not just "the index exists in the
    schema". Runs against a Postgres connection using the same real
    (superuser) role as the rest of this file -- RLS is not the property
    under test here, DB-level uniqueness is -- with `search_path=identity`
    set (`tests/test_postgres_repository.py`'s own convention, since
    `app.models`'s `Tenant`/`User` tables carry no schema-qualified
    `__tablename__` of their own and the migration puts them in `identity`,
    not `public`). Cleans up its own inserted rows in a `finally` so no
    fixture data survives the test, per this ticket's own precondition
    history (GW-026's Tech Lead unblock note).
    """
    engine_url = f"{POSTGRES_TEST_URL}?options={quote('-c search_path=identity')}"
    engine = create_engine(engine_url)

    now = datetime.now(timezone.utc)
    shared_email = f"dup-{uuid.uuid4().hex}@example.com"

    tenant_a_id = f"tenant-{uuid.uuid4().hex}"
    tenant_b_id = f"tenant-{uuid.uuid4().hex}"
    user_a_id = f"user-{uuid.uuid4().hex}"
    user_b_id = f"user-{uuid.uuid4().hex}"

    try:
        with Session(engine) as session:
            session.add(Tenant(id=tenant_a_id, name="dup-email-test-a", created_at=now))
            session.add(Tenant(id=tenant_b_id, name="dup-email-test-b", created_at=now))
            session.commit()

            session.add(
                User(
                    id=user_a_id,
                    tenant_id=tenant_a_id,
                    email=shared_email,
                    role="member",
                    created_at=now,
                )
            )
            session.commit()

            session.add(
                User(
                    id=user_b_id,
                    tenant_id=tenant_b_id,
                    email=shared_email,
                    role="member",
                    created_at=now,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        with Session(engine) as cleanup_session:
            cleanup_session.execute(
                text("DELETE FROM users WHERE id IN (:a, :b)"),
                {"a": user_a_id, "b": user_b_id},
            )
            cleanup_session.execute(
                text("DELETE FROM tenants WHERE id IN (:a, :b)"),
                {"a": tenant_a_id, "b": tenant_b_id},
            )
            cleanup_session.commit()
        engine.dispose()