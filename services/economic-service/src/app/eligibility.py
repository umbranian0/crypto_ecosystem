"""ECON-005: the structural eligibility gate.

Single named guard function, `check_economic_eligibility`, is the **only**
authorized path to `compute_economic_simulation` (the pure profitability
computation). `compute_economic_simulation` is called exclusively from
inside the guard's own success branch, below -- it is never imported and
never called by `src/app/routers/simulations.py` (the guard structural-check
test, option (a) in ECON-005.md, AST-parses that router module and asserts
the string `compute_economic_simulation` never appears in it at all, not
even as an import).

**Design note, documented deviation from the ticket's own shorthand
signature**: ECON-005.md's Design section writes the guard's signature as
`check_economic_eligibility(result: UpstreamValidationResult) ->
EligibilityDecision`, but also requires (a) that `compute_economic_simulation`
-- which needs `SimulationRequest.run_id` to build `EligibleSimulationResult`
-- is only ever called from *inside* the guard's success branch, and (b)
that the router never imports/calls the computation function directly. Both
of those can only hold simultaneously if the guard itself receives the
`SimulationRequest` it needs to pass through to the computation step, so
this implementation extends the guard's signature to
`check_economic_eligibility(result, request) -> EligibilityDecision`
and has `EligibilityDecision` carry the already-computed
`EligibleSimulationResult` (`None` on any refusal branch) rather than the
router calling a second function afterward. This keeps `check_economic_eligibility`
the single, sole entry point a caller needs -- the router calls nothing else
on the eligible path.

**The refusal condition (binding, ECON-005 Design section -- do not alter
without a new ticket)**: refuse unless the conjunction of two
independently-checked facts both hold:

1. `result.source == "live"` (never `"mock_fixture"`) -- there must be a real
   upstream result at all.
2. `result.dm_verdict` indicates the client model beat Naive0 with
   statistical significance, Harvey-corrected (NFE-012). The exact,
   unambiguous rule this module implements: `dm_verdict` must start with the
   literal prefix `"significant_outperformance"` (e.g.
   `"significant_outperformance_harvey_corrected"`). Any other value --
   including `"not_significant"`, `"naive0_better"`, and ECON-004's own
   `"no_real_upstream_verdict_exists"` -- fails this check. Future readers
   (ECON-006 and beyond): this prefix match is the one and only place this
   string vocabulary is interpreted; do not add a second, divergent
   interpretation elsewhere.

Both facts are checked independently (not collapsed into one boolean) so
`EligibilityDecision` can distinguish *why* a request was refused -- "no real
upstream result" (fact 1 failed) vs. "upstream result exists but did not beat
naive" (fact 1 held, fact 2 failed) -- which the router surfaces via
`NotEligibleForSimulation.reason_code`.

This gate reads an already-computed `dm_verdict`/`dm_pvalue`/`dm_statistic`
off `UpstreamValidationResult` (ECON-003); it never calls into
`naive_first_engine` and never recomputes or second-guesses a DM test
(README.md "Does not own").
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.contracts import EligibleSimulationResult, SimulationRequest, UpstreamValidationResult

_SIGNIFICANT_OUTPERFORMANCE_PREFIX = "significant_outperformance"


class EligibilityReason(enum.Enum):
    """Why a `check_economic_eligibility` call resolved the way it did."""

    NO_REAL_UPSTREAM_RESULT = "no_real_upstream_result"
    UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE = "upstream_result_did_not_beat_naive"
    ELIGIBLE = "eligible"


@dataclass(frozen=True)
class EligibilityDecision:
    """Tagged result of the guard check. `is_eligible` is derived from
    `reason` (`True` iff `reason is EligibilityReason.ELIGIBLE`) -- there is
    exactly one source of truth, no separately-settable flag that could drift
    from the reason. `simulation` is populated only on the eligible branch
    (computed by `compute_economic_simulation` from inside the guard itself)
    -- `None` on both refusal branches.
    """

    reason: EligibilityReason
    simulation: EligibleSimulationResult | None = None

    @property
    def is_eligible(self) -> bool:
        return self.reason is EligibilityReason.ELIGIBLE


def check_economic_eligibility(
    result: UpstreamValidationResult, request: SimulationRequest
) -> EligibilityDecision:
    """The single named guard. Checks the two-condition conjunction
    independently, fact 1 before fact 2, so the returned reason distinguishes
    which fact failed. Only on the eligible branch does it call
    `compute_economic_simulation` -- the sole call site for that function in
    this codebase.
    """
    if result.source != "live":
        return EligibilityDecision(reason=EligibilityReason.NO_REAL_UPSTREAM_RESULT)

    if not result.dm_verdict.startswith(_SIGNIFICANT_OUTPERFORMANCE_PREFIX):
        return EligibilityDecision(reason=EligibilityReason.UPSTREAM_RESULT_DID_NOT_BEAT_NAIVE)

    simulation = compute_economic_simulation(result, request)
    return EligibilityDecision(reason=EligibilityReason.ELIGIBLE, simulation=simulation)


def compute_economic_simulation(
    result: UpstreamValidationResult, request: SimulationRequest
) -> EligibleSimulationResult:
    """Pure profitability computation. Only ever called from inside
    `check_economic_eligibility`'s own success branch above -- this function
    has no safety check of its own and trusts its caller entirely, by
    design: duplicating the guard's logic here would create a second,
    divergent place the eligibility rule could be edited out of sync with
    the one in `check_economic_eligibility`. Calling this function directly
    with a guard-refused `UpstreamValidationResult` (e.g. `source="mock_fixture"`)
    produces a numeric result with no error -- it has no independent
    eligibility check of its own, it genuinely depends on the guard.

    The cost/slippage computation itself is intentionally trivial
    placeholder arithmetic -- this ticket's scope is the structural gate, not
    a real cost/slippage model (that is Strategy-shaped future work per the
    Design section; no real client-model result has ever existed to compute
    against, see README.md's trigger-#11 override disclosure).
    """
    total_cost_bps = 10.0
    cost_adjusted_return = result.dm_statistic
    slippage_adjusted_return = cost_adjusted_return - (total_cost_bps / 10_000.0)

    return EligibleSimulationResult(
        run_id=request.run_id,
        cost_adjusted_return=cost_adjusted_return,
        slippage_adjusted_return=slippage_adjusted_return,
        total_cost_bps=total_cost_bps,
        upstream_verdict=result,
    )
