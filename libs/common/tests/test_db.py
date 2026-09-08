from __future__ import annotations

from unittest.mock import Mock

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from naive_first_common.db import build_engine, tenant_scope


class _Base(DeclarativeBase):
    pass


class _Widget(_Base):
    __tablename__ = "widgets"

    id: Mapped[str] = mapped_column(primary_key=True)


def test_build_engine_runs_create_all(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    engine = build_engine(f"sqlite:///{db_path}", _Base)

    assert inspect(engine).has_table("widgets")


def test_build_engine_skips_create_all_for_postgres_urls(monkeypatch) -> None:
    """Found live (Sprint 29, SETUP-004's fresh-Postgres-volume dry run):
    `create_all` against a Postgres URL whose schema is owned by Alembic
    migrations, not this function, previously raised `InvalidSchemaName` on
    a genuinely fresh volume even though the tables already existed --
    `create_all` must never run for a `postgresql` dialect URL. Verified via
    a `create_engine`/`metadata.create_all` call-count spy rather than a
    real Postgres connection (no live DB in this lib's own unit-test scope).
    """
    create_all_calls: list[object] = []
    monkeypatch.setattr(_Base.metadata, "create_all", lambda engine: create_all_calls.append(engine))

    # SQLite in-memory engine, dialect name monkeypatched to "postgresql" --
    # this lib has no `psycopg` dependency of its own (it is a real,
    # separate service dependency, `services/gateway-api`'s/`validation-
    # service`'s own `pyproject.toml`), so a real `postgresql+psycopg://`
    # URL would fail on driver import alone in this lib's own test env. The
    # dialect-name check is `build_engine`'s entire branch condition, so
    # patching `Engine.dialect.name` directly proves the same branch without
    # a real Postgres driver/connection.
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(type(engine.dialect), "name", "postgresql")
    monkeypatch.setattr("naive_first_common.db.create_engine", lambda url: engine)

    from naive_first_common.db import build_engine as build_engine_fn

    result = build_engine_fn("postgresql+psycopg://user:pw@localhost/db", _Base)

    assert result is engine
    assert create_all_calls == []


def test_tenant_scope_issues_exact_set_config_statement() -> None:
    session = Mock()

    tenant_scope(session, "tenant-a")

    session.execute.assert_called_once()
    (statement, params), kwargs = session.execute.call_args
    assert kwargs == {}
    assert str(statement) == "SELECT set_config('app.tenant_id', :tenant_id, true)"
    assert params == {"tenant_id": "tenant-a"}
