"""Wire-contract Pydantic models for economic-service (ECON-003).

Kept local to this service (`src/app/contracts.py`), not promoted to
`libs/common/src/naive_first_common/contracts.py` -- backlog decision 3
(`docs/product/backlog-economic-service.md`): only one consumer exists today
(this service itself), so sharing would be speculative generality ahead of
need (implementation-plan.md section 9's DRY rule extracts on *second*
duplication, not in anticipation of one).

Design constraint, load-bearing for ECON-005's downstream eligibility gate:
`EligibleSimulationResult` and `NotEligibleForSimulation` are two genuinely
separate classes with disjoint field sets -- never one class with
nullable/optional numeric fields defaulting to `None`. A nullable-field
design would let a serialization bug silently emit a value (e.g. `0.0`) that
reads as "no profit" instead of "not eligible" -- exactly the
fabricated/placeholder-number failure mode this backlog exists to prevent.
`NotEligibleForSimulation` therefore has zero numeric fields of any kind.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    """Request shape for a cost/slippage-adjusted portfolio simulation.

    No profitability field here by design -- this is an input, not an
    output; any numeric return figure only ever appears on the success
    response path (`EligibleSimulationResult`).
    """

    run_id: str
    fee_schedule_id: str
    slippage_model_id: str


class UpstreamValidationResult(BaseModel):
    """The DM-test verdict shape this service reads from `validation-service`
    (via ECON-004's mock client today -- see README's trigger-#11 override
    disclosure; no real `httpx` call exists yet).

    Field names mirror `validation-service`'s own `split_results` row shape
    (`dm_statistic`/`dm_pvalue`/`dm_verdict`, see that service's README
    "Data model" section) -- this service reads a DM verdict, it never
    recomputes or second-guesses one.

    `source` is a `Literal`, not a bare `str`: a typo in a bare string would
    silently defeat ECON-005's `"live"`-only gate check. `dm_verdict`'s own
    string vocabulary is expected to carry Harvey-correction status (e.g.
    "significant_outperformance_harvey_corrected" vs a plain
    "significant_outperformance") rather than a separate boolean field --
    this keeps the single upstream verdict string as the one place ECON-005
    reads a pass/fail decision from, matching how `validation-service`
    itself expresses `dm_verdict` today (a single descriptive string, no
    parallel boolean flag).
    """

    source: Literal["mock_fixture", "live"]
    dm_statistic: float
    dm_pvalue: float
    dm_verdict: str


class EligibleSimulationResult(BaseModel):
    """Success-path response: returned only when an upstream verdict has
    passed ECON-005's structural eligibility gate. Numeric fields live only
    here, never on `NotEligibleForSimulation`.
    """

    run_id: str
    cost_adjusted_return: float
    slippage_adjusted_return: float
    total_cost_bps: float = Field(ge=0)
    upstream_verdict: UpstreamValidationResult


class NotEligibleForSimulation(BaseModel):
    """Refusal-path response. No numeric return/profitability field of any
    kind -- no `float`, no `int`, no `Optional[float]` -- by construction,
    so a serialization bug can never make a refusal look like a "no profit"
    numeric result. Only a reason code/message and, where available, the
    upstream verdict that caused the refusal.
    """

    reason_code: str
    message: str
    upstream_verdict: UpstreamValidationResult | None = None
