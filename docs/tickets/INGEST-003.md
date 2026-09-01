# INGEST-003 — Connectors write to the `ingestion` schema instead of local CSVs

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: todo. **Priority**: Must.
**Depends on**: `INGEST-002`, `LC-010`. **Blocks**: `INGEST-004`, `INGEST-005`, `INGEST-006`, `INGEST-008`, `INGEST-009`, `INGEST-010`.

## Analysis
Story: backlog `INGEST-003`, unchanged by solution-design.md section 8 (no refinement noted there beyond
the schema shape `INGEST-002` already built). Constraint: `connectors/base.py`'s `IngestionSource.fetch`
Adapter contract (implementation-plan.md section 7) must not change shape — this is additive DB-write
plumbing, not a rewrite.

## Design
Pattern: Repository (implementation-plan.md section 7) — `ConnectorRecordRepository` Protocol, one
method per table family, `tenant_id` as first parameter after `self`, matching `validation-service`'s
`ValidationRunRepository` convention. Files touched: `services/ingestion-service/src/app/
repositories/interfaces.py` (new), `services/ingestion-service/src/app/repositories/
postgres_repository.py` (new, uses `naive_first_common.db.tenant_scope` from `LC-010`),
`connectors/base.py` (extend `run_incremental`/add `latest_watermark_from_db`, don't replace).
**DRY check**: reuse `LC-010`'s `tenant_scope`, not a fourth hand-rolled `set_config` call.

## Implementation acceptance criteria
- [ ] `ConnectorRecordRepository` Protocol: `add_price_records`, `add_onchain_records`,
  `add_sentiment_records`, each `(tenant_id, source, records: pd.DataFrame) -> int` (rows written).
- [ ] `connectors/base.py`'s `run_incremental` gains optional `tenant_id`/`repository` params; when both
  supplied, writes via the repository instead of CSV. CSV path kept unchanged as the standalone/no-tenant
  fallback — existing tests for the CSV path pass unmodified.
- [ ] `latest_watermark_from_db(repository, tenant_id, source)` queries `MAX(fetched_at)` scoped to
  `tenant_id`, coexisting with (not replacing) the CSV-scanning `latest_watermark`.

## Test acceptance criteria
- [ ] All three connectors' existing `fetch()` unit tests pass unmodified.
- [ ] New DB-write-path test per connector using an in-memory/test-double repository — no real Postgres
  required (matches this service's "fake the client, never hit the real API" convention).
- [ ] Cross-tenant isolation test: two tenants' writes never collide/overwrite each other in the fake
  repository (non-tautological — assert on which tenant's row exists, not just a count).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms `IngestionSource.fetch(self, since) -> FetchResult` signature is byte-unchanged.
- Confirms `LC-010`'s `tenant_scope` is the only tenant-scoping mechanism used, no local reimplementation.
- Re-runs the full existing connector test suite, confirms zero regressions.

## Documentation acceptance criteria
- [ ] `services/ingestion-service/README.md`'s connector section states both output paths (CSV and DB)
  exist, and which is the default going forward (DB) vs. retained for local/offline dev (CSV).
