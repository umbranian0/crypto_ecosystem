"""ECON-004: the upstream-validation-result seam (Strategy/DI,
implementation-plan.md section 7) and its sole implementation.

**Mock-only, by hard sprint-wide rule (see README.md's trigger-#11 override
disclosure) -- not a temporary stub.** `validation-service`'s `VS-017`
("client-supplied prediction baseline") is deferred and unbuilt, so there is
currently no code path anywhere on this platform that could produce a real
client-model DM verdict. `MockValidationResultClient` therefore always
returns hardcoded fixture data with `source="mock_fixture"` -- **never**
`"live"`. No `httpx` import and no `*_URL`-style environment variable read
belongs in this module, ever, until a future, separately-authorized ticket
lands `VS-017` and a real outperformance verdict exists to integrate against
(see README.md for the exact two-part condition).

`UpstreamValidationResultClient` is a `typing.Protocol` so ECON-005's
eligibility gate depends on the interface, never a concrete class -- mirrors
`app.repositories.interfaces.EconomicInputRepository`'s own Protocol-vs-ABC
choice (no shared default method needed).
"""

from __future__ import annotations

import typing

from app.contracts import UpstreamValidationResult


@typing.runtime_checkable
class UpstreamValidationResultClient(typing.Protocol):
    """Reads a DM-test verdict for a given validation run.

    This service reads a DM verdict, it never recomputes or second-guesses
    one (README.md "Does not own"). The tenant/run identifiers are opaque
    strings handed out by `validation-service`'s own REST API -- never a
    direct read of that service's DB schema (CLAUDE.md, implementation-plan.md
    section 5).
    """

    def get_result(self, tenant_id: str, validation_run_id: str) -> UpstreamValidationResult: ...


class MockValidationResultClient:
    """The sole implementation of `UpstreamValidationResultClient` this
    sprint. Returns hardcoded fixture data only -- `source="mock_fixture"`
    always, `"live"` never, regardless of the arguments passed in.

    This is the actual ethical point of ECON-004 (README.md's trigger-#11
    override disclosure): the platform has never produced a real
    "client model beat naive" result, so any client claiming to talk to
    `validation-service` for a real verdict today would be fabricating one.
    `dm_verdict` is deliberately worded `"no_real_upstream_verdict_exists"`
    (not a plausible-looking DM result) so a caller can never mistake this
    fixture for a genuine statistical finding.
    """

    def get_result(self, tenant_id: str, validation_run_id: str) -> UpstreamValidationResult:
        return UpstreamValidationResult(
            source="mock_fixture",
            dm_statistic=0.0,
            dm_pvalue=1.0,
            dm_verdict="no_real_upstream_verdict_exists",
        )

    def __repr__(self) -> str:
        return (
            "MockValidationResultClient(source='mock_fixture', "
            "fabricated=True, note='no real validation-service call ever "
            "made -- see README.md trigger-#11 override disclosure')"
        )
