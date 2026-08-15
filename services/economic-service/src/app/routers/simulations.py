"""ECON-005: `POST /simulations` -- the only HTTP entry point to the
structural eligibility gate.

Resolves an `UpstreamValidationResult` via ECON-004's DI seam
(`Depends(get_upstream_client)`, never a direct instantiation) before doing
anything else, then calls `check_economic_eligibility` -- and nothing else.
`compute_economic_simulation` (the pure profitability computation) is never
imported or referenced in this module at all -- it is called exclusively
from inside `check_economic_eligibility`'s own success branch in
`app/eligibility.py`. This is the module the guard structural-check test
(`tests/test_eligibility.py`) AST-parses to prove that fact, and the module
the Tech Lead's review acceptance criteria will read directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.contracts import EligibleSimulationResult, NotEligibleForSimulation, SimulationRequest
from app.dependencies.upstream import UpstreamValidationResultClientDep
from app.eligibility import EligibilityReason, check_economic_eligibility

router = APIRouter()

_REFUSAL_MESSAGES = {
    EligibilityReason.NO_REAL_UPSTREAM_RESULT: (
        "No real upstream validation result exists for this run "
        "(source != 'live') -- see economic-service README.md's "
        "trigger-#11 override disclosure."
    ),
    EligibilityReason.UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE: (
        "A real upstream validation result exists, but its DM verdict does "
        "not indicate a statistically significant, Harvey-corrected "
        "outperformance of Naive0."
    ),
}


@router.post(
    "/simulations",
    response_model=None,
    status_code=200,
    summary="Request a cost/slippage-adjusted simulation (eligibility-gated)",
    description=(
        "Refuses (409) unless two facts both hold for the given run: (1) a "
        "real upstream validation result exists for it (not this service's "
        "own mock fixture), and (2) that result's Diebold-Mariano verdict "
        "shows the client model beat Naive0 with statistical significance, "
        "Harvey-corrected. As this service is currently wired (ECON-004's "
        "mock-only upstream client), condition (1) can never hold, so every "
        "real call today refuses with a 409 and a reason code -- see "
        "economic-service/README.md for why."
    ),
)
def create_simulation(
    request: SimulationRequest,
    upstream_client: UpstreamValidationResultClientDep,
    response: Response,
) -> EligibleSimulationResult | NotEligibleForSimulation:
    # No tenant-auth dependency is wired into economic-service yet (out of
    # this ticket's scope -- ECON-005 is the eligibility gate, not tenant
    # resolution). `request.run_id` stands in for both positional arguments
    # the Protocol requires; `MockValidationResultClient` ignores both
    # regardless (ECON-004), so this has no effect on the gate's behavior.
    upstream_verdict = upstream_client.get_result(
        tenant_id=request.run_id, validation_run_id=request.run_id
    )

    decision = check_economic_eligibility(upstream_verdict, request)

    if not decision.is_eligible:
        response.status_code = 409
        return NotEligibleForSimulation(
            reason_code=decision.reason.value,
            message=_REFUSAL_MESSAGES[decision.reason],
            upstream_verdict=upstream_verdict,
        )

    assert decision.simulation is not None  # guaranteed by the guard's own eligible branch
    return decision.simulation
