"""Shared SQLAlchemy engine-building scaffolding (ARCH-001).

Extracted from validation-service's and gateway-api's `sqlite_repository.py`
modules, which each defined a byte-for-byte identical `_build_engine`. Generic
over `url` and `base` so the same helper covers `sqlite:///...` today and
`postgresql+psycopg://...` later (VS-013/GW-012) without a second helper.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase


def build_engine(url: str, base: type[DeclarativeBase]) -> Engine:
    """Creates an `Engine` for `url` and runs `base.metadata.create_all` against it."""
    engine = create_engine(url)
    base.metadata.create_all(engine)
    return engine
