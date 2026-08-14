"""Repository interface (implementation-plan.md section 7): `ReportRepository`.

Single responsibility: declare the data-access seam between route handlers
(RS-004/RS-005) and storage, with no storage-driver dependency of any kind --
mirrors `validation-service`'s `app.repositories.interfaces` shape exactly
(RS-002 ticket DRY check note), adapted to the `reporting.reports` table.

Record type (design decision, mirrors VS-003): `ReportRecord` below is a
plain `@dataclass(frozen=True)` type local to this module, a field-for-field
mirror of `app.models.Report` (this service's SQLAlchemy model), rather than
reusing that SQLAlchemy model directly. Reusing it would pull `sqlalchemy`
into this module's import graph transitively, which defeats the "zero
sqlalchemy import in interfaces.py" requirement even if no SQLAlchemy name is
used directly in a method signature here. Plain dataclasses keep
`interfaces.py` importable with zero storage dependencies -- exactly the
property the Repository pattern is meant to buy. `postgres_repository.py` is
responsible for converting between this record and `app.models.Report` rows.

Protocol vs ABC: `ReportRepository` is a `typing.Protocol` (matching
validation-service's `ValidationRunRepository`/`SplitResultRepository`
style), not `abc.ABC` -- there is no shared default method an ABC would buy
over a Protocol here.

Every method's first parameter after `self` is `tenant_id` (ticket AC, no
exceptions): the interface is tenant-scoped at the method-signature level,
not just by convention at the implementation.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReportRecord:
    """Mirrors `app.models.Report`'s columns exactly (see that module's
    docstring for field rationale); kept as a separate type so this module
    never imports `app.models` (and therefore never imports `sqlalchemy`).
    """

    id: str
    tenant_id: str
    run_id: str
    report_kind: str
    generated_at: datetime
    content: str
    status: str


@typing.runtime_checkable
class ReportRepository(typing.Protocol):
    """Repository for the `reporting.reports` table (RS-002 AC1 method set)."""

    def create_report(
        self,
        tenant_id: str,
        run_id: str,
        report_kind: str,
        content: str,
        status: str,
    ) -> ReportRecord: ...

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None: ...
