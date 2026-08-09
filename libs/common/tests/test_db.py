from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from naive_first_common.db import build_engine


class _Base(DeclarativeBase):
    pass


class _Widget(_Base):
    __tablename__ = "widgets"

    id: Mapped[str] = mapped_column(primary_key=True)


def test_build_engine_runs_create_all(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    engine = build_engine(f"sqlite:///{db_path}", _Base)

    assert inspect(engine).has_table("widgets")
