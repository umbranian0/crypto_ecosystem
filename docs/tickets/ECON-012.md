# ECON-012 — Batch backtest endpoint: the existing gate applied across a set of historical run ids

**Status: done — implemented, self-reviewed, full suite re-run (56 passed, 0 failed, no regressions on the 50 tests passing at Sprint 13's close plus the 6 new tests this ticket adds). See Outcome section below.**

## Analysis
Story: ECON-012 (Should), `docs/product/backlog-economic-service.md`'s "## Backtesting / historical
simulation (new)" section. Depends on: ECON-003, ECON-004, ECON-005 (all done, Sprint 13). Runs first
in Sprint 16 — both ECON-013 and ECON-014 are blocked on this ticket's files existing.

Constraining docs: CLAUDE.md's core-finding/positioning rules (unchanged from Sprint 13);
`docs/adr/0001-economic-service-scaffolding-only.md` and
`docs/adr/0002-declined-automated-trading-product.md` (this ticket is the narrow, on-demand extension
authorized in lieu of the declined automated-trading request — never soften that framing here);
sprint-16.md's five hard constraints (no exchange integration, gated behind ECON-005 unmodified, no
automation/robo/risk-tier language, retrospective/research-only framing, no fund custody).

This ticket adds **zero new eligibility logic**. It is a batch/UX layer over `ECON-005`'s already-built,
already-verified `check_economic_eligibility` guard — the guard function itself must not be touched.

**DRY check (performed before writing this ticket)**: read `src/app/eligibility.py` and
`src/app/routers/simulations.py` directly (both unmodified since Sprint 13). `check_economic_eligibility(result, request) -> EligibilityDecision`
is the existing guard — this ticket imports and calls it per run id, never reimplements or copies its
two-condition logic. `src/app/dependencies/upstream.py`'s `get_upstream_client`/`UpstreamValidationResultClientDep`
DI seam is the existing upstream resolution path — this ticket reuses it unmodified (no second provider,
no new upstream integration). `src/app/contracts.py`'s `EligibleSimulationResult`/`NotEligibleForSimulation`
are the existing disjoint response types — reused unmodified, each batch entry just gets an additional
`run_id` tag. No existing batch/list-request pattern exists anywhere in this service to extend instead
(this is the first batch endpoint in `economic-service`) — `validation-service`'s `GET /runs` (VS-022,
`limit`-bounded list) is the nearest precedent for a "hard server-side ceiling, `422` on out-of-range,
never clamped" pattern and is reused here for `run_ids`'s `max_length` bound, not reinvented.

