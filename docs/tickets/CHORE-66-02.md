# CHORE-66-02 -- reporting-service: reject trend `horizon` < 1

**Status: done.** Sprint 66 item 4. Module: services/reporting-service (+ gateway-api only if no assertion proves 422 passthrough).

## Analysis
`GenerateReportRequest.horizon` in `services/reporting-service/src/app/routers/report_generation.py` is a bare `int | None`; `RunRequest.horizon` in libs/common is `Field(ge=1)`. Sprint 65 QA minor: horizon 0/-1 persists a no-data report.

## Design
Add `ge=1` (Field) to the horizon field, same pattern as `RunRequest.horizon`. DRY: grep the module first, extend the existing model, add nothing new. `validation_audit` must still reject `horizon` entirely; `consistency_trend` with omitted or valid horizon unchanged. Gateway forwards downstream errors via `_raise_for_error`; add one gateway test only if none proves 422 passthrough.

## Implementation AC
`horizon` 0 / -1 for consistency_trend -> 422; omitted/valid horizon -> unchanged behaviour.

## Test AC
Reporting tests for 0, -1 (422), 1 and omitted (unchanged); validation_audit+horizon still rejected. Full reporting-service suite green (`.venv/Scripts/python.exe -m pytest tests -q -rs` from the service dir).

## Review AC (TL)
Read diff; rerun suite; audit-log baseline unchanged.

## Documentation AC
services/reporting-service/README.md: horizon must be >= 1.

## Rules
Never run tests, alembic or SQL against the live database `naive_first`; Postgres-backed tests target `naive_first_test` (env override). Do not git commit. Stay in the module. No copy implying prediction/signals/economic value.
