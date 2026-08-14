"""RS-003: report renderer Factory (implementation-plan.md section 7).

Keeps `generate_report()` callers (RS-004) agnostic to which template
renders -- a future second report kind (certification seal, RS-105/Won't
this backlog) becomes one new `ReportRenderer` subclass plus one new branch
here, not a rewrite of any caller.
"""

from __future__ import annotations

from app.renderers.base import ReportRenderer
from app.renderers.validation_audit import ValidationAuditRenderer


class UnknownReportKindError(ValueError):
    """Raised for any `kind` this factory does not recognize -- no silent
    fallback to a default renderer.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"Unknown report kind: {kind!r}")
        self.kind = kind


def get_report_renderer(kind: str) -> ReportRenderer:
    if kind == "validation_audit":
        return ValidationAuditRenderer()
    raise UnknownReportKindError(kind)
