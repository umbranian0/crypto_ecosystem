"""VS-025: `validation.runs` gains a composite index on
`(tenant_id, created_at DESC)`, via migration 0005.

Gated exactly the same way test_postgres_repository.py's/
test_hypertable_migration.py's real-Postgres tests already are -- skipped,
not failed, when Postgres isn't reachable locally (e.g. Docker not running),
never mocked.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

SERVICE_ROOT = Path(__file__).resolve().parent.parent

# Matches infra/.env.example's POSTGRES_*/VALIDATION_SERVICE_DATABASE_URL
# defaults, reached via the host-published port (tests run outside Compose).
# Uses the literal loopback IP, not "localhost" -- same IPv6-hang finding as
# test_postgres_repository.py/test_hypertable_migration.py in this same
# directory (2026-09-01 QA sweep): resolving "localhost" can attempt an IPv6
# (::1) connection first, which Docker Desktop's port-forwarding (127.0.0.1
# only) never answers, hanging this file indefinitely instead of failing
# over to IPv4.
POSTGRES_URL = "postgresql+psycopg://naive_first:naive_first_dev_password@127.0.0.1:5432/naive_first"


def _postgres_reachable() -> bool:
    try:
        engine = create_engine(POSTGRES_URL)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_reachable(), reason="Postgres not reachable at 127.0.0.1:5432"
)


def test_runs_tenant_id_created_at_index_exists_after_upgrade_head() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env={**os.environ, "DATABASE_URL": POSTGRES_URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'validation' AND tablename = 'runs' "
                "AND indexname = 'ix_runs_tenant_id_created_at'"
            )
        ).all()
    engine.dispose()

    assert len(rows) == 1
    indexdef = rows[0].indexdef.lower()
    assert "tenant_id" in indexdef
    assert "created_at" in indexdef
    assert "desc" in indexdef