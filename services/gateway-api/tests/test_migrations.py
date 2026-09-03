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
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

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