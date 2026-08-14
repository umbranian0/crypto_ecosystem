"""RS-002: Postgres-backed implementation of `interfaces.py`'s
`ReportRepository`, matching VS-013/GW-012's proven shape exactly (RS-002
ticket DRY check note) -- Postgres-only from the start, no SQLite sibling
(backlog decision 4, no fallback branch, unlike validation-service/
gateway-api's original build order).

Driver: `psycopg` v3, synchronous (`postgresql+psycopg://` URLs), same
binding decision VS-013/GW-012 made -- keeps `Session`-based method
signatures simple.

Engine construction: `naive_first_common.db.build_engine` (ARCH-001) via the
memoized-by-URL `_get_engine` seam (ARCH-002) in
`app.dependencies.repositories` -- no local `create_engine` call here.

Row-tenant scoping mechanism (RLS, matches VS-013/GW-012):
migrations/versions/0002_add_row_level_security.py enables and *forces*
Postgres row-level security on `reports`, with a `tenant_isolation` policy
that compares each row's `tenant_id` column against
`current_setting('app.tenant_id')`. That `current_setting` is a per-session
GUC with no value until something sets it -- if nothing sets it, the policy
raises rather than silently passing every row through, so a caller can never
accidentally see cross-tenant rows by skipping the setting.

Every transaction opened by `PostgresReportRepository` issues
`SELECT set_config('app.tenant_id', :tenant_id, true)` -- `SET LOCAL`'s
parameter-bindable equivalent (plain `SET LOCAL ... = :param` is not valid
Postgres syntax; `set_config`'s third argument `true` means "for this
transaction only", the same semantics) -- as the *first* statement, before
any other query, scoping `current_setting('app.tenant_id')` to that one
transaction only (reverts at COMMIT/ROLLBACK, so it can never leak into a
pooled connection's next, differently-tenanted, transaction). This is what
makes the RLS policy actually scope queries to the calling tenant; the
`.where(Model.tenant_id == tenant_id)` clauses below are retained anyway
(matching VS-013/GW-012's own style) as defense in depth, not as the
enforcement mechanism -- RLS is.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.models import Base, Report
from app.repositories.interfaces import ReportRecord
from naive_first_common.db import build_engine


def _tenant_scoped_session(engine: Engine, tenant_id: str) -> Session:
    session = Session(engine)
    # `SET LOCAL app.tenant_id = :tenant_id` is not valid Postgres syntax --
    # SET does not accept a bind parameter, only a literal, which would mean
    # string-formatting tenant_id directly into SQL. set_config(..., true)
    # is SET LOCAL's parameter-bindable equivalent (third arg `true` = "for
    # this transaction only", i.e. the exact SET LOCAL revert-at-commit
    # semantics this docstring/the ticket's Design section call for).
    session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id}
    )
    return session


def _report_to_record(report: Report) -> ReportRecord:
    return ReportRecord(
        id=report.id,
        tenant_id=report.tenant_id,
        run_id=report.run_id,
        report_kind=report.report_kind,
        generated_at=report.generated_at,
        content=report.content,
        status=report.status,
    )


class PostgresReportRepository:
    """Postgres implementation of `ReportRepository` (RS-002)."""

    def __init__(self, url: str, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else build_engine(url, Base)

    def create_report(
        self,
        tenant_id: str,
        run_id: str,
        report_kind: str,
        content: str,
        status: str,
    ) -> ReportRecord:
        report = Report(
            id=uuid4().hex,
            tenant_id=tenant_id,
            run_id=run_id,
            report_kind=report_kind,
            generated_at=datetime.utcnow(),
            content=content,
            status=status,
        )
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            session.add(report)
            # Record built from the already-fully-populated object, not a
            # post-commit session.refresh(): every column here is set
            # client-side (id/generated_at are both generated in Python
            # above), and refreshing after commit() would issue a new SELECT
            # in a *new* transaction this class's own _tenant_scoped_session
            # has not (yet) re-scoped with set_config('app.tenant_id', ...)
            # -- which RLS would then correctly, if surprisingly, block. See
            # validation-service's PostgresValidationRunRepository.create_run
            # (VS-013) and gateway-api's PostgresTenantRepository.create_tenant
            # (GW-012) for the identical precedent.
            record = _report_to_record(report)
            session.commit()
            return record

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None:
        with _tenant_scoped_session(self._engine, tenant_id) as session:
            report = session.execute(
                select(Report).where(Report.id == report_id, Report.tenant_id == tenant_id)
            ).scalar_one_or_none()
            return _report_to_record(report) if report is not None else None
