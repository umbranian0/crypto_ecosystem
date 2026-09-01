# INGEST-006 — Regression test: existing connector `fetch()` behavior is unchanged

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done. **Priority**: Should.
**Depends on**: `INGEST-003`, `INGEST-004`, `INGEST-005`.

Dev agent report: added `tests/test_adapter_contract_unchanged.py` (two tests: signature
introspection via `inspect.signature`/`typing.get_type_hints` -- `IngestionSource.fetch` is
`fetch(self, since: datetime) -> FetchResult` unchanged; and `__abstractmethods__` still contains
only `fetch`). Full suite: 49 passing before, 51 passing after (+2), zero regressions. `git status`
scoped to this ticket's own diff shows only the one new test file added; no production file in
`connectors/` or `app/` was touched by this ticket (pre-existing uncommitted changes from prior,
not-yet-committed sprint work are present in the working tree but predate and are untouched by this
ticket).

## Analysis
Story: backlog `INGEST-006`, unchanged. Proves Epic A's DB-integration work was additive to the
`IngestionSource` Adapter contract, not a rewrite-in-disguise.

## Design
New test file only: `services/ingestion-service/tests/test_adapter_contract_unchanged.py`. No production
code touched. No DRY concern (pure test addition).

## Implementation acceptance criteria
- [x] N/A (test-only ticket).

## Test acceptance criteria
- [x] Pre-`INGEST-003` `fetch()` tests for all three connectors re-run byte-for-byte unmodified, still
  pass.
- [x] A structural test asserts `IngestionSource.fetch`'s signature is exactly `fetch(self, since:
  datetime) -> FetchResult` (introspection-based, same spirit as `NFE-018`/`LC-005`'s doc-sync checks).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms this ticket's diff touches only `tests/`, zero production files.
- Re-runs the full `ingestion-service` suite, confirms the count matches pre-ticket + this ticket's new
  tests, zero regressions.

## Documentation acceptance criteria
- [x] None beyond the standing test-count note in the sprint's outcome summary (this ticket file's own
  status/report line serves as that note).