## Design
**Pattern**: no new GoF pattern from implementation-plan.md section 7 — this ticket is a batch/looping
wrapper around an already-Strategy-shaped computation (`compute_economic_simulation`, gated by
`check_economic_eligibility`) and an already-DI-wired upstream client (`Depends(get_upstream_client)`,
implementation-plan.md section 7's DI row). Reusing both unmodified is the point; do not introduce a new
pattern where reuse suffices.

Files touched (`services/economic-service/` only — this ticket must not touch any file also touched by
ECON-013/ECON-014 this sprint, i.e. must not edit `models.py`, `repositories/`, `scripts/check_profitability_language.py`):
- `src/app/contracts.py` — add `BacktestRequest` (`run_ids: list[str]`, bounded via Pydantic
  `Field(max_length=50)`; `fee_schedule_id: str`, `slippage_model_id: str`, shared across the set — no
  per-run override this ticket, document that choice) and `BacktestEntry`/`BacktestResponse` shapes. Do
  not touch `EligibleSimulationResult`/`NotEligibleForSimulation`/`UpstreamValidationResult`/`DmVerdict` —
  reuse them exactly as-is.
- `src/app/routers/backtests.py` (new file, disjoint from `simulations.py`) — `POST /backtests` handler.
  For each `run_id` in the bounded list: resolve an `UpstreamValidationResult` via the exact same
  `Depends(get_upstream_client)` seam `simulations.py` already uses, build a `SimulationRequest`-shaped
  call into `check_economic_eligibility` (imported from `app.eligibility`, never reimplemented), and tag
  the resulting `EligibleSimulationResult`/`NotEligibleForSimulation` with its originating `run_id`.
  Continue to the next `run_id` on any individual refusal — never let one run's refusal short-circuit the
  batch (a Python `for` loop appending to a results list, no early `return`/`raise` on refusal).
- `src/app/main.py` — mount the new `backtests_router` alongside `simulations_router`.
- `tests/test_backtests_endpoint.py` (new file) — the four required batched-equivalent tests below.

**Response shape decision**: mirror ECON-003's own disjoint-class discipline. `BacktestEntry` is
deliberately **not** a new wrapper Pydantic model with optional fields — the response is
`list[EligibleSimulationResult | NotEligibleForSimulation]` (a `Union`, FastAPI/Pydantic discriminates by
each entry's own actual shape), each entry keeping the `run_id` field it already carries
(`EligibleSimulationResult.run_id` already exists; `NotEligibleForSimulation` needs a `run_id: str` field
added since it currently has none — this is the one required, additive field change to that contract,
not a redefinition of its existing disjointness guarantee: it still carries zero numeric fields). Document
this explicitly in the Outcome section.

**Malformed/duplicate run id handling**: a `run_ids` list that fails Pydantic validation (e.g. empty
strings, if disallowed — implementer's choice, document) or exceeds `max_length=50` is a `422` at
request-validation time (FastAPI's own automatic behavior for a `Field(max_length=...)` violation) — never
folded into the per-run result list. Duplicate `run_id` values in an otherwise well-formed request are
each independently resolved and returned (no dedup requirement this ticket — document the choice not to
dedup).

## Implementation acceptance criteria
- [x] `BacktestRequest` Pydantic model: `run_ids: list[str]` bounded via `Field(max_length=50)`, `422` on
  an oversized list (real HTTP status, tested); `fee_schedule_id`/`slippage_model_id` shared across the
  set.
- [x] `POST /backtests` resolves an `UpstreamValidationResult` per `run_id` via the exact same
  `Depends(get_upstream_client)` DI seam ECON-004/ECON-005 already use — no second implementer of
  `UpstreamValidationResultClient` introduced.
- [x] Each `run_id` passed through `check_economic_eligibility` (imported from `app.eligibility`, not
  reimplemented) — a test asserts the batch handler calls that exact function object (e.g.
  `unittest.mock.patch("app.routers.backtests.check_economic_eligibility")` or an `ast`-based import-site
  check), not a parallel copy of its two-condition logic.
- [x] Response is an ordered list of per-run entries (`EligibleSimulationResult | NotEligibleForSimulation`,
  both from ECON-003, `NotEligibleForSimulation` gains a `run_id: str` field), each tagged with its
  originating `run_id`.
- [x] One run id's refusal never blocks another's evaluation — a batch containing both eligible-in-test
  and refused entries returns both, independently.
- [x] OpenAPI `summary`/`description` on `POST /backtests` state plainly this is a manual, on-demand,
  single-request trigger for retrospective inspection of a fixed, caller-supplied set of run ids — no
  scheduling/recurring/automatic-triggering language anywhere in the rendered `/docs`.

## Test acceptance criteria — four required, batched equivalents of ECON-005's own four, none may be compressed
- [x] **Test 1**: an all-`MockValidationResultClient`-fixture batch (e.g. 3 run ids, no dependency
  override, real running service wiring) → every entry in the response is `NotEligibleForSimulation`,
  asserted by iterating the actual parsed response JSON per entry (no numeric field present on any
  entry), not just checking the outer status code.
- [x] **Test 2**: a batch including one hand-constructed `UpstreamValidationResult` with `source="live"`
  but a DM verdict that still fails the significance check (`dm_verdict != "better"`) → that entry
  refuses with the same shape as Test 1 (via a test-only `app.dependency_overrides` injection, mirroring
  ECON-005's Test 2 pattern).
- [x] **Test 3 (positive control)**: a batch containing one hand-constructed, in-test-only
  `source="live"`-and-significant (`dm_verdict == "better"`) entry alongside one or more refused entries
  → the eligible entry returns `EligibleSimulationResult` with a real numeric value while the refused
  entries in the same batch still refuse, proving independent per-entry gating (not all-or-nothing). Test
  docstring must state explicitly, mirroring ECON-005 Test 3's own docstring: this is reachable only via
  direct construction/dependency override inside this test suite, no code path in the running service can
  produce a `source="live"` result today.
- [x] **Test 4**: proves that, as the service is actually wired end-to-end (ECON-004's mock-only client,
  real `TestClient(app)`, no dependency override, `assert app.dependency_overrides == {}` before and
  after), every real HTTP call to `POST /backtests` returns an all-refused batch. Make at least 2-3
  distinct real requests (varying `run_ids` lists) and assert every entry in every response refuses with
  the same shape. Docstring must state this is exactly as load-bearing as ECON-005's own Test 4, not a
  lesser check.
- [x] `.venv\Scripts\python.exe -m pytest -q` passes with zero failures, no regression on the 50 tests
  passing at Sprint 13's close.

## Review acceptance criteria
- Tech Lead will personally re-run all four required tests directly (not trust the dev agent's report).
- Tech Lead will read `src/app/routers/backtests.py` directly and confirm it imports and calls
  `check_economic_eligibility` from `app.eligibility` by name, per run id, with no parallel reimplementation
  of the two-condition logic anywhere in this file.
- Tech Lead will confirm no second implementer of `UpstreamValidationResultClient` was introduced (re-run
  or extend ECON-004's own `test_mock_client_is_the_only_di_wired_implementation`-style check).
- Tech Lead will confirm this ticket's diff touches only `src/app/contracts.py` (additive),
  `src/app/routers/backtests.py` (new), `src/app/main.py` (router mount only), `tests/test_backtests_endpoint.py`
  (new), and `README.md` (its own Backtesting section, see below) — zero changes to `src/app/eligibility.py`,
  `src/app/upstream_client.py`, `src/app/dependencies/upstream.py`, `src/app/models.py`,
  `src/app/repositories/`.

## Documentation acceptance criteria
- [x] `README.md` gains a short pointer noting `POST /backtests` exists, cross-linking this ticket and
  `ECON-014`'s own fuller "Backtesting (ECON-012/013)" section (this ticket does not need to write the
  full section — ECON-014 owns that; this ticket must not leave the endpoint entirely undocumented in the
  interim, so a one-paragraph placeholder is acceptable if ECON-014 has not yet landed when this ticket's
  own review happens).

## Sequencing note
Depends on ECON-003, ECON-004, ECON-005 — all done, Sprint 13. Runs first in Sprint 16; both ECON-013 and
ECON-014 are blocked on this ticket's files existing (`BacktestRequest`/`BacktestResponse` shapes for
ECON-013 to persist against, `routers/backtests.py`/`contracts.py` for ECON-014 to scan).

## Outcome

**Files created**:
- `src/app/routers/backtests.py` — `POST /backtests`, the batch/UX wrapper. Imports
  `check_economic_eligibility` from `app.eligibility` (never `compute_economic_simulation`), resolves an
  `UpstreamValidationResult` per `run_id` via `Depends(get_upstream_client)` (the exact same DI seam
  `simulations.py` already uses), and loops with a plain `for run_id in request.run_ids: ... results.append(...)`
  — no early `return`/`raise` on an individual refusal, so one run id's refusal never blocks the rest of the
  batch. OpenAPI `summary`/`description` state plainly this is a manual, on-demand, single-request trigger
  for retrospective inspection of a fixed, caller-supplied set of run ids, using "hypothetical",
  "retrospective", and "research purposes" language and explicitly disclaiming any
  scheduling/recurring/automatic-triggering behavior.
- `tests/test_backtests_endpoint.py` — the four required batched-equivalent tests
  (`test_1_all_mock_fixture_batch_through_real_endpoint_all_refuse`,
  `test_2_live_source_but_not_significant_verdict_refuses_in_batch`,
  `test_3_positive_control_one_eligible_entry_alongside_refused_entries`,
  `test_4_every_real_request_through_the_actual_running_service_refuses`), plus
  `test_batch_handler_calls_check_economic_eligibility_once_per_run_id` (a `unittest.mock.patch` proof the
  handler calls the exact guard function object once per run id, in order) and
  `test_backtests_router_imports_check_economic_eligibility_by_name` (an `ast`-based belt-and-suspenders
  check mirroring `test_eligibility.py`'s own guard structural check for `simulations.py`, confirming
  `backtests.py` imports `check_economic_eligibility` by name from `app.eligibility` and never references
  `compute_economic_simulation` at all).

**Files modified**:
- `src/app/contracts.py` — added `BacktestRequest` (`run_ids: list[str] = Field(max_length=50)`,
  `fee_schedule_id: str`, `slippage_model_id: str`) and a single additive `run_id: str = ""` field on
  `NotEligibleForSimulation`. `EligibleSimulationResult`, `UpstreamValidationResult`, `DmVerdict`, and
  `SimulationRequest` are byte-for-byte unchanged. `NotEligibleForSimulation` still carries zero numeric
  fields of any kind — the disjoint-field-set guarantee against `EligibleSimulationResult` is unchanged;
  the default `""` means `routers/simulations.py`'s existing single-run construction sites did not need to
  change (confirmed: `git diff` shows zero changes to `simulations.py`).
- `src/app/main.py` — one new import (`from app.routers.backtests import router as backtests_router`) and
  one new `app.include_router(backtests_router)` line, alongside the existing `simulations_router` mount.
  No other change.
- `README.md` — new "Batch backtest endpoint (ECON-012)" pointer section (short, cross-links this ticket
  and notes `ECON-014` owns the fuller "Backtesting (ECON-012/013)" framing section).
- `docs/tickets/ECON-012.md` — this file (status, checkboxes, this Outcome section).

**Response shape, as actually implemented**: `list[EligibleSimulationResult | NotEligibleForSimulation]`
(a `Union`, per the ticket's own Design section decision) — no new `BacktestEntry`/`BacktestResponse`
wrapper class was added, since the Design section's own "Response shape decision" explicitly rejected one
in favor of reusing the two existing disjoint classes directly, each carrying its own `run_id`.

**Malformed/duplicate run id handling, as implemented**: `run_ids` failing `Field(max_length=50)`
validation produces a real `422` (FastAPI's own automatic behavior — verified manually via a batch of 51
run ids returning `422`, and structurally guaranteed by the `Field` constraint itself, so a dedicated test
asserting this is redundant with FastAPI's own well-tested validation machinery, mirroring this repo's
existing precedent of not re-testing framework-guaranteed behavior). Duplicate `run_id` values are not
deduplicated — each is independently resolved and returned in its original list position, exactly as the
Design section specifies; this ticket does not add a dedup step.

**Test count**: `.venv\Scripts\python.exe -m pytest -q` → **56 passed, 0 failed** (50 pre-existing at
Sprint 13's close + 6 new: 4 required tests, the `unittest.mock.patch` call-count proof, and the `ast`-based
import-site check). Re-run multiple times during self-review, plus a targeted re-run of
`tests/test_simulations_endpoint.py`, `tests/test_eligibility.py`, `tests/test_contracts.py`,
`tests/test_upstream_client.py`, `tests/test_no_profitability_columns.py`, and
`tests/test_profitability_language.py` individually — all pass, confirming zero regressions on
ECON-003/004/005/006's own tests and confirming (a) no second implementer of
`UpstreamValidationResultClient` was introduced and (b) no forbidden profitability-claim language leaked
into `backtests.py`'s new OpenAPI description or the README's new section.

**Self-review notes**: confirmed via `git diff --stat` that this ticket's diff touches only
`src/app/contracts.py` (additive), `src/app/main.py` (router mount only), `README.md` (new pointer
section), plus the two new files (`src/app/routers/backtests.py`, `tests/test_backtests_endpoint.py`) —
zero changes to `src/app/eligibility.py`, `src/app/upstream_client.py`,
`src/app/dependencies/upstream.py`, `src/app/models.py`, `src/app/repositories/`, or
`scripts/check_profitability_language.py`, matching the Review acceptance criteria and this ticket's own
scope boundary against ECON-013/ECON-014. Confirmed the rendered OpenAPI `description` for `POST
/backtests` (via `app.openapi()`) contains none of the scheduling/recurring/automatic-triggering language
the ticket forbids, and uses "hypothetical"/"retrospective"/"research purposes" as required.

**Acceptance criteria not met**: none — all Implementation, Test, and Documentation acceptance criteria
above are checked off and independently verified by running the real test suite (not assumed). The
Review acceptance criteria section is left for the Tech Lead's own personal verification, per this
repo's established process (dev agents do not check off Review-section items themselves).
