# INGEST-008 — `POST /connectors/{source}/run`: tenant-authenticated crawl trigger

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done. **Priority**: Must.
**Depends on**: `INGEST-003`, `INGEST-004`, `INGEST-005`, `INGEST-007`. **Blocks**: `GW-019`.
**Can run in parallel with**: `INGEST-009` (separate router file).

## Analysis
Story: backlog `INGEST-008`, unchanged design. Concrete backend half of "trigger a crawl from the UI"
(decision #6). Constraint: this exposes the same sequence each connector's `__main__` block already
encodes — not a second, divergent "run a crawl" implementation.

## Design
Pattern: DI (FastAPI `Depends()` for tenant context + repository), reusing `INGEST-003`'s
`run_incremental`/repository path directly. File: new `services/ingestion-service/src/app/routers/
connectors.py`. **DRY check**: no new "run a crawl" sequence invented — calls `run_incremental` with
the tenant-aware params.

## Implementation acceptance criteria
- [x] `POST /connectors/{source}/run` (tenant-authenticated, `X-Tenant-Id`) resolves `source` to one of
  the three connectors, resolves watermark (`INGEST-005`) and credentials (`INGEST-004`, reddit only),
  calls `fetch()`, writes via the repository.
- [x] Returns `202`/`200` with a reference to the `crawl_runs` row (matching `validation-service`'s
  disclosed synchronous-execution caveat for `POST /runs` — same accepted interim tradeoff). Note:
  `ConnectorRecordRepository` exposes no read-back method for the row just written, so the response body
  is built from the row_count/status/since/fetched_at values already in hand from the write call itself
  (disclosed simplification per the ticket's own Implementation section), not a second repository read.
- [x] Unknown `source` → `404`. Missing Reddit credentials for a tenant → `422` naming the missing
  connector, never a raw `500`.

## Test acceptance criteria
- [x] Successful trigger writes real rows via a test-double repository
  (`tests/fake_repository.py`'s `FakeConnectorRecordRepository`/`FakeCredentialRepository`, reused as-is).
- [x] Cross-tenant isolation: tenant A's trigger never touches tenant B's watermark/credentials/rows.
- [x] Unknown source, missing credential cases covered.

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms the endpoint calls the same primitives `run_incremental`'s DB-write branch calls
  (`latest_watermark_from_db`, `add_{price,onchain,sentiment}_records`, `record_crawl_run`, same order,
  same failure handling), not a parallel/divergent reimplementation — called directly (not through
  `run_incremental` itself) only because the handler needs the resolved values back for the response
  body, which `run_incremental` (returns `None`) cannot supply.
- Confirms tenant resolution goes through `naive_first_common.get_tenant_context`, no bespoke header
  parsing.

## Documentation acceptance criteria
- [x] `services/ingestion-service/README.md`'s Contract section lists this route.
