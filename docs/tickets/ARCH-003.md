# ARCH-003 — Move the gateway-api proxy wire-contract into a shared libs package

Status: **done**
Backlog: docs/product/backlog-technical-upgrades.md, ARCH-003 [Must]
Sprint: docs/sprints/sprint-06.md, Phase 1 (independent, front-loaded)
Depends on: none

## Analysis

`services/gateway-api/src/app/routers/runs.py:56-122` defines four Pydantic models
(`RunRequest`, `RunResponse`, `RunDetailResponse`, `SplitResultResponse`) whose own docstrings
say they are "field-for-field copies" of `services/validation-service/src/app/routers/runs.py:88-122`
and `routers/splits.py:39-69`. This is the eighth hand-synced copy of the same field list
(naive_first_engine's `MetricSet` is source of truth; six more copies exist inside
validation-service's own model/interface/repository/router layers, which are architecturally
necessary boundary conversions — only gateway-api's copy is the avoidable one).

## Design

- **Binding decision (grooming, #5)**: these shared wire-contract Pydantic models land in the
  SAME package as ARCH-001 (`libs/common`) — do not create a new `libs/*` package. (`libs/common`
  already gains SQLAlchemy as a dependency this sprint via ARCH-001; adding a `contracts.py`
  Pydantic-only module here is consistent with its existing Pydantic-only-until-now shape.)
- Add `naive_first_common/contracts.py` (or `contracts/` subpackage) with `RunRequest`,
  `RunResponse`, `RunDetailResponse`, `SplitResultResponse` — copied verbatim from
  validation-service's current field definitions (these are the source-of-truth shapes per the
  backlog's own citation), not gateway-api's copy.
- `gateway-api/src/app/routers/runs.py` deletes its four local Pydantic classes and imports these
  from `naive_first_common.contracts` instead — no field/type changes, response_model wiring
  stays as-is.
- `validation-service/src/app/routers/runs.py` and `routers/splits.py` switch their own
  `RunRequest`/`RunResponse`/`RunDetailResponse`/`SplitResultResponse` definitions to import
  from the same shared module wherever the shape is genuinely field-for-field identical — per
  AC3, this makes validation-service the *canonical* user of the shared models too, not just
  gateway-api, closing the loop so there is exactly one definition instead of two.
- Pattern: shared Pydantic wire-contract in a `libs/*` package — matches implementation-plan.md
  section 9's explicit instruction ("pull shared logic into a libs/* package instead if it's
  genuinely cross-cutting"). Do not add cross-service imports of each other's app code — this
  stays a `libs/common` dependency on both sides, never gateway-api importing validation-service
  or vice versa.
- DRY check: after this ticket, the four model definitions exist exactly once, in
  `naive_first_common/contracts.py`; both services' routers import, none redefine.

## Implementation acceptance criteria

- [x] A shared Pydantic contract module for the run/split wire shapes exists under `libs/common`
      (`naive_first_common.contracts` or similar).
- [x] `gateway-api`'s router imports it instead of hand-copying the four model classes.
- [x] `validation-service`'s router uses the same shared models as its `response_model` wherever
      the shape is genuinely field-for-field identical.
- [x] No behavior change to any endpoint's request/response JSON shape.

## Test acceptance criteria

- [x] `test_runs_routing.py` (gateway-api) passes unmodified in behavior.
- [x] `test_runs_endpoint.py` and `test_splits_endpoint.py` (validation-service) pass unmodified
      in behavior.
- [x] `libs/common` gets a test confirming the contract models are importable and construct
      correctly with representative field values.

## Review acceptance criteria (Tech Lead personally verifies)

- [x] Confirm gateway-api's `runs.py` no longer defines its own `RunRequest`/`RunResponse`/
      `RunDetailResponse`/`SplitResultResponse` classes (grep for `class RunRequest` etc. in that
      file — should return nothing).
- [x] Confirm validation-service's routers import from `naive_first_common.contracts` for the
      identical shapes, not a second independent definition.
- [x] Confirm no cross-service import was introduced (gateway-api importing
      `services.validation_service...` or similar) — only `naive_first_common` imports.

## Documentation acceptance criteria

- [x] `libs/common/README.md` "Owns" list updated to mention the shared wire-contract module.
- [x] Both services' router module docstrings updated to note the shared source of the models.

## Outcome

Added `naive_first_common/contracts.py` with `RunRequest`, `RunResponse`, `RunDetailResponse`,
`SplitResultResponse` copied verbatim from validation-service's field definitions (the
backlog-cited source of truth). `gateway-api/src/app/routers/runs.py` deleted its four local
model classes (and the now-unused `datetime`/`pydantic` imports) and imports from
`naive_first_common.contracts` instead — response_model wiring and handler bodies unchanged.
`validation-service/src/app/routers/runs.py` and `routers/splits.py` switched their own
`RunRequest`/`RunResponse`/`RunDetailResponse`/`SplitResultResponse` definitions to the same
import, making validation-service a canonical user of the shared models too. Added
`libs/common/tests/test_contracts.py` (4 tests, one per model) confirming the models construct
correctly with representative field values. Updated `libs/common/README.md`'s "Owns" list and
both routers' module docstrings to note the shared source.

No cross-service imports were introduced (grep confirms only docstring prose mentions the other
service by name, never a Python import); no `class RunRequest`/etc. definitions remain in either
router file. `libs/common` (19 passed), `gateway-api` (55 passed), and `validation-service` (51
passed) test suites all pass. Did not touch `libs/common/pyproject.toml`, `sqlite_repository.py`,
or `dependencies/repositories.py` (ARCH-001's territory, run in parallel this sprint).
