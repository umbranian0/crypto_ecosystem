"""ECON-012: `POST /backtests` -- a batch/UX wrapper around ECON-005's
already-built, already-verified structural eligibility gate.

This module adds zero new eligibility logic. For each `run_id` in the
caller-supplied, bounded list it resolves an `UpstreamValidationResult` via
the exact same `Depends(get_upstream_client)` seam `routers/simulations.py`
already uses, then calls `check_economic_eligibility` (imported from
`app.eligibility`, never reimplemented or copied) -- the identical two-
condition guard `POST /simulations` already uses, applied per run id inside
a plain loop. One run id's refusal never stops the loop -- there is no early
`return`/`raise` on an individual refusal; every entry, eligible or refused,
is appended to an ordered results list and returned together.

`compute_economic_simulation` (the pure profitability computation) is never
imported or referenced in this module either, for the same reason it is
never referenced in `simulations.py`: it is called exclusively from inside
`check_economic_eligibility`'s own success branch.

ECON-013 (additive, one call site only): on the eligible branch, after
`decision.simulation` is appended to `results`, this module also calls
`BacktestResultRepository.create_backtest_result` -- the ONLY legitimate
call site for that method anywhere in this service (proven structurally by
`tests/test_backtest_results_repository.py`). The refusal branch above never
calls it -- nothing eligible to store there (ECON-002's own "inputs/earned-
outputs only, never a placeholder" design decision).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from app.contracts import (
    BacktestRequest,
    EligibleSimulationResult,
    NotEligibleForSimulation,
    SimulationRequest,
)
from app.dependencies.repositories import BacktestResultRepositoryDep
from app.dependencies.upstream import UpstreamValidationResultClientDep
from app.eligibility import EligibilityReason, check_economic_eligibility

router = APIRouter()

# Reused unmodified from routers/simulations.py's own refusal-message table
# -- the same two refusal reasons the single-run gate already distinguishes,
# just looked up once per run id here instead of once per request.
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
    "/backtests",
    response_model=None,
    status_code=200,
    summary=(
        "Manual, on-demand retrospective inspection of a fixed, "
        "caller-supplied set of run ids (single request, not a schedule)"
    ),
    description=(
        "A single, manually-triggered request that evaluates a fixed, "
        "caller-supplied list of run ids (bounded at 50 per request) "
        "against ECON-005's existing eligibility gate, one at a time. This "
        "is retrospective inspection only -- it does not run on a schedule, "
        "does not recur automatically, and does not watch for new run ids; "
        "the caller must submit the exact set of run ids they want "
        "inspected, once, per call. For each run id, this endpoint refuses "
        "(same shape as POST /simulations) unless a real upstream "
        "validation result exists for it and that result's Diebold-Mariano "
        "verdict shows the client model beat Naive0 with statistical "
        "significance, Harvey-corrected. As this service is currently "
        "wired (ECON-004's mock-only upstream client), that condition can "
        "never hold, so every real call today returns an all-refused batch "
        "-- see economic-service/README.md and docs/tickets/ECON-012.md for "
        "why. Where a run id is eligible, the entry is a hypothetical, "
        "cost/slippage-adjusted result for research purposes only -- never "
        "a forward-looking claim about future performance."
    ),
)
def create_backtest_batch(
    request: BacktestRequest,
    upstream_client: UpstreamValidationResultClientDep,
    backtest_result_repository: BacktestResultRepositoryDep,
) -> list[EligibleSimulationResult | NotEligibleForSimulation]:
    results: list[EligibleSimulationResult | NotEligibleForSimulation] = []
    # One id per real POST /backtests call, grouping every row this call
    # persists (ECON-013) -- generated once here, not per run_id.
    backtest_id = uuid4().hex

    for run_id in request.run_ids:
        upstream_verdict = upstream_client.get_result(
            tenant_id=run_id, validation_run_id=run_id
        )
        simulation_request = SimulationRequest(
            run_id=run_id,
            fee_schedule_id=request.fee_schedule_id,
            slippage_model_id=request.slippage_model_id,
        )

        decision = check_economic_eligibility(upstream_verdict, simulation_request)

        if not decision.is_eligible:
            results.append(
                NotEligibleForSimulation(
                    reason_code=decision.reason.value,
                    message=_REFUSAL_MESSAGES[decision.reason],
                    upstream_verdict=upstream_verdict,
                    run_id=run_id,
                )
            )
            continue

        assert decision.simulation is not None  # guaranteed by the guard's own eligible branch
        results.append(decision.simulation)
        # ECON-013: persist this eligible-branch row only -- no tenant-auth
        # dependency is wired into economic-service yet (same documented gap
        # as routers/simulations.py), so `run_id` stands in for `tenant_id`
        # here too, matching this router's existing upstream-client call above.
        backtest_result_repository.create_backtest_result(
            tenant_id=run_id,
            backtest_id=backtest_id,
            run_id=run_id,
            fee_schedule_id=request.fee_schedule_id,
            slippage_model_id=request.slippage_model_id,
            cost_adjusted_return=decision.simulation.cost_adjusted_return,
            slippage_adjusted_return=decision.simulation.slippage_adjusted_return,
            total_cost_bps=decision.simulation.total_cost_bps,
            upstream_dm_statistic=upstream_verdict.dm_statistic,
            upstream_dm_pvalue=upstream_verdict.dm_pvalue,
            upstream_dm_verdict=upstream_verdict.dm_verdict,
        )

    return results
