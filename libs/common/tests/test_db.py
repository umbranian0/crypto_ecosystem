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


def test_tenant_scope_issues_exact_set_config_statement() -> None:
    session = Mock()

    tenant_scope(session, "tenant-a")

    session.execute.assert_called_once()
    (statement, params), kwargs = session.execute.call_args
    assert kwargs == {}
    assert str(statement) == "SELECT set_config('app.tenant_id', :tenant_id, true)"
    assert params == {"tenant_id": "tenant-a"}
