"""SQLAlchemy 2.0 declarative model for the `reporting` schema: `Report`.

Backend-agnostic (portable SQLAlchemy types only), matching
validation-service's `app.models` shape (RS-002 ticket DRY check note) so it
can be shared, unmodified, by both the repository layer
(`repositories/postgres_repository.py`) and the Alembic migration
(`migrations/versions/0001_create_reporting_schema.py`) -- the schema has a
single source of truth, never defined twice (implementation-plan.md
section 9 DRY rule).

Field list matches RS-002's Design section exactly: `id`, `tenant_id`,
`run_id`, `report_kind`, `generated_at`, `content`, `status`. `content` is a
`Text` column storing the rendered HTML inline (README.md's "Does not own" --
object storage is a documented future contract, not this sprint's scope).
`run_id` is a plain string column, not a `ForeignKey` -- `runs` lives in
`validation-service`'s own `validation` schema, and per CLAUDE.md no service
reaches into another service's DB schema directly (only through that
service's HTTP API), so a cross-schema FK here is not valid.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"

    # Surrogate PK, minted at persistence time (uuid4 hex) -- same precedent
    # as validation-service's SplitResult.id.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    # References validation-service's runs.id (its own `validation` schema)
    # by value only, not a DB-level ForeignKey -- see module docstring.
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    report_kind: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
