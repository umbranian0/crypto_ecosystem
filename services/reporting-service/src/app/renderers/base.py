"""RS-003: `ReportRenderer` interface.

One method, `render(run, splits) -> str`, implemented per report "kind"
(`ValidationAuditRenderer` today; a future certification-seal/digest kind is
a second class implementing this same interface, per the Factory pattern
this module supports -- implementation-plan.md section 7).

`run`/`splits` are the shared `naive_first_common.contracts` wire models
(ARCH-003) -- this module does not redefine any of their fields locally,
matching `dashboard-web`'s own DRY precedent (DASH-004) for consuming the
same contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse


class ReportRenderer(ABC):
    """Renders one `RunDetailResponse` + its `SplitResultResponse` list into
    a durable HTML report string. Implementations must not recompute or
    reinterpret any metric/DM-verdict field -- those already reflect
    validation-service's/naive_first_engine's own leakage-aware protocol
    (including NFE-012's Harvey correction) and are rendered verbatim.
    """

    @abstractmethod
    def render(
        self,
        run: RunDetailResponse,
        splits: list[SplitResultResponse],
        *,
        narrative_html: str | None = None,
    ) -> str:
        """`narrative_html` (AI-002): an optional, already-generated,
        already-fact-checked LLM narrative paragraph to render alongside the
        table. `None` (the default) renders byte-identical output to before
        AI-002 -- no narrative block appears. Never generated here; this
        interface only renders whatever it's handed.
        """
        raise NotImplementedError
