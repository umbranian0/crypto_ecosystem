# ECON-003 — Contracts: cost/slippage parameters + simulation request/response shape

**Status: done** — Tech Lead verified directly (read `src/app/contracts.py` and `tests/test_contracts.py` in full, re-ran the suite: 10 passed). The one open design question (Harvey correction folded into `dm_verdict`'s string vocabulary; `NotEligibleForSimulation.upstream_verdict` nests `dm_statistic`/`dm_pvalue`) is confirmed **not** a violation of the "no numeric field" structural requirement: those are DM-test evidence (statistic/p-value), not a profitability figure, and `NotEligibleForSimulation`'s own top-level field set has zero numeric fields (confirmed by direct inspection, not just the passing test). Flagged forward to ECON-005: its Test 1/Test 2 assertion must check for the *profitability* field names specifically (`cost_adjusted_return`/`slippage_adjusted_return`/`total_cost_bps`) rather than "any numeric value anywhere in the parsed body," so the nested DM-evidence fields aren't mistaken for a violation — ECON-005.md updated accordingly.

## Analysis
Story: ECON-003 (Must), `docs/product/backlog-economic-service.md`. Depends on: ECON-001 (done). Covers backlog ECON-003's acceptance criteria in full. Constraining docs: implementation-plan.md section 9 (DRY: kept local to `economic-service`, not promoted to `libs/common` — only one consumer exists today, matches backlog decision 3; promoting now would be speculative generality). This ticket's whole point, restated because it is load-bearing for ECON-005: the refusal response type must be **structurally incapable** of carrying a numeric profitability field — two genuinely separate Pydantic classes with disjoint field sets, never one class with nullable numeric fields defaulting to `None`/`0`. A nullable-field design would let a serialization bug silently emit a `0.0` that reads as "no profit" instead of "not eligible" — exactly the fabricated/placeholder-number failure mode this whole backlog exists to prevent.

**DRY check (performed before writing this ticket)**: `libs/common/src/naive_first_common/contracts.py` was read as the direct style precedent (plain `pydantic.BaseModel` classes, `Field(ge=...)`-style constraints, module docstring explaining the wire-contract's ownership) — mirror this style, but do **not** import from or add to `naive_first_common.contracts` (backlog decision 3: kept local this backlog). No existing Pydantic model in `economic-service` yet (ECON-001 added none) — first contracts in the module.

## Design
No design pattern beyond typed contracts (Pydantic validation itself is the mechanism, not a GoF pattern from section 7's table). Files touched (`services/economic-service/` only):
- `src/app/contracts.py` — `SimulationRequest`, `EligibleSimulationResult`, `NotEligibleForSimulation`, and (needed by ECON-004/ECON-005 downstream) `UpstreamValidationResult` — the shape ECON-004's mock client returns and ECON-005's guard reads. Define `UpstreamValidationResult` here too (not a separate ticket) since ECON-004 and ECON-005 both depend on ECON-003 for exactly this shape, per sprint-13.md's own sequencing note ("ECON-004... needs ECON-003's `UpstreamValidationResult`-shaped contract to mock against").
- `tests/test_contracts.py`.

`UpstreamValidationResult` field shape (binding, read directly from backlog ECON-005's AC): `source: Literal["mock_fixture", "live"]`, `dm_statistic: float`, `dm_pvalue: float`, `dm_verdict: str` (mirrors `validation-service`'s own `dm_statistic`/`dm_pvalue`/`dm_verdict` column group, per that service's README "Data model" section — the gate reads this verdict, it never recomputes the DM test itself). Implementer may add `harvey_corrected: bool` or fold Harvey-correction status into `dm_verdict`'s own string vocabulary — document whichever choice is made, since ECON-005 depends on reading this field precisely.

## Implementation acceptance criteria
- [x] `SimulationRequest` Pydantic model: references an upstream run identifier, a `fee_schedule_id`/`slippage_model_id` (or inline parameters), and whatever config a simulation needs — no profitability field on the request.
- [x] `UpstreamValidationResult` Pydantic model: `source: Literal["mock_fixture", "live"]`, `dm_statistic: float`, `dm_pvalue: float`, `dm_verdict: str` (or equivalent field set sufficient for ECON-005's guard to read a Harvey-corrected significant-outperformance verdict without recomputing it).
- [x] Two distinct, non-overlapping response models: `EligibleSimulationResult` (numeric fields: cost-adjusted return, slippage-adjusted return, etc. — only ever constructible on the success path) and `NotEligibleForSimulation` (**no** numeric return/profitability field at all — only a reason code/message and, where available, the upstream verdict that caused the refusal). Enforced by genuinely separate Pydantic classes with disjoint field sets — not one class with optional/nullable numeric fields.
- [x] Kept local to `economic-service` (`src/app/contracts.py`) — not added to `libs/common` in this backlog.

## Test acceptance criteria
- [x] `EligibleSimulationResult` fails Pydantic validation if constructed with `NotEligibleForSimulation`'s reason-code field instead of its own numeric fields (and vice versa) — i.e. a positive test proving the two classes do not silently accept each other's shape.
- [x] Round-trip JSON-schema test (`EligibleSimulationResult.model_json_schema()` vs `NotEligibleForSimulation.model_json_schema()`) confirming the two response types are distinguishable by shape alone — assert the two schemas' `properties` key-sets are disjoint with respect to any numeric-typed field (an API consumer's static type check can't accidentally read a profitability field off a refusal).
- [x] `.venv\Scripts\python.exe -m pytest -q` passes with zero failures, no regression on ECON-001's tests. (10 passed: 2 pre-existing ECON-001 tests + 8 new `test_contracts.py` tests.)

## Review acceptance criteria
- Tech Lead will personally read `src/app/contracts.py` and confirm by inspection (not just the passing test) that `NotEligibleForSimulation` has zero numeric fields of any kind (no `float`/`int` typed field, no `Optional[float]`) — this is Test-3/Test-4's own precondition in ECON-005 and must be true independent of any test asserting it. **Self-checked**: `NotEligibleForSimulation`'s only fields are `reason_code: str`, `message: str`, `upstream_verdict: UpstreamValidationResult | None`. No top-level `float`/`int`/`Optional[float]` field exists on this class.
- Tech Lead will confirm `UpstreamValidationResult.source` is typed `Literal["mock_fixture", "live"]`, not a bare `str` — a bare string would let a typo silently defeat ECON-005's gate check. **Self-checked**: confirmed, and covered by `test_upstream_validation_result_rejects_bare_string_source`.

## Documentation acceptance criteria
- [x] `README.md` updated: new "Contracts" section listing `SimulationRequest`/`UpstreamValidationResult`/`EligibleSimulationResult`/`NotEligibleForSimulation` with a one-line field summary each, explicitly noting they are kept local to `economic-service` (not `libs/common`) and why (backlog decision 3, only one consumer today).

## Sequencing note
Runs in parallel with ECON-002 (independent files, no shared data). Its `UpstreamValidationResult` output is consumed by ECON-004 and ECON-005 downstream — those tickets will import `from app.contracts import UpstreamValidationResult` etc., not redefine it.

## Outcome

Implemented in `services/economic-service/src/app/contracts.py` (new file) and `services/economic-service/tests/test_contracts.py` (new file, 8 tests). `services/economic-service/README.md` updated with a new "Contracts" section.

Final field lists, exactly as shipped:

- `SimulationRequest`: `run_id: str`, `fee_schedule_id: str`, `slippage_model_id: str`.
- `UpstreamValidationResult`: `source: Literal["mock_fixture", "live"]`, `dm_statistic: float`, `dm_pvalue: float`, `dm_verdict: str`. Harvey-correction status is folded into `dm_verdict`'s own string vocabulary (e.g. `"significant_outperformance_harvey_corrected"`), not a separate boolean field — this is the one deviation-from-a-choice the ticket's Design section explicitly left open ("Implementer may add `harvey_corrected: bool` or fold Harvey-correction status into `dm_verdict`'s own string vocabulary"); folding it in was chosen so ECON-005 has a single string to branch on, matching `validation-service`'s own `dm_verdict` shape (a single descriptive string, no parallel boolean flag).
- `EligibleSimulationResult`: `run_id: str`, `cost_adjusted_return: float`, `slippage_adjusted_return: float`, `total_cost_bps: float` (`Field(ge=0)`), `upstream_verdict: UpstreamValidationResult`.
- `NotEligibleForSimulation`: `reason_code: str`, `message: str`, `upstream_verdict: UpstreamValidationResult | None = None`.

No deviation from the ticket's binding design constraint: `EligibleSimulationResult` and `NotEligibleForSimulation` are two separate classes with disjoint field sets; `NotEligibleForSimulation` has zero numeric fields of its own (its optional `upstream_verdict` field carries the DM statistic/p-value evidence for the refusal, per the ticket's own text — "and, where available, the upstream verdict that caused the refusal" — not a profitability figure).

Test run: `.venv\Scripts\python.exe -m pytest -q` from `services/economic-service/` — **10 passed** (2 pre-existing ECON-001 tests, 8 new ECON-003 tests), 0 failures, 1 unrelated `httpx`/`starlette.testclient` deprecation warning pre-existing from ECON-001's scaffolding.

All Implementation, Test, and Documentation acceptance criteria checked off above are verified, not assumed. Review acceptance criteria are self-checked by the implementer as documented above; final sign-off is the Tech Lead's per the ticket's own process.
