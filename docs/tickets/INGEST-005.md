# INGEST-005 — Per-tenant crawl-run tracking

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done. **Priority**: Must.
**Depends on**: `INGEST-002`, `INGEST-003`, `INGEST-004` (same repository file — run strictly after
`INGEST-004` lands and is reviewed, not in parallel). **Blocks**: `INGEST-006`, `INGEST-008`.

## Analysis
Story: backlog `INGEST-005`, unchanged by solution-design.md section 8 beyond confirming the schema
(`crawl_runs`, already created by `INGEST-002`). Explicit accepted tradeoff (restated, not
re-litigated): N tenants running independent crawlers against the same public source (Binance,
blockchain.info) means N× external API load — no dedup/caching is built here.

## Design
Extends `INGEST-003`'s `ConnectorRecordRepository` (same file) with a `record_crawl_run` method — not a
new repository class. **DRY check**: confirmed by re-reading `INGEST-003`'s/`INGEST-004`'s final diff
before starting (this ticket's dev agent must read the actual current state of
`postgres_repository.py`, not assume its shape from this ticket file alone).

## Implementation acceptance criteria
- [x] `record_crawl_run(tenant_id, source, since_watermark, fetched_at, row_count, status)` writes one
  `crawl_runs` row per `fetch()` call, including empty-but-successful runs (row_count=0, status=
  "completed", not silently skipped).
- [x] `run_incremental`'s DB-write path (from `INGEST-003`) calls this after every write attempt,
  success or failure (failure status recorded, not swallowed). Implemented via a `try`/`except` around
  the existing `add_*_records` call that records `status="failed"` then re-raises the original
  exception unchanged, so `run_incremental`'s exception-propagation behavior is untouched.

## Test acceptance criteria
- [x] Two tenants crawling the same source produce two independent `crawl_runs` rows and two
  independent watermarks — tenant A running ahead never changes tenant B's `since` resolution
  (non-tautological: assert on tenant B's own next-watermark value staying anchored to tenant B's own
  last row). See `tests/test_base.py::test_run_incremental_two_tenants_have_independent_crawl_runs_and_watermarks`.
- [x] Empty-but-successful crawl still writes a `crawl_runs` row. See
  `tests/test_base.py::test_run_incremental_records_crawl_run_on_empty_success`.

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms `crawl_runs` write happens on every `fetch()` outcome (success, empty-success, failure), not
  only the happy path.
- Confirms zero new tenant-scoping mechanism introduced (reuses `LC-010`'s `tenant_scope` via the
  existing repository's session-handling, unchanged from `INGEST-003`/`INGEST-004`).

## Documentation acceptance criteria
- [x] `services/ingestion-service/README.md` states the N×-external-API-load tradeoff explicitly in a
  design-notes paragraph (not left as a surprise for real pilot-scale volume).
